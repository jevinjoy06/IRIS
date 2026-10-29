"""IRIS Desktop Client — runs on the GPU PC alongside the hub."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

CONFIG_PATH = Path(__file__).parent / "config.json"
VOICE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "voice" / "config.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}\nCopy config.json.template → config.json and fill in values.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def load_voice_config(hub_url: str) -> dict:
    """Load voice/config.json and inject the desktop hub_url."""
    cfg = json.loads(VOICE_CONFIG_PATH.read_text()) if VOICE_CONFIG_PATH.exists() else {}
    cfg["hub_url"] = hub_url

    # Resolve model path relative to voice/ directory
    model_val = cfg.get("wake_word_model", "")
    if model_val:
        candidate = VOICE_CONFIG_PATH.parent / model_val
        if candidate.exists():
            cfg["wake_word_model"] = str(candidate)

    return cfg


async def run_text(config: dict) -> None:
    hub_url = config.get("hub_url", "ws://localhost:7865/ws")
    print(f"IRIS Desktop connecting to {hub_url}")

    async with websockets.connect(hub_url) as ws:
        print("Connected. Type a message (Ctrl+C to quit):")
        while True:
            text = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
            if not text.strip():
                continue
            t_send = time.perf_counter()
            await ws.send(json.dumps({"type": "message", "text": text}))
            first_token = True

            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "token":
                    if first_token:
                        print(f"[{(time.perf_counter() - t_send)*1000:.0f} ms] ", end="", flush=True)
                        first_token = False
                    print(msg["text"], end="", flush=True)
                elif msg["type"] == "tool_use":
                    print(f"\n[tool: {msg['tool']}]", flush=True)
                elif msg["type"] == "error":
                    print(f"\n[error: {msg['text']}]", flush=True)
                    break
                elif msg["type"] == "done":
                    print(f"\n[total: {(time.perf_counter() - t_send)*1000:.0f} ms]")
                    break


def run_voice(config: dict) -> None:
    # Ensure project root is importable
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from voice.pipeline import Pipeline
    voice_cfg = load_voice_config(config["hub_url"])
    Pipeline(voice_cfg).run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IRIS Desktop Client")
    parser.add_argument("--voice", action="store_true", help="Run voice pipeline (wake word + mic)")
    args = parser.parse_args()

    config = load_config()

    if args.voice:
        run_voice(config)
    else:
        asyncio.run(run_text(config))
