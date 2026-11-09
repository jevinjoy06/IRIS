"""Cross-device command execution dispatch.

``execute_remote`` is the single entry point for running a shell command on
a target device — the hub itself or a remote agent — gated by a destructive-
command confirmation handshake when needed.

Two different timeouts are in play, and they bound different things:
- ``CONFIRMATION_TIMEOUT_SECONDS`` bounds how long we wait for a human to
  approve/decline a destructive command (via ``pending_confirmations``).
- ``timeout`` (the parameter) bounds how long the command itself is allowed
  to run, whether locally (``shell.execute``) or on a remote agent.

A second, module-local future registry (``_pending_exec``) is used for the
remote-agent round trip: the agent replies with a result message that must
be routed back to the coroutine waiting on it. It is conceptually the same
pattern as ``pending_confirmations`` but a distinct namespace, since it
carries a different kind of payload (an execution result, not an
approve/decline boolean). Each entry stores the agent WebSocket the request
was dispatched to alongside the future, so a reply arriving on a *different*
connection (e.g. a stale/impersonating agent naming someone else's
request_id) cannot resolve it — only the connection the command was actually
sent to can.
"""

from __future__ import annotations

import asyncio
import uuid

from hub import devices
from hub import pending_confirmations
from hub.tools import shell

CONFIRMATION_TIMEOUT_SECONDS = 90

# Extra margin added on top of `timeout` when waiting for a remote agent's
# reply, to cover network/serialization overhead beyond the command's own
# execution time. A module-level constant (rather than a bare "+ 10") so
# tests can shrink it instead of waiting out a real multi-second timeout.
AGENT_DISPATCH_BUFFER_SECONDS = 10

_pending_exec: dict[str, tuple[asyncio.Future, object]] = {}


async def execute_remote(
    command: str,
    destructive: bool,
    target_device: str | None,
    origin_device_id: str | None,
    ws,
    timeout: int = 30,
) -> dict:
    """Dispatch ``command`` to ``target_device`` (or the origin device).

    Returns a result dict shaped like ``shell.execute``'s: at minimum an
    ``"ok"`` key, plus ``"error"`` on failure or ``"stdout"``/``"stderr"``/
    ``"returncode"`` on success.
    """
    # `timeout` already passed through registry.py's _coerce_timeout, so it's
    # guaranteed to be a real int, but not guaranteed to be in any sane range
    # (could be negative, zero, or huge). Clamp it so the hub-side wait
    # (asyncio.wait_for(..., timeout=timeout + 10) below) and the actual
    # execution duration (capped independently at 30s by shell.py's
    # execute() and by the laptop-client agent's own handler) agree.
    timeout = max(1, min(timeout, 30))

    target = target_device or origin_device_id
    if target is None:
        return {"ok": False, "error": "no target device specified and no origin device known"}

    if not devices.is_connected(target):
        return {"ok": False, "error": f"device '{target}' is not currently connected"}

    is_destructive = destructive or shell.is_destructive_pattern(command)

    if is_destructive:
        request_id = str(uuid.uuid4())
        future = pending_confirmations.create(request_id)
        try:
            await ws.send_json(
                {
                    "type": "confirm_required",
                    "request_id": request_id,
                    "command": command,
                    "target_device": target,
                }
            )
            approved = await asyncio.wait_for(future, timeout=CONFIRMATION_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "confirmation timed out — not executed"}
        except Exception as exc:
            return {"ok": False, "error": f"failed to request confirmation: {exc}"}
        finally:
            pending_confirmations.discard(request_id)

        if not approved:
            return {"ok": False, "error": "user declined — not executed"}

    if devices.is_hub_device(target):
        return await asyncio.get_running_loop().run_in_executor(None, shell.execute, command, timeout)

    agent_ws = devices.get_agent_ws(target)
    if agent_ws is None:
        return {"ok": False, "error": f"device '{target}' has no active agent connection"}

    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    _pending_exec[request_id] = (future, agent_ws)
    try:
        await agent_ws.send_json(
            {
                "type": "exec_command",
                "request_id": request_id,
                "command": command,
                "timeout": timeout,
            }
        )
        result = await asyncio.wait_for(future, timeout=timeout + AGENT_DISPATCH_BUFFER_SECONDS)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "device did not respond in time"}
    except Exception as exc:
        return {"ok": False, "error": f"failed to dispatch command to agent: {exc}"}
    finally:
        _pending_exec.pop(request_id, None)

    return result


def fail_pending_for_ws(ws) -> None:
    """Fail every pending exec request dispatched to ``ws`` immediately.

    Called when an agent's WebSocket disconnects: any command still waiting
    for a reply on that exact connection can never get one, so there is no
    reason to make the hub wait out the full timeout for it. Resolves each
    matching future (identity comparison on the stored agent ws) with an
    error result instead, unless it is already done.
    """
    for request_id, (future, agent_ws) in list(_pending_exec.items()):
        if agent_ws is ws:
            _pending_exec.pop(request_id, None)
            if not future.done():
                future.set_result({"ok": False, "error": "agent disconnected before replying"})


def resolve_exec_result(request_id: str, responding_ws, result: dict) -> bool:
    """Deliver ``result`` to the coroutine awaiting ``request_id``.

    Only resolves if ``responding_ws`` is the same connection the request
    was dispatched to — a reply naming someone else's ``request_id`` from a
    different connection is treated as not found, same as an unknown id, so
    the caller can't distinguish "wrong id" from "wrong connection" and the
    original waiter is left intact for its real agent to resolve later.

    Returns False if the id is unknown or the connection doesn't match;
    True otherwise. Same found/not-found semantics as
    ``pending_confirmations.resolve``.
    """
    entry = _pending_exec.get(request_id)
    if entry is None:
        return False
    future, agent_ws = entry
    if responding_ws is not agent_ws:
        return False
    _pending_exec.pop(request_id, None)
    if not future.done():
        future.set_result(result)
    return True
