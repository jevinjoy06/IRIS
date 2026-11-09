"""IRIS background device agent — executes commands dispatched from the hub.
Runs independently of the chat GUI/CLI so this device stays controllable
even when no chat window is open.

No process supervises this script, so it must not die on a bad message or a
dropped connection: malformed input from the hub is logged and ignored, and
any loss of the websocket connection triggers an automatic reconnect loop
rather than letting the process exit.
"""
import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path

import websockets

CONFIG_PATH = Path(__file__).parent / "config.json"
RECONNECT_DELAY_SECONDS = 5


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}\nCopy config.json.template -> config.json and fill in values.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def agent_url_from(hub_url: str) -> str:
    # ws://host:port/ws -> ws://host:port/ws/agent
    stripped = hub_url.rstrip("/")
    return stripped + "/agent" if stripped.endswith("/ws") else hub_url


def run_command(command: str, timeout: int) -> dict:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": True, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s", "stdout": "", "stderr": "", "returncode": -1}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": "", "returncode": -1}


async def handle_message(ws, raw: str) -> None:
    """Parse and act on one inbound message.

    Never raises: a malformed message (bad JSON, wrong type, missing fields)
    is logged and ignored instead of crashing the connection, since the hub
    is the only thing dispatching work here and a single bad message
    shouldn't take the agent down.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Ignoring malformed message (invalid JSON): {e}")
        return

    if not isinstance(msg, dict):
        print(f"Ignoring malformed message (expected a JSON object): {raw!r}")
        return

    if msg.get("type") != "exec_command":
        return

    command = msg.get("command")
    request_id = msg.get("request_id")
    if not isinstance(command, str) or not isinstance(request_id, str):
        print(f"Ignoring malformed exec_command (missing/invalid command or request_id): {msg!r}")
        return

    timeout = msg.get("timeout", 30)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        timeout = 30

    print(f"Executing (request_id={request_id}): {command!r}")
    result = run_command(command, timeout)
    result["type"] = "exec_result"
    result["request_id"] = request_id

    try:
        await ws.send(json.dumps(result))
    except websockets.ConnectionClosed as e:
        # The hub connection dropped between finishing the command and
        # sending the result back. Nothing to do but log it — the outer
        # reconnect loop will re-establish the connection and the hub's own
        # pending-request timeout handles the lost reply on its side.
        print(f"Could not send result for request_id={request_id}: connection closed ({e})")


async def run_once(config: dict) -> None:
    """Connect, register, and serve exec_command requests until disconnected."""
    url = agent_url_from(config.get("hub_url", "ws://localhost:7865/ws"))
    device_id = socket.gethostname()
    device_name = config.get("device_name")
    print(f"IRIS agent ({device_id}) connecting to {url}")

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "register", "device_id": device_id, "device_name": device_name}))
        print("Registered. Waiting for commands...")
        async for raw in ws:
            await handle_message(ws, raw)


async def run(config: dict) -> None:
    """Keep the agent connected for as long as the process runs.

    Nothing supervises this script, so a connection failure or drop must not
    be fatal: log it and retry after a fixed delay instead of exiting.
    """
    while True:
        try:
            await run_once(config)
        except (websockets.ConnectionClosed, OSError) as e:
            print(f"Connection to hub lost/unavailable: {e}")
        except Exception as e:
            # Catch-all so an unexpected error (e.g. a hub protocol change)
            # degrades to "retry later" rather than killing the agent.
            print(f"Unexpected agent error: {e}")
        print(f"Reconnecting in {RECONNECT_DELAY_SECONDS}s...")
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(run(load_config()))
    except KeyboardInterrupt:
        print("Agent stopped.")
