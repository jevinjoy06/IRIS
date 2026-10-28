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

from hub import brain, memory

_STATIC = Path(__file__).parent / "static"

# Session activity tracking: session_id -> {"ws": WebSocket, "turn_count": int, "last_message_at": datetime, "checkin_sent": bool, "tier2_sent": bool}
_active_sessions: dict = {}


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

    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception as e:
                # Malformed frame (bad JSON, wrong types, etc.) — report it and
                # keep listening instead of killing the whole session over one
                # bad message. A voice client hiccup shouldn't end the conversation.
                await ws.send_json({"type": "error", "text": f"Malformed message: {e}"})
                continue

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
        _connected_clients.discard(ws)
        _active_sessions.pop(session_id, None)


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
