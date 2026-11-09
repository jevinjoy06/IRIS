"""Test suite for hub/server.py — REST API and WebSocket endpoints."""
import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from hub import devices, memory, pending_confirmations
from hub.tools import remote_exec


class TestFactsEndpoints:
    """Tests for /api/facts REST endpoints."""

    def test_list_facts_empty(self, client, temp_db):
        """Test GET /api/facts returns empty list."""
        response = client.get("/api/facts")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_facts_with_data(self, client, temp_db):
        """Test GET /api/facts returns all non-archived facts."""
        memory.write_fact("Fact 1", tier="relevant")
        memory.write_fact("Fact 2", tier="core")
        memory.write_fact("Fact 3", tier="archive")

        response = client.get("/api/facts")

        assert response.status_code == 200
        facts = response.json()
        assert len(facts) == 2
        # Should exclude archived
        tiers = [f["tier"] for f in facts]
        assert "archive" not in tiers

    def test_list_facts_sorted_by_importance(self, client, temp_db):
        """Test GET /api/facts returns facts sorted by importance descending."""
        memory.write_fact("Low", importance=0.2)
        memory.write_fact("High", importance=0.9)
        memory.write_fact("Medium", importance=0.5)

        response = client.get("/api/facts")

        facts = response.json()
        importances = [f["importance"] for f in facts]
        assert importances == [0.9, 0.5, 0.2]

    def test_get_fact_existing(self, client, temp_db):
        """Test GET /api/facts/{id} returns fact with all fields."""
        fact_id = memory.write_fact("Test fact", tier="core", importance=0.8)

        response = client.get(f"/api/facts/{fact_id}")

        assert response.status_code == 200
        fact = response.json()
        assert fact["id"] == fact_id
        assert fact["content"] == "Test fact"
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.8
        assert "created_at" in fact

    def test_get_fact_missing(self, client, temp_db):
        """Test GET /api/facts/{id} returns 404 for missing fact."""
        response = client.get("/api/facts/99999")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"] == "Fact not found"

    def test_create_fact_with_defaults(self, client, temp_db):
        """Test POST /api/facts creates fact with default values."""
        payload = {"content": "New fact"}

        response = client.post("/api/facts", json=payload)

        assert response.status_code == 201
        fact = response.json()
        assert fact["content"] == "New fact"
        assert fact["tier"] == "relevant"
        assert fact["importance"] == 0.5
        assert fact["tags"] == "[]"
        assert fact["access_count"] == 0

    def test_create_fact_with_custom_fields(self, client, temp_db):
        """Test POST /api/facts creates fact with custom values."""
        payload = {
            "content": "Important fact",
            "tier": "core",
            "importance": 0.9,
            "tags": ["important", "recall"],
        }

        response = client.post("/api/facts", json=payload)

        assert response.status_code == 201
        fact = response.json()
        assert fact["content"] == "Important fact"
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.9
        assert json.loads(fact["tags"]) == ["important", "recall"]

    def test_create_fact_returns_full_object(self, client, temp_db):
        """Test POST /api/facts returns the created fact object."""
        payload = {"content": "Test"}

        response = client.post("/api/facts", json=payload)

        fact = response.json()
        assert "id" in fact
        assert "created_at" in fact
        assert "access_count" in fact

    def test_update_fact_content_only(self, client, temp_db):
        """Test PATCH /api/facts/{id} updates only content."""
        fact_id = memory.write_fact("Original", tier="core", importance=0.8)

        response = client.patch(f"/api/facts/{fact_id}", json={"content": "Updated"})

        assert response.status_code == 200
        fact = response.json()
        assert fact["content"] == "Updated"
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.8

    def test_update_fact_tier_only(self, client, temp_db):
        """Test PATCH /api/facts/{id} updates only tier."""
        fact_id = memory.write_fact("Content", tier="relevant")

        response = client.patch(f"/api/facts/{fact_id}", json={"tier": "core"})

        assert response.status_code == 200
        fact = response.json()
        assert fact["tier"] == "core"
        assert fact["content"] == "Content"

    def test_update_fact_importance_only(self, client, temp_db):
        """Test PATCH /api/facts/{id} updates only importance."""
        fact_id = memory.write_fact("Content", importance=0.5)

        response = client.patch(f"/api/facts/{fact_id}", json={"importance": 0.9})

        assert response.status_code == 200
        fact = response.json()
        assert fact["importance"] == 0.9

    def test_update_fact_tags_only(self, client, temp_db):
        """Test PATCH /api/facts/{id} updates only tags."""
        fact_id = memory.write_fact("Content", tags=["old"])

        response = client.patch(
            f"/api/facts/{fact_id}", json={"tags": ["new", "tags"]}
        )

        assert response.status_code == 200
        fact = response.json()
        assert json.loads(fact["tags"]) == ["new", "tags"]

    def test_update_fact_multiple_fields(self, client, temp_db):
        """Test PATCH /api/facts/{id} updates multiple fields."""
        fact_id = memory.write_fact("Original", tier="relevant", importance=0.5)

        payload = {
            "content": "Updated",
            "tier": "core",
            "importance": 0.9,
        }
        response = client.patch(f"/api/facts/{fact_id}", json=payload)

        assert response.status_code == 200
        fact = response.json()
        assert fact["content"] == "Updated"
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.9

    def test_update_fact_missing(self, client, temp_db):
        """Test PATCH /api/facts/{id} returns 404 for missing fact."""
        response = client.patch("/api/facts/99999", json={"content": "Something"})

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_update_fact_empty_payload(self, client, temp_db):
        """Test PATCH /api/facts/{id} with empty payload returns False."""
        fact_id = memory.write_fact("Content")

        response = client.patch(f"/api/facts/{fact_id}", json={})

        # Should return 404 because no fields were updated
        assert response.status_code == 404

    def test_delete_fact_existing(self, client, temp_db):
        """Test DELETE /api/facts/{id} deletes and returns success."""
        fact_id = memory.write_fact("To delete")

        response = client.delete(f"/api/facts/{fact_id}")

        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Verify it's gone
        get_response = client.get(f"/api/facts/{fact_id}")
        assert get_response.status_code == 404

    def test_delete_fact_missing(self, client, temp_db):
        """Test DELETE /api/facts/{id} returns 404 for missing fact."""
        response = client.delete("/api/facts/99999")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data


