"""IRIS brain — agentic loop using Ollama (OpenAI-compatible API)."""
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

if TYPE_CHECKING:
    from fastapi import WebSocket

from hub import memory
from hub.tools.registry import TOOL_DEFINITIONS, dispatch

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = """You are IRIS — Intelligent Responsive Interface System — Jevin's personal AI assistant running on his GPU PC.

You have access to his file system, the web, and a persistent world model you can read and write. You remember facts about his life, projects, preferences, and commitments across all conversations.

Personality:
- Direct and brief. Short answers by default. Elaborate only when depth is asked for.
- Capable and confident. "I'll handle it." then handle it.
- Consistent identity across every device and channel.

Memory:
- After every turn you extract and store new facts. Relevant facts from your world model are injected below.
- When you learn something worth keeping — a preference, a deadline, a project detail — write it with memory_write.

Tools:
- Use tools when they are the right way to answer. Don't ask permission for routine file reads or web searches.
- Confirm before writing or deleting files unless the user has already indicated intent."""


def _make_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


async def process_turn(user_text: str, ws: "WebSocket") -> None:
    client = _make_client()

    mem_context = memory.build_memory_context(user_text)
    system = SYSTEM_PROMPT + ("\n\n" + mem_context if mem_context else "")

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    full_response_parts: list[str] = []

    while True:
        current_text = ""
        tool_calls_map: dict[int, dict] = {}
        finish_reason = None

        try:
            stream = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
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
            return

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

            for tc in tool_calls_map.values():
                await ws.send_json({"type": "tool_use", "tool": tc["name"]})
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(tc["name"], args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
        else:
            messages.append({"role": "assistant", "content": current_text})
            break

    await ws.send_json({"type": "done"})

    full_response = "".join(full_response_parts)
    if full_response.strip():
        await _extract_facts(user_text, full_response, client)


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
