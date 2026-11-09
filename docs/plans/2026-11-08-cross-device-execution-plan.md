# Cross-Device Command Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let IRIS execute arbitrary commands on whichever connected device (hub desktop, laptop, or any future device) the model decides makes sense for a request, with a confirmation gate on anything destructive.

**Architecture:** The hub gains a device registry (`hub/devices.py`) tracking every connected chat session and background "agent" connection by self-reported hostname. A new `execute_command` tool replaces `shell_run`; the hub dispatches it either in-process (when the target is the hub itself) or over a new `/ws/agent` WebSocket to a remote device's persistent background agent, and gates anything destructive behind a confirm/deny round-trip sent back to the chat session that asked. Each client (laptop) gains a lightweight always-on agent process independent of its chat GUI, plus device self-identification on its existing chat connection.

**Tech Stack:** Python (FastAPI/WebSocket, asyncio, pytest), existing Electron/React laptop client, existing `websockets` client library.

**Spec:** `docs/plans/2026-11-08-cross-device-execution-design.md`

## Global Constraints

- Transport is the existing FastAPI WebSocket stack — no new transport/protocol library.
- Trust boundary is Tailscale network membership; the hub must bind only to the Tailscale interface, not `0.0.0.0` (`HUB_HOST` default changes from `0.0.0.0` to `127.0.0.1`; remote access requires explicitly setting `HUB_HOST` to the Tailscale IP in `hub/.env`).
- `shell_run`'s bypassable blocklist and the destructive-request nudge (`docs/known-issues.md` #1 and #6) are retired by this work, not left running in parallel — `shell_run` is removed as a tool; its old hard-refuse pattern list becomes the heuristic that *upgrades* `execute_command`'s `destructive` flag, never a hard refusal.
- Destructive commands always pause for a yes/no from the user before running, on any target device; non-destructive commands run immediately.
- Device identity is self-reported hostname (+ optional friendly `device_name`), no server-side manual registry file.
- The hub is always an implicit, always-connected device (its own hostname) — targeting it never goes over the network.
- An offline named target returns a normal tool error, not a crash or silent no-op.

## Review Focus

- A chat client that never sends `register_device` (older client, or a message arriving before registration) — `execute_command` with no explicit `target_device` and no known origin must return a clear tool error, not throw or hang.
- A destructive command whose confirmation prompt is never answered (user ignores it, connection hiccups) — must time out and report "not executed," never execute by default and never hang the turn forever.
- A command the model marks `destructive: false` but which matches an obviously destructive pattern (e.g. `Remove-Item -Recurse -Force`, `rm -rf`) — the heuristic must still force confirmation.
- A `target_device` naming a device that is well-formed but not currently connected (typo, sleeping laptop, agent not started) — clean error, not a hang waiting on a dead connection.
- Two devices with the same self-reported hostname connecting at once (e.g. a test run), or a device's chat and agent connections arriving in either order — registry state must stay consistent either way, not throw on re-registration.

---

## Task 1: Harden the hub's network exposure

**Files:**
- Modify: `hub/__main__.py:10`
- Modify: `hub/.env.template` (add `HUB_HOST` documentation)
- Modify: `docs/known-issues.md` (mark item 7 resolved)
- Test: `tests/test_hub_main.py`

**Interfaces:**
- Produces: `HUB_HOST` env var now defaults to `"127.0.0.1"` (was `"0.0.0.0"`) wherever read in `hub/__main__.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hub_main.py
import os
import importlib

def test_hub_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("HUB_HOST", raising=False)
    import hub.__main__  # noqa: F401 side-effect import is wrong for a default check
```

Actually test the default directly against the literal in source rather than importing (importing `hub.__main__` calls `uvicorn.run` as a side effect at module scope and would hang). Write instead:

```python
# tests/test_hub_main.py
from pathlib import Path

def test_hub_host_default_is_loopback_not_wildcard():
    source = Path("hub/__main__.py").read_text()
    assert 'os.environ.get("HUB_HOST", "127.0.0.1")' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hub_main.py -v`
Expected: FAIL (source still says `"0.0.0.0"`)

- [ ] **Step 3: Change the default in `hub/__main__.py:10`**

`host = os.environ.get("HUB_HOST", "127.0.0.1")`

- [ ] **Step 4: Document it in `hub/.env.template`**