class TestConversationsEndpoints:
    """Tests for /api/conversations REST endpoints."""

    def test_list_conversations_empty(self, client, temp_db):
        """Test GET /api/conversations returns empty list."""
        response = client.get("/api/conversations")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_conversations_with_data(self, client, temp_db):
        """Test GET /api/conversations returns sessions with metadata."""
        s1 = memory.start_session()
        memory.save_turn(s1, "user", "Hello")
        memory.save_turn(s1, "assistant", "Hi")

        response = client.get("/api/conversations")

        assert response.status_code == 200
        conversations = response.json()
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv["session_id"] == s1
        assert conv["first_message"] == "Hello"
        assert conv["turn_count"] == 2

    def test_list_conversations_multiple(self, client, temp_db):
        """Test GET /api/conversations with multiple sessions."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Session 1")
        memory.save_turn(s2, "user", "Session 2")

        response = client.get("/api/conversations")

        conversations = response.json()
        assert len(conversations) == 2

    def test_list_conversations_newest_first(self, client, temp_db):
        """Test GET /api/conversations returns newest conversations first."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Msg")
        memory.save_turn(s2, "user", "Msg")

        response = client.get("/api/conversations")

        conversations = response.json()
        # s2 was created second, should be first
        assert conversations[0]["session_id"] == s2

    def test_get_conversation_existing(self, client, temp_db):
        """Test GET /api/conversations/{id} returns turns."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Hello")
        memory.save_turn(session_id, "assistant", "Hi")

        response = client.get(f"/api/conversations/{session_id}")

        assert response.status_code == 200
        turns = response.json()
        assert len(turns) == 2
        assert turns[0]["content"] == "Hello"
        assert turns[1]["content"] == "Hi"

    def test_get_conversation_returns_all_fields(self, client, temp_db):
        """Test GET /api/conversations/{id} returns full turn objects."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Test message")

        response = client.get(f"/api/conversations/{session_id}")

        turns = response.json()
        turn = turns[0]
        assert "id" in turn
        assert "role" in turn
        assert "content" in turn
        assert "created_at" in turn

    def test_get_conversation_empty_session(self, client, temp_db):
        """Test GET /api/conversations/{id} for non-existent session."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/conversations/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_get_conversation_ordered(self, client, temp_db):
        """Test GET /api/conversations/{id} returns turns in order."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "First")
        memory.save_turn(session_id, "assistant", "Second")
        memory.save_turn(session_id, "user", "Third")

        response = client.get(f"/api/conversations/{session_id}")

        turns = response.json()
        assert [t["content"] for t in turns] == ["First", "Second", "Third"]

    def test_delete_conversation_existing(self, client, temp_db):
        """Test DELETE /api/conversations/{id} deletes turns."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Msg 1")
        memory.save_turn(session_id, "assistant", "Msg 2")

        response = client.delete(f"/api/conversations/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_turns"] == 2

        # Verify turns are gone
        get_response = client.get(f"/api/conversations/{session_id}")
        assert get_response.status_code == 404

    def test_delete_conversation_nonexistent(self, client, temp_db):
        """Test DELETE /api/conversations/{id} returns 404 for missing session."""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/conversations/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_delete_conversation_only_deletes_target(self, client, temp_db):
        """Test DELETE /api/conversations/{id} doesn't affect other sessions."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Session 1")
        memory.save_turn(s2, "user", "Session 2")

        client.delete(f"/api/conversations/{s1}")

        # s2 should still exist
        response = client.get(f"/api/conversations/{s2}")
        assert response.status_code == 200
        turns = response.json()
        assert len(turns) == 1


