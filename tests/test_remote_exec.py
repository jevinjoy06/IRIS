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
    agent_ws = AsyncMock()

    async def reply_with_result(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        remote_exec.resolve_exec_result(
            request_id, agent_ws, {"ok": True, "stdout": "remote output", "stderr": "", "returncode": 0}
        )

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

@pytest.mark.asyncio
async def test_agent_timeout_returns_error(monkeypatch):
    # `timeout` is now clamped to >=1 in execute_remote (Fix 3a), so a
    # negative input no longer makes the wait_for bound effectively 0.
    # Shrink the dispatch buffer instead so this still exercises the real
    # timeout branch without a real multi-second wait.
    monkeypatch.setattr(remote_exec, "AGENT_DISPATCH_BUFFER_SECONDS", 0.1)
    agent_ws = AsyncMock()
    devices.register_agent("laptop-host", "laptop", agent_ws)
    result = await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock(), timeout=-10)
    assert result["ok"] is False
    assert "did not respond in time" in result["error"]


@pytest.mark.asyncio
async def test_agent_dispatch_timeout_is_clamped_to_30():
    """An oversized timeout must not reach the agent uncapped — it's clamped
    to the same 30s cap already enforced by shell.execute() and the laptop
    client's agent handler."""
    agent_ws = AsyncMock()

    async def reply_with_result(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        remote_exec.resolve_exec_result(
            request_id, agent_ws, {"ok": True, "stdout": "ok", "stderr": "", "returncode": 0}
        )

    agent_ws.send_json.side_effect = reply_with_result
    devices.register_agent("laptop-host", "laptop", agent_ws)

    await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock(), timeout=9999)
    sent = agent_ws.send_json.call_args[0][0]
    assert sent["timeout"] == 30


@pytest.mark.asyncio
async def test_agent_dispatch_timeout_is_clamped_to_minimum_1():
    """A non-positive timeout must not collapse the dispatched timeout to
    zero or negative — it's clamped up to a minimum of 1s."""
    agent_ws = AsyncMock()

    async def reply_with_result(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        remote_exec.resolve_exec_result(
            request_id, agent_ws, {"ok": True, "stdout": "ok", "stderr": "", "returncode": 0}
        )

    agent_ws.send_json.side_effect = reply_with_result
    devices.register_agent("laptop-host", "laptop", agent_ws)

    await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock(), timeout=-50)
    sent = agent_ws.send_json.call_args[0][0]
    assert sent["timeout"] == 1

@pytest.mark.asyncio
async def test_resolve_exec_result_rejects_wrong_responding_ws():
    agent_ws = AsyncMock()
    impostor_ws = AsyncMock()

    async def reply_from_wrong_then_right_ws(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        # A reply from a different connection naming the same request_id must
        # not resolve the future...
        assert remote_exec.resolve_exec_result(
            request_id, impostor_ws, {"ok": True, "stdout": "forged", "stderr": "", "returncode": 0}
        ) is False
        # ...but the real agent connection still can.
        assert remote_exec.resolve_exec_result(
            request_id, agent_ws, {"ok": True, "stdout": "remote output", "stderr": "", "returncode": 0}
        ) is True

    agent_ws.send_json.side_effect = reply_from_wrong_then_right_ws
    devices.register_agent("laptop-host", "laptop", agent_ws)

    result = await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock())
    assert result["ok"] is True
    assert result["stdout"] == "remote output"

@pytest.mark.asyncio
async def test_confirmation_send_json_raising_returns_clean_error_and_cleans_up():
    hub_id = devices.register_hub_self()
    origin_ws = AsyncMock()
    origin_ws.send_json.side_effect = RuntimeError("socket closed")

    result = await remote_exec.execute_remote("echo hi", True, None, hub_id, origin_ws)

    assert result["ok"] is False
    assert "error" in result
    from hub import pending_confirmations
    assert pending_confirmations._pending == {}

@pytest.mark.asyncio
async def test_fail_pending_for_ws_resolves_immediately_without_full_timeout():
    """A pending exec future for a disconnected agent must be failed right
    away by fail_pending_for_ws, not left to wait out the full timeout."""
    agent_ws = AsyncMock()
    devices.register_agent("laptop-host", "laptop", agent_ws)

    # Dispatch, but never reply — simulate the agent vanishing mid-flight by
    # calling fail_pending_for_ws for its ws shortly after dispatch.
    async def disconnect_after_send(*args, **kwargs):
        request_id = agent_ws.send_json.call_args[0][0]["request_id"]
        assert request_id in remote_exec._pending_exec
        remote_exec.fail_pending_for_ws(agent_ws)

    agent_ws.send_json.side_effect = disconnect_after_send

    result = await asyncio.wait_for(
        remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock(), timeout=25),
        timeout=2,  # proves it resolved immediately, not after the ~35s real wait
    )
    assert result["ok"] is False
    assert "agent disconnected" in result["error"]
    assert remote_exec._pending_exec == {}


@pytest.mark.asyncio
async def test_fail_pending_for_ws_leaves_other_agents_pending_future_untouched():
    """fail_pending_for_ws must only touch entries whose stored agent_ws is
    the exact ws passed in — a different agent's pending future is
    unaffected."""
    future_a = asyncio.get_event_loop().create_future()
    future_b = asyncio.get_event_loop().create_future()
    ws_a, ws_b = object(), object()
    remote_exec._pending_exec["req-a"] = (future_a, ws_a)
    remote_exec._pending_exec["req-b"] = (future_b, ws_b)

    try:
        remote_exec.fail_pending_for_ws(ws_a)

        assert future_a.done()
        assert future_a.result() == {"ok": False, "error": "agent disconnected before replying"}
        assert "req-a" not in remote_exec._pending_exec

        assert not future_b.done()
        assert "req-b" in remote_exec._pending_exec
    finally:
        remote_exec._pending_exec.pop("req-a", None)
        remote_exec._pending_exec.pop("req-b", None)
        if not future_b.done():
            future_b.cancel()


@pytest.mark.asyncio
async def test_agent_dispatch_send_json_raising_returns_clean_error_and_cleans_up():
    agent_ws = AsyncMock()
    agent_ws.send_json.side_effect = RuntimeError("socket closed")
    devices.register_agent("laptop-host", "laptop", agent_ws)

    result = await remote_exec.execute_remote("echo hi", False, "laptop-host", None, AsyncMock())

    assert result["ok"] is False
    assert "error" in result
    assert remote_exec._pending_exec == {}
