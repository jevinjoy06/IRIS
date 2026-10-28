"""IRIS brain — agentic loop using Ollama (OpenAI-compatible API)."""
import asyncio
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

if TYPE_CHECKING:
    from fastapi import WebSocket

from hub import memory
from hub.tools.registry import TOOL_DEFINITIONS, async_dispatch

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = """You are IRIS, Jevin's personal AI assistant running on his GPU PC. Personality: direct, confident, dry humor, call him "boss" occasionally but not every sentence. No filler words ("Absolutely!", "Great question!", "Certainly!"). Keep responses brief.

## WHEN TO USE TOOLS
Only call a tool when you need data you cannot produce yourself:
- file_read / file_write / file_list — boss asks about files on his machine
- web_search — boss asks about current events or something to look up online
- shell_run — boss asks you to run a command or script
- clipboard_read / clipboard_write — boss asks about his clipboard
- system_info — boss asks about his PC hardware or status
- notify — boss asks you to send a desktop notification
- timer_set — boss asks to set a timer
- window_list / window_focus / app_open — boss asks about open windows or apps
- memory_recall — boss specifically asks "what did we talk about" or "do you remember X"
- memory_write — boss explicitly says "remember this" or "save this"

## CAPABILITY GAPS — BE HONEST ABOUT THESE
You have NO way to close, kill, or quit an app or window — only list, focus, and open. If boss asks you to close/kill/quit something, tell him plainly you can't do that yet. Never say "closing X" or "done" for an action you have no tool for.

## NEVER USE TOOLS FOR
- Greetings or small talk ("hello", "how are you", "what's up")
- Questions about your own identity ("what's your name", "who are you", "what are you")
- General knowledge or questions you already know the answer to
- Anything a person could answer without looking something up

## OUTPUT RULES
- Never output tool call JSON, function call syntax, or parameter dicts in your response text
- Answer directly — no preamble, no restating the question
- Facts about Jevin from memory are injected below when relevant

## GROUNDING — NON-NEGOTIABLE
- Never state a specific file name, number, or system fact unless it came from an actual tool result in this turn. If you have not called a tool, you do not have that data — say so, don't invent it.
- Never claim an action was performed (closing an app, deleting a file, saving something, etc.) unless a tool call actually ran and reported success. If no tool exists for what boss is asking, tell him directly instead of pretending.
- If a tool call errors or fails, report the failure in one line and stop — do not retry more than once, and do not fall back to guessing or estimating a plausible-sounding answer."""

_client = None

# Words/phrases that indicate a tool is likely needed, regardless of message length.
_TOOL_KEYWORDS = {
    "search", "find", "look up", "file", "folder", "open", "run", "execute",
    "command", "remember", "save", "clipboard", "notify", "notification",
    "timer", "alarm", "window", "app", "application", "install", "download",
    "close", "kill", "quit", "exit",
    "recall", "last time", "did we", "yesterday", "last week", "system",
    "cpu", "ram", "disk", "battery", "temperature", "weather", "news",
}

# Whole-word/phrase matchers, so "research" doesn't match "search" and
# "installation" doesn't match "install".
_TOOL_KEYWORD_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b") for kw in _TOOL_KEYWORDS
]

# Keywords that unambiguously imply exactly one tool. Generic tool_choice="required"
# was observed to be silently ignored by Ollama for this model (e.g. clipboard_read),
# so when we can name the single tool directly, we force that tool by name instead.
_KEYWORD_TO_TOOL = {
    "search": "web_search", "find": "web_search", "look up": "web_search",
    "news": "web_search", "weather": "web_search",
    "folder": "file_list",
    "run": "shell_run", "execute": "shell_run", "command": "shell_run",
    "remember": "memory_write", "save": "memory_write",
    "notify": "notify", "notification": "notify",
    "timer": "timer_set", "alarm": "timer_set",
    "recall": "memory_recall", "last time": "memory_recall", "did we": "memory_recall",
    "yesterday": "memory_recall", "last week": "memory_recall",
    "system": "system_info", "cpu": "system_info", "ram": "system_info",
    "disk": "system_info", "battery": "system_info", "temperature": "system_info",
}

# Keywords with genuinely no matching tool — never force a call for these;
# the capability-gap prompt section handles honesty about them instead.
_NO_TOOL_KEYWORDS = {"close", "kill", "quit", "exit", "install", "download"}


