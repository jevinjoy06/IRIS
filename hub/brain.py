"""IRIS brain — agentic Claude loop with streaming + tool use + memory."""
import json
import os
from typing import TYPE_CHECKING

from hub import memory
from hub.tools.registry import TOOL_DEFINITIONS, dispatch

if TYPE_CHECKING:
    from fastapi import WebSocket

MODEL = "claude-sonnet-4-6"
EXTRACT_MODEL = "claude-haiku-4-5-20251001"

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
- Confirm before writing or deleting files unless the user has already indicated intent.

{memory_context}"""


async def process_turn(user_text: str, ws: "WebSocket") -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        await ws.send_json({
            "type": "error",
            "text": "ANTHROPIC_API_KEY is not set. Add it to hub/.env and restart the server.",
        })
        return

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)

    mem_context = memory.build_memory_context(user_text)
    system = SYSTEM_PROMPT.format(memory_context=mem_context).strip()

    messages: list[dict] = [{"role": "user", "content": user_text}]
    full_response_parts: list[str] = []

    while True:
        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        ) as stream:
            # Stream text tokens to the client
            async for token in stream.text_stream:
                full_response_parts.append(token)
                await ws.send_json({"type": "token", "text": token})

            final = await stream.get_final_message()

        stop_reason = final.stop_reason

        if stop_reason == "tool_use":
            # Append assistant turn (may include text + tool_use blocks)
            messages.append({"role": "assistant", "content": _blocks_to_params(final.content)})

            # Execute each tool and collect results
            tool_results = []
            for block in final.content:
                if block.type == "tool_use":
                    await ws.send_json({"type": "tool_use", "tool": block.name})
                    result_str = dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "user", "content": tool_results})
            # Continue the loop — Claude will process results and respond

        else:
            # end_turn or stop_sequence — done
            messages.append({"role": "assistant", "content": _blocks_to_params(final.content)})
            break

    await ws.send_json({"type": "done"})

    full_response = "".join(full_response_parts)
    if full_response.strip():
        await _extract_facts(user_text, full_response, client)


def _blocks_to_params(content) -> list[dict]:
    """Convert Anthropic SDK content blocks → plain dicts for the messages list."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


async def _extract_facts(user_text: str, assistant_response: str, client) -> None:
    """Use Haiku to extract new facts and write them to the world model."""
    prompt = f"""Extract facts from this conversation worth storing in a personal AI assistant's world model.
Return a JSON array. Each element: {{"content": "...", "tier": "core|relevant|archive", "importance": 0.0-1.0, "tags": [...]}}
Return [] if nothing is worth storing. Return ONLY the JSON array, no other text.

User: {user_text}
Assistant: {assistant_response}"""

    try:
        response = await client.messages.create(
            model=EXTRACT_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
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
        pass  # Extraction is best-effort; never crash the main turn
