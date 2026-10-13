"""Asyncio timer tool that sends WebSocket messages."""
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket


async def set_timer_task(seconds: int, message: str, ws: "WebSocket") -> None:
    """
    Async task that waits for the specified duration, then sends a message to the WebSocket.

    Args:
        seconds: Duration to wait
        message: Message to send when timer fires
        ws: WebSocket connection to send the message to
    """
    try:
        await asyncio.sleep(seconds)
        await ws.send_json({
            "type": "timer",
            "message": message,
            "seconds_elapsed": seconds,
        })
    except Exception:
        pass  # WebSocket may be closed or disconnected


def set_timer(seconds: int, message: str) -> dict:
    """
    Set a timer that will fire and send a WebSocket message.

    Note: The actual async task must be created by the caller using set_timer_task.
    This function is a placeholder for the sync dispatch layer.

    Args:
        seconds: Duration in seconds
        message: Message to send when timer fires

    Returns:
        Confirmation dict
    """
    # Cap at reasonable limit (24 hours)
    seconds = min(max(seconds, 1), 86400)

    return {
        "ok": True,
        "message": message,
        "fires_in_seconds": seconds,
        "note": "Timer created; async task spawned by brain",
    }