def _tool_choice_for(text: str) -> "str | dict | None":
    """Decide tool_choice for the first round of a turn.

    Returns a specific function-forcing dict when exactly one tool is
    unambiguously implied, "required" when some tool is needed but which
    one isn't clear-cut, or None to leave it to the model (including when
    no real tool exists for the request at all).
    """
    text_lower = text.lower()

    # Clipboard is common and genuinely ambiguous (read vs write) — special-cased
    # directly since generic "required" forcing was observed to be skipped here.
    if re.search(r"\bclipboard\b", text_lower):
        name = "clipboard_write" if re.search(r"\bcopy\b", text_lower) else "clipboard_read"
        return {"type": "function", "function": {"name": name}}

    if any(re.search(r"\b" + re.escape(kw) + r"\b", text_lower) for kw in _NO_TOOL_KEYWORDS):
        return None

    matched_tools = {
        tool for kw, tool in _KEYWORD_TO_TOOL.items()
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)
    }
    if len(matched_tools) == 1:
        return {"type": "function", "function": {"name": next(iter(matched_tools))}}

    return "required" if _needs_tools(text) else None


def _needs_tools(text: str) -> bool:
    """Return True only if the message contains a whole-word tool-trigger keyword.

    Message length is not a signal on its own: long messages are routinely
    pure conversation (venting, opinions, follow-ups) and must not be handed
    the full tool list just because they're wordy.
    """
    text_lower = text.lower()
    return any(pattern.search(text_lower) for pattern in _TOOL_KEYWORD_PATTERNS)


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    return _client


