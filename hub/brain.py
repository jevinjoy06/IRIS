"""IRIS brain — agentic loop using Ollama (OpenAI-compatible API)."""
import asyncio
import base64
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

if TYPE_CHECKING:
    from fastapi import WebSocket

from hub import memory, tts
from hub.tools.registry import TOOL_DEFINITIONS, async_dispatch

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = """You are IRIS, Jevin's personal AI assistant running on his GPU PC. The person you are talking to IS Jevin (boss). Personality: direct, confident, dry humor, call him "boss" occasionally but not every sentence. No filler words ("Absolutely!", "Great question!", "Certainly!"). Keep responses brief.

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
- Never invent technical data (CPU%, GPU%, RAM usage, disk space, etc.) — call system_info or say you'd need to check
- Facts about Jevin from memory are injected below when relevant

## GROUNDING — NON-NEGOTIABLE
- Never state a specific file name, number, system fact, business/place name, price, address, review, or any other real-world specific unless it came from an actual tool result in this turn. If you have not called a tool, you do not have that data — say so, or call web_search, don't invent it.
- Never claim an action was performed (closing an app, deleting a file, saving something, etc.) unless a tool call actually ran and reported success. If no tool exists for what boss is asking, tell him directly instead of pretending.
- If a tool call errors or fails, report the failure in one line and stop — do not retry more than once, and do not fall back to guessing or estimating a plausible-sounding answer."""

_client = None

# Patterns that mean "this message needs no tool at all" — greetings, thanks,
# short acknowledgments, and questions about IRIS's own identity. This is a
# denylist, not an allow-list, deliberately: the set of topics that might need
# a tool (restaurants, prices, current events, directions, ...) is unbounded
# and can never be fully enumerated by keyword, but pure conversational
# chitchat is a small, closed category that can be. Tools default to being
# offered for everything else; tool_choice stays "auto" so visibility alone
# doesn't force a call — the model still judges, guided by the WHEN/NEVER TO
# USE TOOLS sections below, backed by the GROUNDING rule against fabricating
# specifics either way.
_NO_TOOL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^\s*(hi|hey|hello|yo|sup)\b.{0,20}$",
        r"\b(thanks|thank you|thx|appreciate it)\b",
        r"\bhow(?:'s| is| are) it going\b|\bwhat'?s up\b|\bhow are you\b",
        r"\bwho are you\b|\bwhat'?s your name\b|\bwhat are you\b",
        r"^\s*(ok|okay|cool|nice|great|got it|alright|sounds good|sure)\.?\s*$",
    ]
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

    # No unambiguous single tool — leave it to the model's own judgment (None
    # means the API's default "auto" applies) rather than forcing some call.
    # Forcing "required" here with no clear target risks forcing the wrong
    # tool on an open-ended message like a restaurant recommendation request.
    return None


