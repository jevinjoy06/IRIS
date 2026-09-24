"""IRIS Laptop Client — connects to the hub running on the desktop over the network."""
import asyncio
import json
import os
import sys
from pathlib import Path

import websockets

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}\nCopy config.json.template → config.json and fill in the hub IP.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


async def run(config: dict) -> None:
    hub_url = config.get("hub_url")
    if not hub_url:
        print("hub_url is required in config.json (e.g. ws://192.168.1.x:7865/ws or a tunnel URL)")
        sys.exit(1)

    print(f"IRIS Laptop connecting to {hub_url}")

    async with websockets.connect(hub_url) as ws:
        print("Connected. Type a message (Ctrl+C to quit):")
        while True:
            text = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
            if not text.strip():
                continue
            await ws.send(json.dumps({"type": "message", "text": text}))

            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "token":
                    print(msg["text"], end="", flush=True)
                elif msg["type"] == "tool_use":
                    print(f"\n[tool: {msg['tool']}]", flush=True)
                elif msg["type"] == "error":
                    print(f"\n[error: {msg['text']}]", flush=True)
                    break
                elif msg["type"] == "done":
                    print()
                    break


if __name__ == "__main__":
    config = load_config()
    asyncio.run(run(config))