async def process_turn(
    user_text: str,
    ws: "WebSocket",
    session_id: str | None = None,
    turn_number: int = 1,
) -> bool:
    """Process a turn. Returns True if session was closed this turn."""
    client = _get_client()

    # Initialize session if not provided
    if session_id is None:
        session_id = memory.start_session()

    # Update session activity
    memory.update_session_last_active(session_id)

    # Save user message
    memory.save_turn(session_id, "user", user_text)

    # Deterministic tools bypass the model's tool-calling decision entirely.
    # Ollama/qwen2.5 was proven (repeatedly, even with the specific tool forced
    # via tool_choice) to sometimes skip calling the tool altogether and emit
    # fabricated content instead — forcing happens at the API layer, which this
    # exact model/runtime combo doesn't reliably honor. Calling the tool
    # ourselves, before the model is ever involved, is the only guarantee.
    forced = _tool_choice_for(user_text)
    if isinstance(forced, dict):
        forced_name = forced["function"]["name"]
        if forced_name in _DETERMINISTIC_TOOLS:
            await ws.send_json({"type": "tool_use", "tool": forced_name})
            result = await async_dispatch(forced_name, {}, ws)
            memory.save_turn(session_id, "tool", result, tool_name=forced_name)
            deterministic_text = _DETERMINISTIC_TOOLS[forced_name](json.loads(result))
            await ws.send_json({"type": "token", "text": deterministic_text})
            await ws.send_json({"type": "done"})
            memory.save_turn(session_id, "assistant", deterministic_text)
            return False

    mem_context = memory.build_memory_context(user_text)

    # On first turn, search for related sessions
    resume_note = ""
    if turn_number == 1:
        related = memory.search_sessions(user_text, limit=3)
        if related:
            resume_snippets = []
            for sess in related:
                label = sess.get("label") or "(unlabeled)"
                summary = sess.get("summary") or ""
                snippet = f"  - {label}"
                if summary:
                    snippet += f": {summary[:60]}..."
                resume_snippets.append(snippet)
            resume_note = (
                "\n\n## Possibly continuing\n"
                "You may be picking up from a past session. Candidates:\n"
                + "\n".join(resume_snippets)
                + "\nIf this seems related to what boss just said, ask casually in one line if he wants to pick that up. If it's clearly something new, just respond normally."
            )

    # Build message history (user/assistant roles only)
    recent_turns = memory.get_session_turns(session_id, limit=20)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT + ("\n\n" + mem_context if mem_context else "") + resume_note},
    ]

    # Add historical turns (skip tool turns and the current user turn already saved)
    for t in recent_turns[:-1]:
        if t["role"] == "user":
            messages.append({"role": "user", "content": t["content"]})
        elif t["role"] == "assistant":
            messages.append({"role": "assistant", "content": t["content"]})

    # Append current user message
    messages.append({"role": "user", "content": user_text})

    full_response_parts: list[str] = []
    tools_used_this_turn: set[str] = set()

    while True:
        current_text = ""
        tool_calls_map: dict[int, dict] = {}
        finish_reason = None

        needs_tools = _needs_tools(user_text)
        tools_for_turn = TOOL_DEFINITIONS if needs_tools else None
        # Force an actual tool call on the first round when a keyword matched —
        # otherwise the model will sometimes skip the tool entirely and answer
        # from a memorized pattern instead of real data (observed repeatedly).
        tool_choice = _tool_choice_for(user_text) if len(full_response_parts) == 0 else None
        try:
            create_kwargs = dict(
                model=MODEL,
                messages=messages,
                tools=tools_for_turn,
                stream=True,
                temperature=0.1,
            )
            if tool_choice:
                create_kwargs["tool_choice"] = tool_choice
            # Ollama defaults to a 4096-token context window, which a long
            # transcription or tool-heavy turn can exceed — observed to cause
            # language-consistency breakdowns when it does.
            create_kwargs["extra_body"] = {"options": {"num_ctx": 8192}}
            stream = await client.chat.completions.create(**create_kwargs)

            async for chunk in stream:
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta

                if delta.content:
                    current_text += delta.content
                    full_response_parts.append(delta.content)
                    await ws.send_json({"type": "token", "text": delta.content})

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_map[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_map[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_map[idx]["arguments"] += tc.function.arguments

        except Exception as e:
            await ws.send_json({"type": "error", "text": str(e)})
            return False

        if finish_reason == "tool_calls" and tool_calls_map:
            tool_calls_list = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_map.values()
            ]
            assistant_msg: dict = {"role": "assistant", "tool_calls": tool_calls_list}
            if current_text:
                assistant_msg["content"] = current_text
            messages.append(assistant_msg)

            # Save assistant message with tool calls
            if current_text:
                memory.save_turn(session_id, "assistant", current_text)

            for tc in tool_calls_map.values():
                tools_used_this_turn.add(tc["name"])
                await ws.send_json({"type": "tool_use", "tool": tc["name"]})
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    args = {}
                result = await async_dispatch(tc["name"], args, ws)
                # Save tool call result
                memory.save_turn(session_id, "tool", result, tool_name=tc["name"])

                if tc["name"] in _DETERMINISTIC_TOOLS:
                    deterministic_text = _DETERMINISTIC_TOOLS[tc["name"]](json.loads(result))
                    await ws.send_json({"type": "token", "text": deterministic_text})
                    await ws.send_json({"type": "done"})
                    memory.save_turn(session_id, "assistant", deterministic_text)
                    return False

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
        else:
            messages.append({"role": "assistant", "content": current_text})
            # Save final assistant message
            if current_text:
                memory.save_turn(session_id, "assistant", current_text)
            break

    await ws.send_json({"type": "done"})

    # Get final response text
    current_text_final = ""
    if messages and messages[-1]["role"] == "assistant":
        current_text_final = messages[-1].get("content", "")

    # Background tasks: extract facts and check for session close.
    # Skip extraction entirely when a transient/snapshot tool was used this turn —
    # their results (CPU%, directory listings, search results, clipboard contents)
    # are stale within minutes and the extractor unreliably stores them as if durable.
    if not (tools_used_this_turn & _TRANSIENT_TOOLS):
        asyncio.create_task(_extract_facts(user_text, current_text_final, client))

    # On first turn, label the session in background
    if turn_number == 1:
        asyncio.create_task(_label_session(session_id, user_text, current_text_final))

    # Detect if user is closing the conversation
    should_close = await _detect_close_intent(user_text)
    if should_close:
        asyncio.create_task(_write_session_summary(session_id))
        await ws.send_json({"type": "session_closed"})
        return True

    return False


async def _extract_facts(user_text: str, assistant_response: str, client) -> None:
    prompt = f"""Extract facts from this conversation worth storing LONG-TERM in a personal AI assistant's world model.

Only extract durable facts about the user: stable preferences, identity, relationships, ongoing projects, or things they explicitly asked to be remembered. Do NOT extract: greetings/small talk, the assistant's own identity or capabilities, one-off tool results (file listings, system stats, search results), transient status updates, or anything that will be stale within hours.

"core" tier is reserved for facts the assistant should basically always know (e.g. the user's name, role, long-running projects) — use it sparingly, at most one fact here. Most things belong in "relevant" or should not be stored at all.

Return a JSON array. Each element: {{"content": "...", "tier": "core|relevant|archive", "importance": 0.0-1.0, "tags": [...]}}
Return [] if nothing durable is worth storing — this is the common case, most turns produce nothing. Return ONLY the JSON array, no other text.

User: {user_text}
Assistant: {assistant_response}"""

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        facts = json.loads(raw)
        for fact in facts:
            if not isinstance(fact, dict) or "content" not in fact:
                continue
            content = str(fact["content"]).strip()
            # Quality gate: skip trivial/fragment-length content regardless of
            # what tier/importance the extractor assigned it.
            if len(content) < 20 or len(content.split()) < 3:
                continue
            tier = fact.get("tier", "relevant")
            importance = float(fact.get("importance", 0.5))
            # Core tier is reserved for genuinely high-confidence durable facts.
            if tier == "core" and importance < 0.85:
                tier = "relevant"
            memory.write_fact(
                content=content,
                tier=tier,
                importance=importance,
                tags=fact.get("tags"),
            )
    except Exception:
        pass


async def _label_session(session_id: str, first_message: str, response: str) -> None:
    """Generate a 3-6 word label for the session in background."""
    try:
        client = _get_client()
        prompt = f"""Generate a 3-6 word label for this conversation topic. Be concise and descriptive.

User: {first_message[:200]}
Assistant: {response[:200]}

Return ONLY the label text, nothing else."""

        result = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
        )
        label = result.choices[0].message.content.strip()
        if label:
            memory.label_session(session_id, label)
    except Exception:
        pass


