"""IRIS Hub — FastAPI + WebSocket server."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from hub import brain, memory

app = FastAPI(title="IRIS Hub")

_STATIC = Path(__file__).parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.on_event("startup")
async def startup() -> None:
    memory.init_db()


@app.get("/")
async def index() -> HTMLResponse:
    html_path = _STATIC / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>IRIS Hub</h1><p>static/index.html not found.</p>")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
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
