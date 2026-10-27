"""IRIS brain — agentic loop using Ollama (OpenAI-compatible API)."""
import asyncio
import json
import os
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

## NEVER USE TOOLS FOR
- Greetings or small talk ("hello", "how are you", "what's up")
- Questions about your own identity ("what's your name", "who are you", "what are you")
- General knowledge or questions you already know the answer to
- Anything a person could answer without looking something up

## OUTPUT RULES
- Never output tool call JSON, function call syntax, or parameter dicts in your response text
- Answer directly — no preamble, no restating the question
- Never invent technical data (CPU%, GPU%, RAM usage, disk space, etc.) — call system_info or say you'd need to check
- Facts about Jevin from memory are injected below when relevant"""

_client = None

# Words that indicate a tool is likely needed even in short messages
_TOOL_KEYWORDS = {
    "search", "find", "look up", "file", "folder", "open", "run", "execute",
    "command", "remember", "save", "clipboard", "notify", "notification",
    "timer", "alarm", "window", "app", "application", "install", "download",
    "recall", "last time", "did we", "yesterday", "last week", "system",
    "cpu", "gpu", "ram", "disk", "battery", "temperature", "weather", "news",
    "status", "usage", "utilization", "performance", "memory", "storage",
}


def _needs_tools(text: str) -> bool:
    """Return False for purely conversational messages that don't need tools.

    Short messages (< 60 chars) only get tools if they contain a tool-trigger
    keyword. Longer messages always get tools (safe default).
    """
    if len(text.strip()) >= 60:
        return True
    text_lower = text.lower()
    return any(kw in text_lower for kw in _TOOL_KEYWORDS)


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

    while True:
        current_text = ""
        tool_calls_map: dict[int, dict] = {}
        finish_reason = None

        tools_for_turn = TOOL_DEFINITIONS if _needs_tools(user_text) else None
        try:
            stream = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools_for_turn,
                stream=True,
            )

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

    # Background tasks: extract facts and check for session close
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
    prompt = f"""Extract facts from this conversation worth storing in a personal AI assistant's world model.
Return a JSON array. Each element: {{"content": "...", "tier": "core|relevant|archive", "importance": 0.0-1.0, "tags": [...]}}
Return [] if nothing is worth storing. Return ONLY the JSON array, no other text.

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
            if isinstance(fact, dict) and "content" in fact:
                memory.write_fact(
                    content=fact["content"],
                    tier=fact.get("tier", "relevant"),
                    importance=float(fact.get("importance", 0.5)),
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
