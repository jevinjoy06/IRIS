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
