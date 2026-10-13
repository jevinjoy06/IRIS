"""Test suite for hub/server.py — REST API endpoints."""
import json
import uuid

import pytest

from hub import memory


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