def _needs_tools(text: str) -> bool:
    """Return False only for the small, closed set of pure-chitchat patterns.

    Everything else gets the tool list offered (tool_choice stays "auto", so
    this alone doesn't force a call). See _NO_TOOL_PATTERNS for why this is a
    denylist rather than an allow-list of trigger topics.
    """
    text_lower = text.strip().lower()
    if not text_lower:
        return False
    return not any(pattern.search(text_lower) for pattern in _NO_TOOL_PATTERNS)


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

    # Deterministic tools guarantee the model's tool-calling DECISION is
    # skipped for tools proven unreliable even under forced tool_choice —
    # Ollama/qwen2.5 was observed to sometimes skip the call entirely, or call
    # it and still report fabricated content instead of the real result.
    # Calling the tool ourselves, before the model is involved, guarantees a
    # real result exists. We do NOT short-circuit the rest of the turn here
    # (an earlier version did, via an immediate return) — a message can
    # legitimately bundle a deterministic-tool request with something else
    # ("what's on my clipboard, and what time did we last talk?"), and
    # returning early silently dropped the second half. Instead the real
    # result is seeded into the message history below as if the model had
    # called it itself, and the normal loop continues so anything else in a
    # compound request still gets handled, now grounded in real data.
    pre_seeded_messages: list[dict] = []
    tools_used_this_turn: set[str] = set()
    forced = _tool_choice_for(user_text)
    if isinstance(forced, dict):
        forced_name = forced["function"]["name"]
        if forced_name in _DETERMINISTIC_TOOLS:
            await ws.send_json({"type": "tool_use", "tool": forced_name})
            result = await async_dispatch(forced_name, {}, ws)
            memory.save_turn(session_id, "tool", result, tool_name=forced_name)
            tools_used_this_turn.add(forced_name)
            call_id = f"deterministic_{forced_name}"
            # The real tool result is included (role: "tool") for protocol
            # correctness, but we also pre-answer it as spoken assistant text
            # (role: "assistant") right after — this is the part that actually
            # prevents re-narration. Clipboard specifically was proven to
            # fabricate a *different* answer even when the real result was
            # already present as a plain tool message, so leaving the model a
            # fresh turn to "explain" that data in its own words reopens the
            # exact failure mode this bypass exists to close.
            deterministic_text = _DETERMINISTIC_TOOLS[forced_name](json.loads(result))
            pre_seeded_messages = [
                {"role": "assistant", "tool_calls": [{
                    "id": call_id, "type": "function",
                    "function": {"name": forced_name, "arguments": "{}"},
                }]},
                {"role": "tool", "tool_call_id": call_id, "content": result},
                {"role": "assistant", "content": deterministic_text},
            ]
            await ws.send_json({"type": "token", "text": deterministic_text})
            memory.save_turn(session_id, "assistant", deterministic_text)

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

    # Append current user message, then the pre-seeded deterministic-tool
    # call/result (if any), so the model sees it as already having happened.
    messages.append({"role": "user", "content": user_text})
    messages.extend(pre_seeded_messages)

    full_response_parts: list[str] = []

    while True:
        current_text = ""
        tool_calls_map: dict[int, dict] = {}
        finish_reason = None

        needs_tools = _needs_tools(user_text)
        tools_for_turn = TOOL_DEFINITIONS if needs_tools else None
        # Force an actual tool call on the first round when a keyword matched —
        # otherwise the model will sometimes skip the tool entirely and answer
        # from a memorized pattern instead of real data (observed repeatedly).
        # Skip forcing when we already pre-seeded that exact tool's result above —
        # forcing it again would just call it a second time for no reason.
        tool_choice = (
            None if (pre_seeded_messages and len(full_response_parts) == 0)
            else (_tool_choice_for(user_text) if len(full_response_parts) == 0 else None)
        )
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

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

                if tc["name"] in _DETERMINISTIC_TOOLS:
                    # Same reasoning as the pre-model bypass above: pre-answer
                    # with the real result as spoken assistant text so the
                    # model doesn't get a free turn to re-narrate (and
                    # potentially diverge from) data it's proven unreliable at
                    # reporting faithfully — but don't short-circuit the rest
                    # of this tool-call batch or the turn; other tool calls in
                    # the same batch still need their results appended below.
                    deterministic_text = _DETERMINISTIC_TOOLS[tc["name"]](json.loads(result))
                    messages.append({"role": "assistant", "content": deterministic_text})
                    await ws.send_json({"type": "token", "text": deterministic_text})
                    memory.save_turn(session_id, "assistant", deterministic_text)
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

    # Synthesize and stream speech audio for the response. Runs after "done"
    # so the text/UI side isn't held up waiting on synthesis; clients that
    # don't handle the "audio" message type (the laptop CLI client, etc.)
    # just ignore it, same as any other unrecognized message type.
    if current_text_final.strip() and tts.available():
        asyncio.create_task(_speak_response(current_text_final, ws))

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


async def _speak_response(text: str, ws: "WebSocket") -> None:
    """Synthesize text to speech and stream it to the client as a WS message.

    Kokoro synthesis is blocking CPU/GPU work, so it runs in the default
    executor rather than the event loop — otherwise it would stall every
    other active session on the hub for the duration of synthesis.
    """
    try:
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, tts.synthesize_wav, text)
        await ws.send_json({
            "type": "audio",
            "format": "wav",
            "data": base64.b64encode(wav_bytes).decode("ascii"),
        })
    except Exception as e:
        # Non-fatal and silent to the client: the text response already
        # succeeded, and a generic "error" message risks being misread by
        # the client as the whole turn having failed. Log server-side only.
        print(f"[tts] synthesis failed: {e}", flush=True)


async def _extract_facts(user_text: str, assistant_response: str, client) -> None:
    prompt = f"""Extract facts from this conversation worth storing LONG-TERM in a personal AI assistant's world model.

Only extract durable facts about the user: stable preferences, identity, relationships, ongoing projects, or things they explicitly asked to be remembered. Do NOT extract: greetings/small talk, the assistant's own identity or capabilities, one-off tool results (file listings, search results), transient status updates, system metrics or hardware stats (CPU/GPU/RAM/disk percentages, real-time system state), or anything that will be stale within hours.

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