Add a line: `# HUB_HOST=100.x.x.x  # set to this machine's Tailscale IP to allow other devices to connect; defaults to 127.0.0.1 (local only)`

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_hub_main.py -v`
Expected: PASS

- [ ] **Step 6: Update `docs/known-issues.md` item 7**

Move it under "Resolved since this file was written" with one line noting the default changed to `127.0.0.1` and remote access now requires explicitly setting `HUB_HOST`.

- [ ] **Step 7: Commit**

```bash
git add hub/__main__.py hub/.env.template docs/known-issues.md tests/test_hub_main.py
git commit -m "fix(hub): default HUB_HOST to loopback, not 0.0.0.0"
```

---

## Task 2: Refactor `hub/tools/shell.py` into reusable execute + heuristic

**Files:**
- Modify: `hub/tools/shell.py`
- Modify: `tests/test_tools.py:14-60` (the `TestShell` class)

**Interfaces:**
- Produces: `shell.is_destructive_pattern(command: str) -> bool`, `shell.execute(command: str, timeout: int = 30) -> dict` (same return shape as the old `run_command`: `{"ok": bool, "stdout": str, "stderr": str, "returncode": int}` on success, `{"ok": False, "error": str, "stdout": "", "stderr": "", "returncode": -1}` on failure/timeout). `run_command` is removed — nothing outside this module and its tests calls it (confirmed via grep).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests** (replacing the old `TestShell` class in `tests/test_tools.py`)

```python
class TestShell:
    def test_execute_simple_command_success(self):
        from hub.tools import shell
        result = shell.execute("echo hello")
        assert result["ok"] is True
        assert "hello" in result["stdout"]
        assert result["returncode"] == 0

    def test_execute_nonzero_returncode(self):
        from hub.tools import shell
        result = shell.execute("cmd /c exit 1")
        assert result["ok"] is True
        assert result["returncode"] == 1

    def test_execute_timeout(self):
        from hub.tools import shell
        result = shell.execute("ping -n 10 127.0.0.1", timeout=1)
        assert result["ok"] is False
        assert "timed out" in result["error"].lower()

    def test_is_destructive_pattern_rm_rf(self):
        from hub.tools import shell
        assert shell.is_destructive_pattern("rm -rf /tmp") is True

    def test_is_destructive_pattern_format(self):
        from hub.tools import shell
        assert shell.is_destructive_pattern("format c:") is True

    def test_is_destructive_pattern_del_fsfq(self):
        from hub.tools import shell
        assert shell.is_destructive_pattern("del /f /s /q C:") is True

    def test_is_destructive_pattern_safe_command(self):
        from hub.tools import shell
        assert shell.is_destructive_pattern("echo hello") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py::TestShell -v`
Expected: FAIL (`shell.execute` / `shell.is_destructive_pattern` don't exist yet)

- [ ] **Step 3: Implement in `hub/tools/shell.py`**

Keep the existing 6-pattern list (`rm -rf`, `format `, `del /f /s /q C:`, `mkfs`, `dd if=`, `shred `) as a module-level `DANGEROUS_PATTERNS` list. `is_destructive_pattern` checks the lowercased command against each pattern with `re.search`, returns `True` on any match. `execute` is `run_command`'s old body minus the pattern-check block (no hard refusal — that call is deleted, callers that need the refusal call `is_destructive_pattern` themselves). Delete `run_command`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py::TestShell -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/tools/shell.py tests/test_tools.py
git commit -m "refactor(hub): split shell.run_command into execute() + is_destructive_pattern()"
```

---

## Task 3: Device registry (`hub/devices.py`)

**Files:**
- Create: `hub/devices.py`
- Test: `tests/test_devices.py`

**Interfaces:**
- Produces:
  - `register_hub_self() -> str` — registers the hub's own hostname as an always-connected, `is_hub=True` device; returns the device_id used.
  - `get_hub_device_id() -> str | None`
  - `register_chat(device_id: str, device_name: str | None, ws) -> None`
  - `unregister_chat(ws) -> None`
  - `register_agent(device_id: str, device_name: str | None, ws) -> None`
  - `unregister_agent(ws) -> None`
  - `get_device_id_for_chat_ws(ws) -> str | None`
  - `is_hub_device(device_id: str) -> bool`
  - `get_agent_ws(device_id: str)` — returns the agent's WebSocket or `None`
  - `is_connected(device_id: str) -> bool`
  - `list_connected() -> list[dict]` — each item `{"device_id": str, "device_name": str | None, "can_execute": bool}`; `can_execute` is `True` when the device is the hub or has a live agent connection, `False` for a device only reachable as a chat session (no agent running yet).
  - `reset_for_tests() -> None` — clears all module state; test-only helper so tests don't leak device entries into each other.
