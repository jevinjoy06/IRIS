"""IRIS Hub — FastAPI + WebSocket server."""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hub import brain, devices, memory, pending_confirmations
from hub.tools import remote_exec
from hub.tools.system_info import get_system_info

_STATIC = Path(__file__).parent / "static"

# Session activity tracking: session_id -> {"ws": WebSocket, "turn_count": int, "last_message_at": datetime, "checkin_sent": bool, "tier2_sent": bool}
_active_sessions: dict = {}

# Queue sentinel the /ws reader task posts when the socket closes. A private
# object rather than a {"type": ...} dict, so a client can't forge it.
_DISCONNECT = object()

_LOOPBACK_HOSTS = ("127.0.0.1", "::1")


def _is_loopback(ws: WebSocket) -> bool:
    """True if the peer address is loopback, or equals the hub's own
    currently-configured HUB_HOST.

    uvicorn binds to exactly one host. If HUB_HOST is set to a non-loopback
    address (e.g. the hub's Tailscale IP, so remote devices can reach it),
    the hub stops listening on 127.0.0.1/::1 entirely — so a client on the
    hub machine itself has to reconnect via that same address instead of
    localhost. Its peer address is then HUB_HOST's value, not loopback, but
    it's still physically the same machine, so it must still be recognized
    as local (e.g. to claim the hub's own device_id). This does NOT treat
    every device on the tailnet as local — only a peer address that matches
    the hub's own bind address exactly.
    """
    if ws.client is None:
        return False
    host = ws.client.host
    if host in _LOOPBACK_HOSTS:
        return True
    configured_host = os.environ.get("HUB_HOST", "127.0.0.1")
    return host == configured_host


async def _silence_monitor() -> None:
    """Monitor silence in active sessions and send check-ins or close."""
    while True:
        await asyncio.sleep(30)
        try:
            # Use list() for safe iteration during potential modifications
            for session_id, info in list(_active_sessions.items()):
                ws = info.get("ws")
                if not ws:
                    continue

                now = datetime.now(timezone.utc)
                last_msg_time = info.get("last_message_at")
                if not last_msg_time:
                    continue

                elapsed = (now - last_msg_time).total_seconds()

                # 3 min: send check-in
                if elapsed >= 180 and not info.get("checkin_sent"):
                    try:
                        await ws.send_json({
                            "type": "token",
                            "text": "Still with you boss — take your time."
                        })
                        await ws.send_json({"type": "done"})
                        info["checkin_sent"] = True
                    except Exception:
                        pass

                # 10 min: send tier-2 message and mark warm
                if elapsed >= 600 and not info.get("tier2_sent"):
                    try:
                        await ws.send_json({
                            "type": "token",
                            "text": "I'll be here when you're ready — just say IRIS."
                        })
                        await ws.send_json({"type": "done"})
                        info["tier2_sent"] = True
                        memory.set_session_warm(session_id)
                    except Exception:
                        pass

                # 30 min: close session
                if elapsed >= 1800:
                    try:
                        asyncio.create_task(brain.close_session_externally(session_id, ws))
                    except Exception:
                        pass
                    _active_sessions.pop(session_id, None)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory.init_db()
    devices.register_hub_self()
    asyncio.create_task(_silence_monitor())
    yield


