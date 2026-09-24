"""IRIS Hub — FastAPI + WebSocket server."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from hub import brain, memory

app = FastAPI(title="IRIS Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_STATIC = Path(__file__).parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_connected_clients: set[WebSocket] = set()


@app.on_event("startup")
async def startup() -> None:
    memory.init_db()


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
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "message":
                text = data.get("text", "").strip()
                if text:
                    await brain.process_turn(text, ws)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
    finally:
        _connected_clients.discard(ws)