# Tools whose results get formatted directly by code instead of being handed
# back to the model for prose synthesis. clipboard_read was proven (repeatedly,
# across generic/specific tool_choice forcing, temperature changes, and a fresh
# model reload) to confidently fabricate completely unrelated content instead of
# relaying its own real tool result — this bypasses that failure mode entirely
# for this one tool rather than trusting the model to report it faithfully.
def _format_clipboard_read(result: dict) -> str:
    if not result.get("ok"):
        return f"Couldn't read the clipboard: {result.get('error', 'unknown error')}"
    text = result.get("text", "")
    if not text:
        return "Your clipboard is empty, boss."
    return f'Your clipboard has: "{text}"'


_DETERMINISTIC_TOOLS = {
    "clipboard_read": _format_clipboard_read,
}


_TRANSIENT_TOOLS = {
    "system_info", "shell_run", "file_list", "file_read", "window_list",
    "clipboard_read", "web_search",
}


_CLOSE_PHRASES = {
    "goodbye", "good bye", "bye", "see you", "see ya", "cya",
    "that's all", "thats all", "we're done", "were done",
    "i'm done", "im done", "all set", "i'm all set", "im all set",
    "thanks for your help", "we're good", "were good",
    "no more questions", "that will be all", "see you later",
}


async def _detect_close_intent(user_text: str) -> bool:
    """Detect if user is signaling conversation wrap-up via keyword match."""
    text = user_text.lower().strip()
    return any(phrase in text for phrase in _CLOSE_PHRASES)


async def _write_session_summary(session_id: str) -> None:
    """Write a 2-3 sentence summary of the session."""
    try:
        turns = memory.get_session_turns(session_id, limit=30)
        conversation_text = ""
        for t in turns:
            role = t["role"].upper()
            content = t["content"][:100]
            conversation_text += f"[{role}]: {content}\n"

        client = _get_client()
        prompt = f"""Summarize this conversation in 2-3 sentences.

{conversation_text}

Return ONLY the summary, no other text."""

        result = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        summary = result.choices[0].message.content.strip()
        if summary:
            memory.close_session(session_id, summary)
    except Exception:
        memory.close_session(session_id, None)


async def close_session_externally(session_id: str, ws: "WebSocket") -> None:
    """Close a session due to external trigger (silence timeout)."""
    try:
        await _write_session_summary(session_id)
        await ws.send_json({"type": "session_closed"})
    except Exception:
        pass