class TestStatusEndpoint:
    """Tests for /status endpoint."""

    def test_status_returns_all_fields(self, client, temp_db):
        """Test GET /status returns connected_clients, model, ollama_url."""
        response = client.get("/status")

        assert response.status_code == 200
        status = response.json()
        assert "connected_clients" in status
        assert "model" in status
        assert "ollama_url" in status

    def test_status_connected_clients_is_number(self, client, temp_db):
        """Test /status returns connected_clients as integer."""
        response = client.get("/status")

        status = response.json()
        assert isinstance(status["connected_clients"], int)
        assert status["connected_clients"] >= 0

    def test_status_model_has_value(self, client, temp_db):
        """Test /status returns a model string."""
        response = client.get("/status")

        status = response.json()
        assert isinstance(status["model"], str)
        assert len(status["model"]) > 0

    def test_status_ollama_url_has_value(self, client, temp_db):
        """Test /status returns ollama_url."""
        response = client.get("/status")

        status = response.json()
        assert isinstance(status["ollama_url"], str)
        assert len(status["ollama_url"]) > 0


class TestAPIIntegration:
    """Integration tests combining multiple endpoints."""

    def test_create_fact_then_retrieve(self, client, temp_db):
        """Test create a fact via POST then retrieve via GET."""
        # Create
        create_response = client.post(
            "/api/facts", json={"content": "Integration test", "tier": "core"}
        )
        assert create_response.status_code == 201
        fact_id = create_response.json()["id"]

        # Retrieve
        get_response = client.get(f"/api/facts/{fact_id}")
        assert get_response.status_code == 200
        assert get_response.json()["content"] == "Integration test"

    def test_create_fact_then_update_then_delete(self, client, temp_db):
        """Test full CRUD cycle."""
        # Create
        create_response = client.post("/api/facts", json={"content": "Original"})
        fact_id = create_response.json()["id"]

        # Update
        update_response = client.patch(
            f"/api/facts/{fact_id}", json={"content": "Updated"}
        )
        assert update_response.json()["content"] == "Updated"

        # Delete
        delete_response = client.delete(f"/api/facts/{fact_id}")
        assert delete_response.status_code == 200

        # Verify gone
        get_response = client.get(f"/api/facts/{fact_id}")
        assert get_response.status_code == 404

    def test_create_conversation_then_retrieve(self, client, temp_db):
        """Test create conversation via memory, retrieve via API."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Hello")
        memory.save_turn(session_id, "assistant", "Hi")

        # List conversations
        list_response = client.get("/api/conversations")
        conversations = list_response.json()
        assert len(conversations) == 1

        # Get specific conversation
        get_response = client.get(f"/api/conversations/{session_id}")
        assert get_response.status_code == 200
        turns = get_response.json()
        assert len(turns) == 2

    def test_multiple_facts_list_maintains_order(self, client, temp_db):
        """Test listing multiple facts maintains importance order."""
        client.post("/api/facts", json={"content": "Low", "importance": 0.2})
        client.post("/api/facts", json={"content": "High", "importance": 0.9})
        client.post("/api/facts", json={"content": "Medium", "importance": 0.5})

        response = client.get("/api/facts")
        facts = response.json()

        contents = [f["content"] for f in facts]
        assert contents == ["High", "Medium", "Low"]

    def test_archived_facts_not_in_list(self, client, temp_db):
        """Test archived facts don't appear in /api/facts."""
        # Create directly via memory
        memory.write_fact("Active", tier="relevant")
        memory.write_fact("Archived", tier="archive")

        response = client.get("/api/facts")
        facts = response.json()

        assert len(facts) == 1
        assert facts[0]["content"] == "Active"


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    """Poll ``predicate`` until true or ``timeout`` elapses (the server runs in another thread)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _connected_ids() -> dict:
    return {d["device_id"]: d for d in devices.list_connected()}


async def _reply_done(text, ws, **kwargs):
    """process_turn stand-in that sends one token + done so receive_json() never hangs."""
    await ws.send_json({"type": "token", "text": f"echo:{text}"})
    await ws.send_json({"type": "done"})
    return False


class TestDeviceWebSockets:
    """Tests for /ws/agent and the device/confirmation messages on /ws."""

    def setup_method(self):
        devices.reset_for_tests()

    def teardown_method(self):
        devices.reset_for_tests()

    # ---- /ws/agent -------------------------------------------------------

    def test_agent_register_adds_device(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            ws.send_json({"type": "exec_result", "request_id": "doesnt-matter", "ok": True})

        assert "laptop-host" not in _connected_ids()  # disconnected on exit

    def test_agent_register_then_connected_while_open(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            assert _wait_until(lambda: "laptop-host" in _connected_ids())
            connected = _connected_ids()
            assert connected["laptop-host"]["can_execute"] is True
            assert connected["laptop-host"]["device_name"] == "laptop"

    def test_agent_unmatched_exec_result_does_not_crash(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            # No pending future for this id -> resolve_exec_result returns False.
            ws.send_json({"type": "exec_result", "request_id": "req-xyz", "ok": True, "stdout": "done"})
            # The connection must still be processing messages afterwards.
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "renamed"})
            assert _wait_until(
                lambda: _connected_ids().get("laptop-host", {}).get("device_name") == "renamed"
            )

    def test_agent_exec_result_resolves_pending_future(self, client, temp_db):
        """End to end: a chat turn dispatches to the agent, the agent's reply resolves it."""

        async def turn_runs_remote_command(text, ws, **kwargs):
            result = await asyncio.wait_for(
                remote_exec.execute_remote(
                    "echo hi", False, None, kwargs.get("origin_device_id"), ws, timeout=5
                ),
                timeout=10,
            )
            await ws.send_json({"type": "token", "text": json.dumps(result)})
            await ws.send_json({"type": "done"})
            return False

        with patch("hub.server.brain.process_turn", side_effect=turn_runs_remote_command):
            # `with client:` gives both sockets one shared event loop, so a future
            # created by the chat handler can be resolved by the agent handler.
            with client:
                with client.websocket_connect("/ws/agent") as agent, client.websocket_connect("/ws") as chat:
                    agent.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
                    chat.send_json({"type": "register_device", "device_id": "laptop-host", "device_name": "laptop"})
                    # The chat's register_device is ordered before its message on the
                    # same socket; only the agent registration (other socket) can race.
                    assert _wait_until(lambda: devices.get_agent_ws("laptop-host") is not None)
                    chat.send_json({"type": "message", "text": "run it"})

                    cmd = agent.receive_json()
                    assert cmd["type"] == "exec_command"
                    assert cmd["command"] == "echo hi"
                    agent.send_json({
                        "type": "exec_result",
                        "request_id": cmd["request_id"],
                        "ok": True,
                        "stdout": "hi\n",
                    })

                    token = chat.receive_json()
                    assert token["type"] == "token"
                    result = json.loads(token["text"])
                    assert result["ok"] is True
                    assert result["stdout"] == "hi\n"
                    assert chat.receive_json() == {"type": "done"}

    def test_agent_disconnect_unregisters(self, client, temp_db):
        with client.websocket_connect("/ws/agent") as ws:
            ws.send_json({"type": "register", "device_id": "laptop-host", "device_name": "laptop"})
            assert _wait_until(lambda: "laptop-host" in _connected_ids())
        assert devices.get_agent_ws("laptop-host") is None

    # ---- /ws register_device / confirm_response ------------------------

    def test_chat_register_device_sets_origin(self, client, temp_db):
        with patch("hub.server.brain.process_turn", side_effect=_reply_done) as mock_turn:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "register_device", "device_id": "desktop-host", "device_name": "desktop"})
                ws.send_json({"type": "message", "text": "hello"})
                assert ws.receive_json() == {"type": "token", "text": "echo:hello"}
                assert ws.receive_json() == {"type": "done"}

            assert mock_turn.called
            _, kwargs = mock_turn.call_args
            assert kwargs["origin_device_id"] == "desktop-host"

    def test_local_chat_with_hub_device_id_gets_hub_as_origin(self, temp_db):
        from fastapi.testclient import TestClient
        from hub.server import app

        # TestClient's default peer is ("testclient", 50000), which is NOT
        # loopback; pin a loopback peer to model a client on the hub machine.
        local_client = TestClient(app, client=("127.0.0.1", 50000))
        hub_id = devices.register_hub_self()
        with patch("hub.server.brain.process_turn", side_effect=_reply_done) as mock_turn:
            with local_client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "register_device", "device_id": hub_id, "device_name": "hub"})
                ws.send_json({"type": "message", "text": "hello"})
                ws.receive_json()
                ws.receive_json()

            _, kwargs = mock_turn.call_args
            assert kwargs["origin_device_id"] == hub_id
        assert devices.is_hub_device(hub_id) is True  # still the hub after chat disconnects

    def test_remote_chat_cannot_claim_hub_device_id(self, temp_db):
        from fastapi.testclient import TestClient
        from hub.server import app

        remote_client = TestClient(app, client=("100.64.0.7", 50000))  # e.g. a Tailscale peer
        hub_id = devices.register_hub_self()
        with patch("hub.server.brain.process_turn", side_effect=_reply_done) as mock_turn:
            with remote_client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "register_device", "device_id": hub_id, "device_name": "hub"})
                ws.send_json({"type": "message", "text": "hello"})
                ws.receive_json()
                ws.receive_json()

            _, kwargs = mock_turn.call_args
            assert kwargs["origin_device_id"] is None

    def test_chat_without_register_device_has_no_origin(self, client, temp_db):
        with patch("hub.server.brain.process_turn", side_effect=_reply_done) as mock_turn:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "message", "text": "hello"})
                ws.receive_json()
                ws.receive_json()

            _, kwargs = mock_turn.call_args
            assert kwargs["origin_device_id"] is None

    def test_chat_disconnect_clears_device(self, client, temp_db):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "register_device", "device_id": "desktop-host", "device_name": "desktop"})
            assert _wait_until(lambda: "desktop-host" in _connected_ids())
            assert _connected_ids()["desktop-host"]["can_execute"] is False

        assert "desktop-host" not in _connected_ids()

    def test_confirm_response_resolves_future_not_process_turn(self, client, temp_db):
        with patch("hub.server.brain.process_turn", new_callable=AsyncMock, return_value=False) as mock_turn, \
                patch("hub.server.pending_confirmations.resolve", return_value=True) as mock_resolve:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "confirm_response", "request_id": "req-abc", "approved": True})
                assert _wait_until(lambda: mock_resolve.called)

            mock_resolve.assert_called_once_with("req-abc", True)
            assert mock_turn.called is False

    def test_confirm_response_non_boolean_approved_fails_closed(self, client, temp_db):
        with patch("hub.server.pending_confirmations.resolve", return_value=True) as mock_resolve:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "confirm_response", "request_id": "req-abc", "approved": "false"})
                assert _wait_until(lambda: mock_resolve.called)

            mock_resolve.assert_called_once_with("req-abc", False)

    def test_confirm_response_arrives_while_turn_in_flight(self, client, temp_db):
        """Regression for the deadlock the reader task exists to prevent.

        The turn awaits a confirmation future; the confirm_response must be
        read and resolved while process_turn is still running.
        """

        async def turn_awaiting_confirmation(text, ws, **kwargs):
            future = pending_confirmations.create("req-inflight")
            try:
                await ws.send_json({"type": "confirm_required", "request_id": "req-inflight"})
                try:
                    approved = await asyncio.wait_for(future, timeout=5)
                    outcome = f"approved={approved}"
                except asyncio.TimeoutError:
                    outcome = "timed out"
            finally:
                pending_confirmations.discard("req-inflight")
            await ws.send_json({"type": "token", "text": outcome})
            await ws.send_json({"type": "done"})
            return False

        with patch("hub.server.brain.process_turn", side_effect=turn_awaiting_confirmation):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "message", "text": "delete stuff"})
                assert ws.receive_json() == {"type": "confirm_required", "request_id": "req-inflight"}
                ws.send_json({"type": "confirm_response", "request_id": "req-inflight", "approved": False})
                assert ws.receive_json() == {"type": "token", "text": "approved=False"}
                assert ws.receive_json() == {"type": "done"}

    def test_malformed_frame_reports_error_and_session_continues(self, client, temp_db):
        with patch("hub.server.brain.process_turn", side_effect=_reply_done):
            with client.websocket_connect("/ws") as ws:
                ws.send_text("not json {")
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "Malformed message" in err["text"]
                ws.send_json({"type": "message", "text": "still here"})
                assert ws.receive_json() == {"type": "token", "text": "echo:still here"}
                assert ws.receive_json() == {"type": "done"}