- Consumes: nothing (pure in-memory module, no imports from the rest of `hub/` beyond `WebSocket` for typing under `TYPE_CHECKING`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_devices.py
import pytest
from hub import devices

@pytest.fixture(autouse=True)
def _reset():
    devices.reset_for_tests()
    yield
    devices.reset_for_tests()

def test_register_hub_self_is_always_connected():
    device_id = devices.register_hub_self()
    assert devices.is_hub_device(device_id) is True
    assert devices.is_connected(device_id) is True

def test_register_chat_then_lookup_by_ws():
    ws = object()
    devices.register_chat("laptop-host", "laptop", ws)
    assert devices.get_device_id_for_chat_ws(ws) == "laptop-host"

def test_unregister_chat_clears_lookup():
    ws = object()
    devices.register_chat("laptop-host", "laptop", ws)
    devices.unregister_chat(ws)
    assert devices.get_device_id_for_chat_ws(ws) is None

def test_register_agent_then_get_agent_ws():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    assert devices.get_agent_ws("laptop-host") is ws

def test_unregister_agent_clears_ws():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    devices.unregister_agent(ws)
    assert devices.get_agent_ws("laptop-host") is None

def test_chat_only_device_is_connected_but_cannot_execute():
    devices.register_chat("laptop-host", "laptop", object())
    assert devices.is_connected("laptop-host") is True
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries["laptop-host"]["can_execute"] is False

def test_agent_device_can_execute():
    devices.register_agent("laptop-host", "laptop", object())
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries["laptop-host"]["can_execute"] is True

def test_unknown_device_is_not_connected():
    assert devices.is_connected("nonexistent-host") is False

def test_chat_and_agent_same_device_share_one_entry():
    devices.register_agent("laptop-host", "laptop", object())
    devices.register_chat("laptop-host", "laptop", object())
    assert len(devices.list_connected()) == 1

def test_reregistering_same_ws_does_not_duplicate():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    devices.register_agent("laptop-host", "laptop", ws)
    assert len(devices.list_connected()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_devices.py -v`
Expected: FAIL (`hub.devices` doesn't exist)

- [ ] **Step 3: Implement `hub/devices.py`**

A module-level `dict[str, DeviceEntry]` keyed by device_id, where `DeviceEntry` is a small dataclass with `device_id`, `device_name`, `chat_ws`, `agent_ws`, `is_hub`. `register_hub_self` uses `socket.gethostname()` for the id and `os.environ.get("HUB_DEVICE_NAME", "hub")` for the name. `register_chat`/`register_agent` create the entry if it doesn't exist (matching on device_id) and set/overwrite the relevant `*_ws` field and `device_name` if one was given. `unregister_chat`/`unregister_agent` scan entries for a matching `ws` identity and clear that field — don't delete the entry itself (the other role's connection, or the hub flag, may still be live).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_devices.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/devices.py tests/test_devices.py
git commit -m "feat(hub): add device registry for cross-device targeting"
```

---

## Task 4: Confirmation futures (`hub/pending_confirmations.py`)

**Files:**
- Create: `hub/pending_confirmations.py`
- Test: `tests/test_pending_confirmations.py`

**Interfaces:**
- Produces: `create(request_id: str) -> asyncio.Future`, `resolve(request_id: str, approved: bool) -> bool` (returns `False` if `request_id` is unknown — e.g. already resolved or timed out and discarded — `True` otherwise), `discard(request_id: str) -> None`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pending_confirmations.py
import asyncio
import pytest
from hub import pending_confirmations as pc

@pytest.mark.asyncio
async def test_create_then_resolve_sets_future_result():
    future = pc.create("req-1")
    assert pc.resolve("req-1", True) is True
    assert await future is True

@pytest.mark.asyncio
async def test_resolve_unknown_request_id_returns_false():
    assert pc.resolve("nonexistent", True) is False

@pytest.mark.asyncio
async def test_discard_removes_pending_entry():
    pc.create("req-2")
    pc.discard("req-2")
    assert pc.resolve("req-2", True) is False

@pytest.mark.asyncio
async def test_resolve_false_propagates():
    future = pc.create("req-3")
    pc.resolve("req-3", False)
    assert await future is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pending_confirmations.py -v`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement `hub/pending_confirmations.py`**

A module-level `dict[str, asyncio.Future]`. `create` makes a `loop.create_future()`, stores it, returns it. `resolve` looks up and pops the future, calls `.set_result(approved)` if found and not already done, returns whether it was found. `discard` pops without resolving (used on timeout so a late client reply doesn't try to resolve a future no one awaits anymore).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pending_confirmations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/pending_confirmations.py tests/test_pending_confirmations.py
git commit -m "feat(hub): add confirmation future registry for destructive actions"
```

---

## Task 5: Remote execution dispatch (`hub/tools/remote_exec.py`)

**Files:**
- Create: `hub/tools/remote_exec.py`
- Test: `tests/test_remote_exec.py`

**Interfaces:**
- Consumes: `hub.devices.{is_connected, is_hub_device, get_agent_ws}`, `hub.pending_confirmations.{create, resolve, discard}`, `hub.tools.shell.{execute, is_destructive_pattern}`.
- Produces: `async def execute_remote(command: str, destructive: bool, target_device: str | None, origin_device_id: str | None, ws, timeout: int = 30) -> dict`, `resolve_exec_result(request_id: str, result: dict) -> bool` (same found/not-found semantics as `pending_confirmations.resolve`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_remote_exec.py
import asyncio
import pytest
from unittest.mock import AsyncMock
from hub import devices
from hub.tools import remote_exec

@pytest.fixture(autouse=True)
def _reset():
    devices.reset_for_tests()
    yield
    devices.reset_for_tests()

@pytest.mark.asyncio
async def test_no_target_and_no_origin_returns_error():
    result = await remote_exec.execute_remote("echo hi", False, None, None, AsyncMock())
    assert result["ok"] is False
    assert "device" in result["error"].lower()

@pytest.mark.asyncio
async def test_unconnected_target_returns_error():
    result = await remote_exec.execute_remote("echo hi", False, "nonexistent-host", None, AsyncMock())
    assert result["ok"] is False
    assert "not currently connected" in result["error"]

@pytest.mark.asyncio
async def test_non_destructive_on_hub_runs_immediately_no_confirmation():
    hub_id = devices.register_hub_self()
    origin_ws = AsyncMock()
    result = await remote_exec.execute_remote("echo hi", False, None, hub_id, origin_ws)
    assert result["ok"] is True
    assert "hi" in result["stdout"]
    origin_ws.send_json.assert_not_called()

@pytest.mark.asyncio
async def test_declared_destructive_sends_confirm_required_and_waits():
    hub_id = devices.register_hub_self()
    origin_ws = AsyncMock()

    async def approve_after_send(*args, **kwargs):
        # Simulate the client approving shortly after confirm_required is sent.
        request_id = origin_ws.send_json.call_args[0][0]["request_id"]
        asyncio.get_event_loop().call_soon(
            lambda: __import__("hub.pending_confirmations", fromlist=["resolve"]).resolve(request_id, True)
        )

    origin_ws.send_json.side_effect = approve_after_send
    result = await remote_exec.execute_remote("echo hi", True, None, hub_id, origin_ws)
    assert result["ok"] is True
    sent = origin_ws.send_json.call_args[0][0]
    assert sent["type"] == "confirm_required"

@pytest.mark.asyncio
async def test_declined_confirmation_does_not_execute():
    hub_id = devices.register_hub_self()
    origin_ws = AsyncMock()

    async def decline_after_send(*args, **kwargs):
        request_id = origin_ws.send_json.call_args[0][0]["request_id"]
        from hub import pending_confirmations
        pending_confirmations.resolve(request_id, False)

    origin_ws.send_json.side_effect = decline_after_send
    result = await remote_exec.execute_remote("echo hi", True, None, hub_id, origin_ws)
    assert result["ok"] is False
    assert "declined" in result["error"].lower()

@pytest.mark.asyncio
async def test_heuristic_upgrades_undeclared_destructive_command(monkeypatch):
    # The confirmation wait uses CONFIRMATION_TIMEOUT_SECONDS (production: 90s),
    # not the `timeout` argument (that one bounds command *execution*, not the
    # confirmation wait) — shrink it so this test doesn't take 90 real seconds.
    monkeypatch.setattr(remote_exec, "CONFIRMATION_TIMEOUT_SECONDS", 0.1)
    hub_id = devices.register_hub_self()
    origin_ws = AsyncMock()
    origin_ws.send_json.side_effect = lambda *a, **k: None  # never resolves -> times out
    result = await remote_exec.execute_remote("rm -rf /tmp", False, None, hub_id, origin_ws)
    # Should have gone through the confirm path (and timed out, since nothing resolves it)
    assert origin_ws.send_json.called
    assert result["ok"] is False

@pytest.mark.asyncio
async def test_remote_agent_dispatch_round_trip():
    devices.register_hub_self()
    agent_ws = AsyncMock()

    async def reply_with_result(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        remote_exec.resolve_exec_result(request_id, {"ok": True, "stdout": "remote output", "stderr": "", "returncode": 0})

    agent_ws.send_json.side_effect = reply_with_result
    devices.register_agent("laptop-host", "laptop", agent_ws)

    result = await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock())
    assert result["ok"] is True
    assert result["stdout"] == "remote output"

@pytest.mark.asyncio
async def test_agent_device_with_no_agent_ws_errors():
    # A device known only as a chat session (no agent running) can't execute.
    devices.register_chat("laptop-host", "laptop", AsyncMock())
    result = await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock())
    assert result["ok"] is False
```

Note: the `call_soon`-based approval test is awkward by nature of testing a cross-task future resolution — if it proves flaky, replace with a direct `asyncio.create_task` that calls `pending_confirmations.resolve(...)` after `await asyncio.sleep(0)`, started before awaiting `execute_remote`. Either approach is fine; the behavior under test is "confirm_required is sent, and resolving the matching request_id unblocks execution."

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_remote_exec.py -v`
Expected: FAIL (`hub.tools.remote_exec` doesn't exist)

- [ ] **Step 3: Implement `hub/tools/remote_exec.py`**

`execute_remote`'s control flow:
1. `target = target_device or origin_device_id`; if still `None`, return `{"ok": False, "error": "no target device specified and no origin device known"}`.
2. If `not devices.is_connected(target)`, return `{"ok": False, "error": f"device '{target}' is not currently connected"}`.
3. `is_destructive = destructive or shell.is_destructive_pattern(command)`.
4. If `is_destructive`: generate a `uuid.uuid4()` request id, `future = pending_confirmations.create(request_id)`, `await ws.send_json({"type": "confirm_required", "request_id": request_id, "command": command, "target_device": target})`, then `try: approved = await asyncio.wait_for(future, timeout=CONFIRMATION_TIMEOUT_SECONDS) except asyncio.TimeoutError: pending_confirmations.discard(request_id); return {"ok": False, "error": "confirmation timed out — not executed"}`. If not approved, return `{"ok": False, "error": "user declined — not executed"}`. `CONFIRMATION_TIMEOUT_SECONDS = 90` is a module-level constant (not the `timeout` parameter, which bounds command *execution*, not the confirmation wait) — tests that need the confirmation wait to time out should `monkeypatch.setattr(remote_exec, "CONFIRMATION_TIMEOUT_SECONDS", <small value>)` rather than waiting out the real 90s.
5. If `devices.is_hub_device(target)`: run locally via `await asyncio.get_running_loop().run_in_executor(None, shell.execute, command, timeout)`.
6. Else: `agent_ws = devices.get_agent_ws(target)`; if `None`, return `{"ok": False, "error": f"device '{target}' has no active agent connection"}`; generate a second request id, register it the same way `_pending_exec` does (a module-level `dict[str, asyncio.Future]`, mirroring `pending_confirmations`'s pattern but local to this module since it's a different kind of reply), `await agent_ws.send_json({"type": "exec_command", "request_id": request_id, "command": command, "timeout": timeout})`, `try: result = await asyncio.wait_for(future, timeout=timeout + 10) except asyncio.TimeoutError: return {"ok": False, "error": "device did not respond in time"}`.
7. Return the result dict.

`resolve_exec_result(request_id, result)` pops the matching future from `_pending_exec` and sets its result to `result`, returning whether one was found (same shape as `pending_confirmations.resolve`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_remote_exec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/tools/remote_exec.py tests/test_remote_exec.py
git commit -m "feat(hub): add execute_remote dispatch with destructive confirmation gate"
```

---

## Task 6: Wire `execute_command` into the tool registry, retire `shell_run`

**Files:**
- Modify: `hub/tools/registry.py`
- Test: `tests/test_tools.py` (new `TestRegistry` additions)

**Interfaces:**
- Consumes: `hub.tools.remote_exec.execute_remote`, `hub.devices.list_connected`.
- Produces: `async_dispatch(tool_name: str, tool_input: dict, ws, origin_device_id: str | None = None) -> str` — signature gains the new trailing keyword argument (default `None` so every other existing call site keeps working unmodified); `dispatch()` (the sync one) is untouched — `execute_command` is async-only since it may await a confirmation/network round-trip, so it's dispatched only through `async_dispatch`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tools.py — add to the file
class TestRegistry:
    @pytest.mark.asyncio
    async def test_execute_command_dispatches_to_remote_exec(self, monkeypatch):
        from hub.tools import registry
        captured = {}

        async def fake_execute_remote(command, destructive, target_device, origin_device_id, ws, timeout=30):
            captured.update(locals())
            return {"ok": True, "stdout": "ran", "stderr": "", "returncode": 0}

        monkeypatch.setattr(registry, "execute_remote", fake_execute_remote)
        result_json = await registry.async_dispatch(
            "execute_command",
            {"command": "echo hi", "destructive": False, "target_device": "laptop-host"},
            AsyncMock(),
            origin_device_id="desktop-host",
        )
        result = json.loads(result_json)
        assert result["ok"] is True
        assert captured["command"] == "echo hi"
        assert captured["target_device"] == "laptop-host"
        assert captured["origin_device_id"] == "desktop-host"

    def test_shell_run_tool_definition_removed(self):
        from hub.tools.registry import TOOL_DEFINITIONS
        names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        assert "shell_run" not in names
        assert "execute_command" in names
```

(`AsyncMock` and `json` are already imported at the top of `tests/test_tools.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py::TestRegistry -v`
Expected: FAIL (`execute_command` tool/dispatch doesn't exist, `shell_run` still present)

- [ ] **Step 3: Implement in `hub/tools/registry.py`**

- Import `from hub.tools.remote_exec import execute_remote` and `from hub import devices` at module level.
- Remove the `shell_run` entry from `TOOL_DEFINITIONS` (lines 67-74) and its `dispatch()` case (lines 152-156); remove the now-unused `shell` import from the `from hub.tools import ...` line if nothing else in the module uses it.
- Add a new `TOOL_DEFINITIONS` entry for `execute_command`: `command` (string, required), `destructive` (boolean, required — description must tell the model it MUST be `true` for anything deleting/overwriting/killing/formatting/otherwise irreversible, and that the user will be asked to confirm when it's true), `target_device` (string, optional — description: "Exact device_id from the Connected devices list. Omit to target the device this request came from."), `timeout` (integer, optional, default 30, max 30).
- In `async_dispatch`, add `origin_device_id: str | None = None` as the new trailing parameter, and a branch: `if tool_name == "execute_command": result = await execute_remote(tool_input["command"], tool_input.get("destructive", False), tool_input.get("target_device"), origin_device_id, ws, tool_input.get("timeout", 30))` before falling through to the existing `else: result_json = dispatch(...)` path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py -v`
Expected: PASS (including the pre-existing tests, which must still pass unchanged)

- [ ] **Step 5: Commit**

```bash
git add hub/tools/registry.py tests/test_tools.py
git commit -m "feat(hub): replace shell_run tool with device-aware execute_command"
```

---

## Task 7: Hub WebSocket changes — agent endpoint, device registration, confirmation side-channel

**Files:**
- Modify: `hub/server.py`
- Test: `tests/test_server.py` (new `TestDeviceWebSockets` class)

**Interfaces:**
- Consumes: `hub.devices.*`, `hub.pending_confirmations.resolve`, `hub.tools.remote_exec.resolve_exec_result`.
- Produces: new route `@app.websocket("/ws/agent")`; `/ws` now accepts an optional `{"type": "register_device", "device_id": ..., "device_name": ...}` message and a `{"type": "confirm_response", "request_id": ..., "approved": ...}` message, in addition to its existing `{"type": "message", ...}` handling.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py — add to the file
from unittest.mock import AsyncMock, patch
from hub import devices, pending_confirmations

class TestDeviceWebSockets:
    def setup_method(self):
        devices.reset_for_tests()

    def teardown_method(self):
        devices.reset_for_tests()

    def test_agent_register_adds_device(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            ws.send_json({"type": "exec_result", "request_id": "doesnt-matter", "ok": True})
            # give the server a moment to process; assert via registry state below

        connected = {d["device_id"]: d for d in devices.list_connected()}
        assert "laptop-host" not in connected  # disconnected on exit

    def test_agent_register_then_connected_while_open(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            import time; time.sleep(0.1)
            connected = {d["device_id"]: d for d in devices.list_connected()}
            assert connected["laptop-host"]["can_execute"] is True

    def test_agent_exec_result_resolves_pending_future(self, client, temp_db):
        from hub.tools import remote_exec
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            # Register a pending future the way execute_remote would, then
            # simulate the agent replying to it.
            import asyncio
            future = asyncio.get_event_loop().run_until_complete(_noop())  # placeholder to keep sync test structure
            # Simpler: directly check resolve_exec_result's return value via a real pending entry.
            ws.send_json({"type": "exec_result", "request_id": "req-xyz", "ok": True, "stdout": "done"})
            # No pending future registered -> resolve_exec_result returns False, nothing to assert on
            # the socket side; this test exists to prove the server doesn't crash on an unmatched reply.

    def test_chat_register_device_sets_origin(self, client, temp_db):
        with patch("hub.server.brain.process_turn", new_callable=AsyncMock, return_value=False) as mock_turn:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "register_device", "device_id": "desktop-host", "device_name": "desktop"})
                ws.send_json({"type": "message", "text": "hello"})
                ws.receive_json()  # don't block forever if process_turn's mock sends nothing; see note below

            assert mock_turn.called
            _, kwargs = mock_turn.call_args
            assert kwargs["origin_device_id"] == "desktop-host"

    def test_confirm_response_resolves_future_not_process_turn(self, client, temp_db):
        with patch("hub.server.brain.process_turn", new_callable=AsyncMock, return_value=False) as mock_turn:
            future = pending_confirmations.create("req-abc")
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "confirm_response", "request_id": "req-abc", "approved": True})
                import time; time.sleep(0.1)

            assert mock_turn.called is False


async def _noop():
    return None
```

These WebSocket tests are the trickiest in the plan because `TestClient.websocket_connect` runs the server in a background thread. The `test_chat_register_device_sets_origin` test may need `mock_turn` to also send a `done` message so the client-side `with` block's implicit drain doesn't hang — if `process_turn` is mocked to just `return False` with no side effect, no messages are ever sent back, and `ws.receive_json()` will block. Make the mock's side effect send one token and a done, e.g. set `mock_turn.side_effect` to an async function that calls `await args[1].send_json({"type": "done"})` using the `ws` passed into `process_turn`, then `ws.receive_json()` has something to read. Adjust the test to do this rather than leaving a bare `receive_json()` call that can hang the suite.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py::TestDeviceWebSockets -v`
Expected: FAIL (`/ws/agent` doesn't exist, `/ws` doesn't understand `register_device`/`confirm_response`, `process_turn` isn't called with `origin_device_id`)

- [ ] **Step 3: Implement in `hub/server.py`**

- Add `from hub import devices, pending_confirmations` and `from hub.tools import remote_exec` to the imports.
- In `lifespan`, after `memory.init_db()`, call `devices.register_hub_self()`.
- Add the new route:

```python
@app.websocket("/ws/agent")
async def agent_websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break
            msg_type = data.get("type")
            if msg_type == "register":
                devices.register_agent(data.get("device_id"), data.get("device_name"), ws)
            elif msg_type == "exec_result":
                remote_exec.resolve_exec_result(data.get("request_id"), ws, data)
    finally:
        devices.unregister_agent(ws)
```

**Signature note (updated during Task 5's review):** `resolve_exec_result` is `resolve_exec_result(request_id: str, responding_ws, result: dict) -> bool`, not `(request_id, result)` as originally drafted — it now verifies the reply arrived on the same agent connection the hub actually dispatched to, per a security-review finding addressed during Task 5. Call it with the `ws` this handler is already holding, as shown above.

- Restructure `websocket_endpoint` (the existing `/ws` handler) to decouple receiving from turn-processing, so a `confirm_response` arriving while `process_turn` is mid-flight (awaiting a confirmation future inside `execute_remote`) doesn't deadlock behind the single `await ws.receive_json()` call the turn loop is blocked on today. Introduce an `asyncio.Queue()` and a background `reader()` task for the duration of the connection: `reader()` loops on `ws.receive_json()` (preserving the existing malformed-frame try/except that sends back `{"type": "error", ...}` and continues); on `WebSocketDisconnect` it puts a `{"type": "__disconnect__"}` sentinel on the queue and returns; on `register_device` it calls `devices.register_chat(...)` and does not forward to the queue; on `confirm_response` it calls `pending_confirmations.resolve(data.get("request_id"), bool(data.get("approved")))` and does not forward to the queue; everything else is forwarded to the queue unchanged. The existing `while True:` body that currently does `data = await ws.receive_json()` instead does `data = await inbound_queue.get()`, and its first line becomes `if data.get("type") == "__disconnect__": raise WebSocketDisconnect()` before the existing `if data.get("type") == "message":` branch. Start the reader task right after `_active_sessions[session_id] = {...}` with `reader_task = asyncio.create_task(reader())`, and cancel it in the existing `finally:` block alongside the current cleanup. That `finally:` block must also call `devices.unregister_chat(ws)` (alongside the existing `_connected_clients.discard(ws)` and `_active_sessions.pop(...)`) — without it, a disconnected chat session's device entry never clears its `chat_ws`, so `get_device_id_for_chat_ws` and `list_connected()`'s online status would keep reporting a closed connection as live. Add one test for this: connect, send `register_device`, close the connection (exit the `with client.websocket_connect(...) as ws:` block), then assert `devices.get_device_id_for_chat_ws` style state is actually cleared — e.g. assert the device_id no longer appears with a live chat connection in `devices.list_connected()` (it may still appear if it also has an agent connection; register only a chat connection in this test so a cleared entry means it drops out entirely, matching the pattern already used in `test_agent_register_adds_device`).
- Thread origin device id through: where the existing code calls `await brain.process_turn(text, ws, session_id=session_id, turn_number=turn_count)`, add `origin_device_id=devices.get_device_id_for_chat_ws(ws)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: PASS (including every pre-existing test in the file)

- [ ] **Step 5: Commit**

```bash
git add hub/server.py tests/test_server.py
git commit -m "feat(hub): add /ws/agent endpoint and device registration/confirmation on /ws"
```

---

## Task 8: Brain — thread origin device id, inject device list, update system prompt

**Files:**
- Modify: `hub/brain.py:23-56` (SYSTEM_PROMPT), `hub/brain.py:156-161` (`process_turn` signature), `hub/brain.py:193-216` and `hub/brain.py:339-367` (the two `async_dispatch` call sites)
- Test: `tests/test_brain.py` (new file, or extend if one already covers `process_turn`)

**Interfaces:**
- Consumes: `hub.devices.list_connected`.
- Produces: `process_turn(user_text: str, ws, session_id: str | None = None, turn_number: int = 1, origin_device_id: str | None = None) -> bool` — new trailing keyword argument, default `None` so existing callers (there's only the one in `hub/server.py`, already updated in Task 7) keep working.

- [ ] **Step 1: Write the failing test**

Check first whether `tests/test_brain.py` already exists; if not, create it following the mocking style already used in `tests/test_tools.py` (`AsyncMock` for the Ollama client stream).

```python
# tests/test_brain.py
import pytest
from unittest.mock import AsyncMock, patch
from hub import brain, devices

@pytest.fixture(autouse=True)
def _reset_devices():
    devices.reset_for_tests()
    yield
    devices.reset_for_tests()

@pytest.mark.asyncio
async def test_process_turn_passes_origin_device_id_to_async_dispatch(monkeypatch, temp_db):
    devices.register_agent("laptop-host", "laptop", AsyncMock())
    captured = {}

    async def fake_async_dispatch(tool_name, tool_input, ws, origin_device_id=None):
        captured["origin_device_id"] = origin_device_id
        return '{"ok": true}'

    monkeypatch.setattr(brain, "async_dispatch", fake_async_dispatch)
    # Force the deterministic-tool pre-seed path, which is the simplest way to
    # exercise async_dispatch without mocking the full streaming chat client —
    # pick whatever is in _DETERMINISTIC_TOOLS and craft user_text that triggers it.
    ...
```

Note for the implementer: the deterministic-tools pre-seed path (lines 190-217) is the cheapest way to exercise `async_dispatch` in a unit test without standing up a fake streaming Ollama client — check `_DETERMINISTIC_TOOLS`'s keys and `_tool_choice_for`'s matching logic (both already in `hub/brain.py`) to craft `user_text` that forces that path, then assert `captured["origin_device_id"] == "laptop-host"`. If that path doesn't exercise it cleanly, mock `_get_client()` to return an object whose `.chat.completions.create` is an `AsyncMock` yielding a minimal fake stream with one tool-call chunk and a `finish_reason="tool_calls"` chunk, matching the shape the main loop (lines 293-316) expects.

```python
@pytest.mark.asyncio
async def test_system_prompt_lists_connected_devices(monkeypatch, temp_db):
    devices.register_hub_self()
    devices.register_agent("laptop-host", "laptop", AsyncMock())
    # Assert the device list appears somewhere reachable from process_turn's
    # constructed system message — exact assertion depends on how Step 3 below
    # exposes it (e.g. a standalone `_device_context()` helper is easiest to
    # unit test directly rather than asserting against the full message list).
    from hub.brain import _device_context
    ctx = _device_context()
    assert "laptop-host" in ctx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain.py -v`
Expected: FAIL

- [ ] **Step 3: Implement in `hub/brain.py`**

- Add `origin_device_id: str | None = None` to `process_turn`'s signature.
- Add a small helper `_device_context() -> str` that calls `devices.list_connected()` and formats it as a short block, e.g.:
  ```
  ## Connected devices
  - laptop-host ("laptop") — can execute commands
  - desktop-host ("hub", this machine) — can execute commands
  Use the exact device_id as target_device for execute_command. Omit target_device to use the device this request came from.
  ```
  Return an empty string if `list_connected()` is empty (shouldn't happen once the hub self-registers, but keep it defensive).
- In the system message construction (line 244), append `_device_context()` the same way `mem_context` and `resume_note` are appended.
- Update `SYSTEM_PROMPT`'s tool list (lines 25-36): remove the `shell_run` line, add `execute_command — boss asks you to run a command/script on a device, or to open/launch/control something no structured tool covers; ALWAYS set destructive=true for anything that deletes, overwrites, kills, or formats`.
- At both `async_dispatch(...)` call sites (the deterministic pre-seed one and the main tool-loop one), add `origin_device_id=origin_device_id` as a keyword argument.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/brain.py tests/test_brain.py
git commit -m "feat(hub): inject connected-device list into system prompt, thread origin device id"
```

---

## Task 9: Laptop chat client reports device identity + renders confirmation prompt

**Files:**
- Modify: `clients/laptop/electron/preload.js`
- Modify: `clients/laptop/config.json.template`
- Modify: `clients/laptop/src/App.jsx`

**Interfaces:**
- Produces: `window.irisConfig.hostname` (new field, alongside the existing `hubUrl`), `window.irisConfig.deviceName` (from `config.json`'s new `device_name` field, `null` if unset).
- Consumes: the hub's `register_device` / `confirm_required` / `confirm_response` message shapes from Task 7.

No automated test harness exists for this Electron client yet (confirmed — only `tests/` at the repo root, covering `hub/` and `voice/`, nothing under `clients/`). Verify these steps by running the app, per the steps below, rather than writing new test infrastructure from scratch for this one change.

- [ ] **Step 1: Add `hostname` to `preload.js`'s exposed config**

```js
const os = require('os')
contextBridge.exposeInMainWorld('irisConfig', {
  hubUrl: config.hub_url || 'ws://localhost:7865/ws',
  hostname: os.hostname(),
  deviceName: config.device_name || null,
})
```

- [ ] **Step 2: Add `device_name` to `config.json.template`**

```json
{
  "_comment": "Copy to config.json — gitignored. Defaults to localhost for running on the same machine as the hub. For a remote device, set hub_url to the hub machine's Tailscale IP (e.g. ws://100.98.135.70:7865/ws) or LAN IP. device_name is an optional friendly label other devices can target you by (e.g. \"laptop\") — defaults to this machine's hostname if left out.",
  "hub_url": "ws://localhost:7865/ws",
  "device_name": "laptop"
}
```

- [ ] **Step 3: Send `register_device` right after the WebSocket opens in `App.jsx`**

Find the existing `ws.onopen` (or equivalent connect handler) around the `new WebSocket(hubUrl)` call at `App.jsx:61`, and send immediately after open:

```js
ws.send(JSON.stringify({
  type: 'register_device',
  device_id: window.irisConfig?.hostname,
  device_name: window.irisConfig?.deviceName,
}))
```

- [ ] **Step 4: Handle `confirm_required` and render a yes/no prompt**

In the existing `ws.onmessage` switch/if-chain, add a case for `type === 'confirm_required'` that stores `{requestId, command, targetDevice}` in a new piece of state (e.g. `pendingConfirmation`). Render a small inline prompt when that state is non-null — reuse the existing transient-response area's styling rather than introducing a new component family — showing the command and target device, with Approve/Decline buttons that each send `{"type": "confirm_response", "request_id": pendingConfirmation.requestId, "approved": true|false}` and then clear `pendingConfirmation`.

- [ ] **Step 5: Manually verify**

Run: `npm run dev` in `clients/laptop/`
Expected: app connects, no console errors about `irisConfig` being undefined; `window.irisConfig.hostname` and `.deviceName` are defined when checked in DevTools console.

- [ ] **Step 6: Commit**

```bash
git add clients/laptop/electron/preload.js clients/laptop/config.json.template clients/laptop/src/App.jsx
git commit -m "feat(laptop-client): report device identity, render destructive-action confirmation prompt"
```

---

## Task 10: Laptop CLI client reports device identity

**Files:**
- Modify: `clients/laptop/main.py:38-66` (`run_text`)

**Interfaces:**
- Consumes: `config.get("device_name")`, `socket.gethostname()`.

- [ ] **Step 1: Add the import and send the registration message**

At the top of `clients/laptop/main.py`, add `import socket`. In `run_text`, right after `async with websockets.connect(hub_url) as ws:` and before the `print("Connected...")` line, add:

```python
await ws.send(json.dumps({
    "type": "register_device",
    "device_id": socket.gethostname(),
    "device_name": config.get("device_name"),
}))
```

- [ ] **Step 2: Manually verify**

Run: `python clients/laptop/main.py` against a running hub.
Expected: connects and behaves exactly as before (no visible change — this message has no reply, it's fire-and-forget registration).

- [ ] **Step 3: Commit**

```bash
git add clients/laptop/main.py
git commit -m "feat(laptop-client): CLI reports device identity on connect"
```

---

## Task 11: Background device agent

**Files:**
- Create: `clients/laptop/agent.py`
- Modify: `README.md` (add a short "Background agent" section)

**Interfaces:**
- Consumes: `clients/laptop/config.json`'s `hub_url` (derive the agent URL by replacing the trailing `/ws` with `/ws/agent`) and `device_name`.
- Produces: a standalone script with no dependency on `hub/` (clients and hub are separate Python environments per `CLAUDE.md`) — reuses only `websockets` (already a `clients/laptop` dependency per `main.py`) and the standard library.

- [ ] **Step 1: Write `clients/laptop/agent.py`**

Structure, mirroring `main.py`'s existing config-loading pattern (`CONFIG_PATH`, `load_config()`):

```python
"""IRIS background device agent — executes commands dispatched from the hub.
Runs independently of the chat GUI/CLI so this device stays controllable
even when no chat window is open."""
import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path

import websockets

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def agent_url_from(hub_url: str) -> str:
    # ws://host:port/ws -> ws://host:port/ws/agent
    return hub_url.rstrip("/") + "/agent" if hub_url.rstrip("/").endswith("/ws") else hub_url


def run_command(command: str, timeout: int) -> dict:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": True, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s", "stdout": "", "stderr": "", "returncode": -1}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": "", "returncode": -1}


async def run(config: dict) -> None:
    url = agent_url_from(config.get("hub_url", "ws://localhost:7865/ws"))
    device_id = socket.gethostname()
    device_name = config.get("device_name")
    print(f"IRIS agent ({device_id}) connecting to {url}")

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "register", "device_id": device_id, "device_name": device_name}))
        print("Registered. Waiting for commands...")
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "exec_command":
                result = run_command(msg["command"], msg.get("timeout", 30))
                result["type"] = "exec_result"
                result["request_id"] = msg["request_id"]
                await ws.send(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(run(load_config()))
```

`run_command`'s subprocess call blocks the single asyncio task running it — acceptable here since this agent handles one command at a time and the hub already enforces a timeout on its side of the round-trip; no concurrent command dispatch is in scope for this plan.

- [ ] **Step 2: Manually verify against a locally running hub**

Run (with the hub already up from Task 7's work): `python clients/laptop/agent.py`
Expected: prints `Registered. Waiting for commands...` and stays running; check the hub's device list (e.g. a quick `python -c "from hub import devices; print(devices.list_connected())"` in a separate shell with the hub's process, or temporarily hit a debug endpoint) shows the agent's hostname with `can_execute: true`.

- [ ] **Step 3: Document manual autostart setup in `README.md`**

Add a short section after the existing "Laptop Client" quick-start block:

```markdown
### Background agent (optional)

To let IRIS run commands on this device even when the chat window isn't open,
start `python clients/laptop/agent.py` at login:

1. Press `Win+R`, type `shell:startup`, press Enter.
2. Create a shortcut in that folder targeting:
   `pythonw.exe C:\path\to\IRIS\clients\laptop\agent.py`
3. Log out and back in (or just run the script manually) to confirm it connects.
```

- [ ] **Step 4: Commit**

```bash
git add clients/laptop/agent.py README.md
git commit -m "feat(laptop-client): add persistent background device agent"
```

---

## Task 12: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: all tests pass, including every new test added in Tasks 1-8.

- [ ] **Step 2: Manually verify the local (hub-targeting-itself) path**

With the hub running (`python -m hub`) and a chat client connected (`clients/laptop` GUI or CLI, pointed at the hub, `register_device` firing on connect):
- Ask it to do something non-destructive that maps to `execute_command` (e.g. "list the files in my Downloads folder" if no dedicated tool covers it, or directly "run `echo hello` for me") with no device named.
- Expected: runs immediately, no confirmation prompt, correct output relayed back.

- [ ] **Step 3: Manually verify the destructive-confirmation path**

Ask the same local session to do something it should mark destructive (e.g. "delete the file X" via `execute_command`, or a command matching the heuristic like a `del` on a real throwaway test file).
- Expected: a `confirm_required` prompt appears in the client; declining (or waiting out the 90s timeout) results in the model reporting it did not run; approving results in it actually running and the result being relayed.

- [ ] **Step 4: Manually verify the cross-device path**

With `clients/laptop/agent.py` running on the actual laptop (over Tailscale, per Task 11) and a chat session open on the desktop (or vice versa):
- Ask "open Google on my laptop" (or whatever `device_name`/hostname was configured) from the desktop session.
- Expected: Chrome/the default browser opens on the laptop, not the desktop; the chat response confirms which device it ran on.

- [ ] **Step 5: Manually verify an offline-target error**

Stop the laptop's agent, then from the desktop ask it to run something targeting the laptop by name.
- Expected: a clean error relayed back ("laptop isn't connected right now"), not a hang or crash.

- [ ] **Step 6: Update `docs/known-issues.md`**

Move items 1 (destructive-request suggestion nudge) and 6 (bypassable shell blocklist) to "Resolved since this file was written," each with a one-line note pointing at `execute_command`'s confirmation gate as the replacement mechanism.

- [ ] **Step 7: Commit**

```bash
git add docs/known-issues.md
git commit -m "docs: mark destructive-request and shell-blocklist issues resolved by execute_command"
```