app = FastAPI(title="IRIS Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_connected_clients: set[WebSocket] = set()


@app.get("/")
async def index() -> HTMLResponse:
    html_path = _STATIC / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>IRIS Hub</h1><p>static/index.html not found.</p>")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse({
        "connected_clients": len(_connected_clients),
        "model": os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
        "ollama_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    })


# Defined as a plain (non-async) endpoint deliberately: get_system_info() blocks
# for ~1s (psutil.cpu_percent sampling) plus an nvidia-smi subprocess call.
# FastAPI runs sync def endpoints in a thread pool, so this can't stall the
# event loop and starve active WebSocket chat sessions while a dashboard polls it.
@app.get("/api/system")
def system_telemetry() -> JSONResponse:
    return JSONResponse(get_system_info())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_clients.add(ws)
    session_id = memory.start_session()
    turn_count = 0

    # Register session in active tracking
    _active_sessions[session_id] = {
        "ws": ws,
        "turn_count": 0,
        "last_message_at": datetime.now(timezone.utc),
        "checkin_sent": False,
        "tier2_sent": False,
    }

    # Receiving is decoupled from turn processing. A turn can block for a long
    # time inside process_turn (e.g. execute_remote awaiting a destructive-
    # command confirmation), and the confirm_response that unblocks it arrives
    # on this same socket. If the turn loop were also the only thing calling
    # receive_json(), that reply could never be read: deadlock. So a reader
    # task owns the socket's receive side, handles the side-channel messages
    # (register_device, confirm_response) immediately, and queues everything
    # else for the turn loop below.
    inbound_queue: asyncio.Queue = asyncio.Queue()

    async def reader() -> None:
        try:
            while True:
                try:
                    data = await ws.receive_json()
                except WebSocketDisconnect:
                    return
                except Exception as e:
                    # Malformed frame (bad JSON, wrong types, etc.) — report it and
                    # keep listening instead of killing the whole session over one
                    # bad message. A voice client hiccup shouldn't end the conversation.
                    await ws.send_json({"type": "error", "text": f"Malformed message: {e}"})
                    continue

                if not isinstance(data, dict):
                    await ws.send_json(
                        {"type": "error", "text": "Malformed message: expected a JSON object"}
                    )
                    continue

                msg_type = data.get("type")
                if msg_type == "register_device":
                    device_id = data.get("device_id")
                    device_name = data.get("device_name")
                    if not isinstance(device_id, str) or not (
                        device_name is None or isinstance(device_name, str)
                    ):
                        await ws.send_json(
                            {"type": "error", "text": "register_device needs a string device_id"}
                        )
                        continue
                    devices.register_chat(
                        device_id, device_name, ws, is_local=_is_loopback(ws)
                    )
                elif msg_type == "confirm_response":
                    request_id = data.get("request_id")
                    if isinstance(request_id, str):
                        # Fail closed: only a literal JSON true approves. bool()
                        # would treat e.g. the string "false" as approval.
                        pending_confirmations.resolve(request_id, data.get("approved") is True)
                else:
                    await inbound_queue.put(data)
        finally:
            # However the reader ends (clean disconnect, or a send failing on a
            # dead socket), wake the turn loop so the session is torn down
            # instead of waiting on the queue forever.
            inbound_queue.put_nowait(_DISCONNECT)

    reader_task = asyncio.create_task(reader())

    try:
        while True:
            data = await inbound_queue.get()
            if data is _DISCONNECT:
                raise WebSocketDisconnect()

            try:
                if data.get("type") == "message":
                    text = data.get("text")
                    text = str(text).strip() if text is not None else ""
                    if text:
                        turn_count += 1

                        # Update activity timestamp and reset silence counters
                        if session_id in _active_sessions:
                            _active_sessions[session_id].update({
                                "last_message_at": datetime.now(timezone.utc),
                                "turn_count": turn_count,
                                "checkin_sent": False,
                                "tier2_sent": False,
                            })

                        # Process turn
                        session_closed = await brain.process_turn(
                            text,
                            ws,
                            session_id=session_id,
                            turn_number=turn_count,
                            origin_device_id=devices.get_device_id_for_chat_ws(ws),
                        )

                        # If session was closed, start a new one
                        if session_closed:
                            session_id = memory.start_session()
                            turn_count = 0
                            _active_sessions[session_id] = {
                                "ws": ws,
                                "turn_count": 0,
                                "last_message_at": datetime.now(timezone.utc),
                                "checkin_sent": False,
                                "tier2_sent": False,
                            }
            except WebSocketDisconnect:
                raise
            except Exception as e:
                # Error while processing a well-formed message — report it and
                # keep the session alive rather than dropping the connection.
                await ws.send_json({"type": "error", "text": str(e)})
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        # Retrieve the task's outcome (cancellation or a send error on a dead
        # socket) so it isn't logged as "exception was never retrieved".
        await asyncio.gather(reader_task, return_exceptions=True)
        _connected_clients.discard(ws)
        _active_sessions.pop(session_id, None)
        devices.unregister_chat(ws)


@app.websocket("/ws/agent")
async def agent_websocket_endpoint(ws: WebSocket) -> None:
    """Connection from a device's background agent, which executes commands."""
    await ws.accept()
    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except Exception as e:
                await ws.send_json({"type": "error", "text": f"Malformed message: {e}"})
                continue

            if not isinstance(data, dict):
                await ws.send_json(
                    {"type": "error", "text": "Malformed message: expected a JSON object"}
                )
                continue

            msg_type = data.get("type")
            if msg_type == "register":
                device_id = data.get("device_id")
                device_name = data.get("device_name")
                if not isinstance(device_id, str) or not (
                    device_name is None or isinstance(device_name, str)
                ):
                    await ws.send_json(
                        {"type": "error", "text": "register needs a string device_id"}
                    )
                    continue
                devices.register_agent(device_id, device_name, ws)
            elif msg_type == "exec_result":
                request_id = data.get("request_id")
                if isinstance(request_id, str):
                    remote_exec.resolve_exec_result(request_id, ws, data)
    finally:
        devices.unregister_agent(ws)
        # Fail any command still pending for this exact connection immediately
        # instead of making the hub wait out the full timeout for a reply
        # that can now never arrive.
        remote_exec.fail_pending_for_ws(ws)


# Pydantic models for REST API
class FactCreate(BaseModel):
    content: str
    tier: str = "relevant"
    importance: float = 0.5
    tags: list[str] = []


class FactUpdate(BaseModel):
    content: str | None = None
    tier: str | None = None
    importance: float | None = None
    tags: list[str] | None = None


# Facts REST endpoints
@app.get("/api/facts")
async def list_facts_endpoint() -> JSONResponse:
    """List all non-archived facts, sorted by importance descending."""
    facts = memory.list_facts(include_archived=False)
    return JSONResponse(facts)


@app.get("/api/facts/{fact_id}")
async def get_fact_endpoint(fact_id: int) -> JSONResponse:
    """Get a single fact by ID."""
    fact = memory.get_fact(fact_id)
    if fact is None:
        return JSONResponse({"error": "Fact not found"}, status_code=404)
    return JSONResponse(fact)


@app.post("/api/facts")
async def create_fact_endpoint(body: FactCreate) -> JSONResponse:
    """Create a new fact."""
    fact_id = memory.write_fact(
        content=body.content,
        tier=body.tier,
        importance=body.importance,
        tags=body.tags,
    )
    fact = memory.get_fact(fact_id)
    return JSONResponse(fact, status_code=201)


@app.patch("/api/facts/{fact_id}")
async def update_fact_endpoint(fact_id: int, body: FactUpdate) -> JSONResponse:
    """Update a fact's fields."""
    updated = memory.update_fact(
        fact_id,
        content=body.content,
        tier=body.tier,
        importance=body.importance,
        tags=body.tags,
    )
    if not updated:
        return JSONResponse({"error": "Fact not found"}, status_code=404)
    fact = memory.get_fact(fact_id)
    return JSONResponse(fact)


@app.delete("/api/facts/{fact_id}")
async def delete_fact_endpoint(fact_id: int) -> JSONResponse:
    """Delete a fact by ID."""
    deleted = memory.delete_fact(fact_id)
    if not deleted:
        return JSONResponse({"error": "Fact not found"}, status_code=404)
    return JSONResponse({"success": True})


# Conversations REST endpoints
@app.get("/api/conversations")
async def list_conversations_endpoint() -> JSONResponse:
    """List recent conversation sessions with metadata."""
    conversations = memory.list_conversations(limit=20)
    return JSONResponse(conversations)


@app.get("/api/conversations/{session_id}")
async def get_conversation_endpoint(session_id: str) -> JSONResponse:
    """Get all turns for a conversation session."""
    turns = memory.get_session_turns(session_id, limit=100)
    if not turns:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse(turns)


@app.delete("/api/conversations/{session_id}")
async def delete_conversation_endpoint(session_id: str) -> JSONResponse:
    """Delete all turns for a conversation session."""
    count = memory.delete_conversation(session_id)
    if count == 0:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse({"deleted_turns": count})
