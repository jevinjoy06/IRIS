"""In-memory registry of devices that can be targeted by cross-device commands.

Each device has up to two live connections:
- a chat session (the GUI/CLI the user talks to), and
- an agent connection (the background process that actually runs commands).

The hub itself is registered as an always-connected device with no WebSocket.
This module holds no persistent state; entries vanish when the process exits.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket


@dataclass
class DeviceEntry:
    device_id: str
    device_name: str | None = None
    chat_ws: WebSocket | None = None
    agent_ws: WebSocket | None = None
    is_hub: bool = False

    def is_live(self) -> bool:
        return self.is_hub or self.chat_ws is not None or self.agent_ws is not None


_devices: dict[str, DeviceEntry] = {}


def _get_or_create(device_id: str, device_name: str | None) -> DeviceEntry:
    entry = _devices.get(device_id)
    if entry is None:
        entry = DeviceEntry(device_id=device_id, device_name=device_name)
        _devices[device_id] = entry
    elif device_name is not None:
        entry.device_name = device_name
    return entry


def register_hub_self() -> str:
    """Register the hub's own machine as an always-connected device.

    The hub's device_id is reserved: any external connection that previously
    claimed the same hostname is dropped, so it cannot inherit hub capability.
    """
    device_id = socket.gethostname()
    device_name = os.environ.get("HUB_DEVICE_NAME", "hub")
    entry = _get_or_create(device_id, device_name)
    entry.chat_ws = None
    entry.agent_ws = None
    entry.is_hub = True
    return device_id


def get_hub_device_id() -> str | None:
    for entry in _devices.values():
        if entry.is_hub:
            return entry.device_id
    return None


def _is_external_device_id(device_id: str | None) -> bool:
    """False for empty ids and for the reserved hub id; True otherwise."""
    if not device_id:
        return False
    return device_id != get_hub_device_id()


def register_chat(device_id: str, device_name: str | None, ws: Any) -> None:
    if not _is_external_device_id(device_id):
        return
    _get_or_create(device_id, device_name).chat_ws = ws


def unregister_chat(ws: Any) -> None:
    for entry in _devices.values():
        if entry.chat_ws is ws:
            entry.chat_ws = None


def register_agent(device_id: str, device_name: str | None, ws: Any) -> None:
    if not _is_external_device_id(device_id):
        return
    _get_or_create(device_id, device_name).agent_ws = ws


def unregister_agent(ws: Any) -> None:
    for entry in _devices.values():
        if entry.agent_ws is ws:
            entry.agent_ws = None


def get_device_id_for_chat_ws(ws: Any) -> str | None:
    for entry in _devices.values():
        if entry.chat_ws is ws:
            return entry.device_id
    return None


def is_hub_device(device_id: str) -> bool:
    entry = _devices.get(device_id)
    return entry is not None and entry.is_hub


def get_agent_ws(device_id: str) -> Any:
    entry = _devices.get(device_id)
    return entry.agent_ws if entry is not None else None


def is_connected(device_id: str) -> bool:
    entry = _devices.get(device_id)
    return entry is not None and entry.is_live()


def list_connected() -> list[dict]:
    """Return every device with a live connection, flagged by whether it can execute."""
    return [
        {
            "device_id": entry.device_id,
            "device_name": entry.device_name,
            "can_execute": entry.is_hub or entry.agent_ws is not None,
        }
        for entry in _devices.values()
        if entry.is_live()
    ]


def reset_for_tests() -> None:
    """Clear all module state. Test-only."""
    _devices.clear()
