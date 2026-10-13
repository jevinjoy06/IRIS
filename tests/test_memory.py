"""Test suite for hub/memory.py — facts, sessions, and conversation management."""
import json
import uuid

import pytest

from hub import memory


class TestFactManagement:
    """Tests for fact CRUD operations."""

    def test_init_db_creates_tables(self, temp_db):
        """Verify init_db() creates both facts and turns tables."""
        import sqlite3

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()

        # Check facts table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
        )
        assert cursor.fetchone() is not None

        # Check turns table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='turns'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_write_fact_with_defaults(self, temp_db):
        """Test write_fact() with default parameters."""
        content = "This is a test fact"
        fact_id = memory.write_fact(content)

        assert isinstance(fact_id, int)
        assert fact_id > 0

        # Verify it was stored
        fact = memory.get_fact(fact_id)
        assert fact is not None
        assert fact["content"] == content
        assert fact["tier"] == "relevant"
        assert fact["importance"] == 0.5
        assert fact["tags"] == "[]"
        assert fact["access_count"] == 0

    def test_write_fact_with_custom_fields(self, temp_db):
        """Test write_fact() with all custom parameters."""
        content = "Important fact"
        tags = ["important", "recall"]
        fact_id = memory.write_fact(
            content=content,
            tier="core",
            importance=0.9,
            tags=tags,
        )

        fact = memory.get_fact(fact_id)
        assert fact["content"] == content
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.9
        assert json.loads(fact["tags"]) == tags

    def test_get_fact_returns_dict(self, temp_db):
        """Test get_fact() returns a dict with all fields."""
        fact_id = memory.write_fact("Test fact")
        fact = memory.get_fact(fact_id)

        assert isinstance(fact, dict)
        assert "id" in fact
        assert "content" in fact
        assert "tier" in fact
        assert "importance" in fact
        assert "tags" in fact
        assert "access_count" in fact
        assert "last_accessed" in fact
        assert "created_at" in fact

    def test_get_fact_missing_returns_none(self, temp_db):
        """Test get_fact() returns None for non-existent fact."""
        fact = memory.get_fact(99999)
        assert fact is None

    def test_list_facts_empty(self, temp_db):
        """Test list_facts() on empty database."""
        facts = memory.list_facts()
        assert facts == []

    def test_list_facts_excludes_archived_by_default(self, temp_db):
        """Test list_facts() excludes archived facts by default."""
        memory.write_fact("Core fact", tier="core")
        memory.write_fact("Relevant fact", tier="relevant")
        memory.write_fact("Archived fact", tier="archive")

        facts = memory.list_facts(include_archived=False)
        assert len(facts) == 2
        tiers = [f["tier"] for f in facts]
        assert "archive" not in tiers

    def test_list_facts_includes_archived_when_requested(self, temp_db):
        """Test list_facts() includes archived facts when requested."""
        memory.write_fact("Core fact", tier="core")
        memory.write_fact("Archived fact", tier="archive")

        facts = memory.list_facts(include_archived=True)
        assert len(facts) == 2

    def test_list_facts_sorted_by_importance_desc(self, temp_db):
        """Test list_facts() returns facts sorted by importance descending."""
        memory.write_fact("Low importance", tier="relevant", importance=0.2)
        memory.write_fact("High importance", tier="relevant", importance=0.9)
        memory.write_fact("Medium importance", tier="relevant", importance=0.5)

        facts = memory.list_facts()
        assert len(facts) == 3
        importances = [f["importance"] for f in facts]
        assert importances == [0.9, 0.5, 0.2]

    def test_update_fact_content_only(self, temp_db):
        """Test update_fact() with only content field."""
        fact_id = memory.write_fact("Original content", tier="core", importance=0.8)

        updated = memory.update_fact(fact_id, content="Updated content")
        assert updated is True

        fact = memory.get_fact(fact_id)
        assert fact["content"] == "Updated content"
        assert fact["tier"] == "core"  # unchanged
        assert fact["importance"] == 0.8  # unchanged

    def test_update_fact_tier_only(self, temp_db):
        """Test update_fact() with only tier field."""
        fact_id = memory.write_fact("Content", tier="relevant")

        updated = memory.update_fact(fact_id, tier="core")
        assert updated is True

        fact = memory.get_fact(fact_id)
        assert fact["tier"] == "core"
        assert fact["content"] == "Content"  # unchanged

    def test_update_fact_importance_only(self, temp_db):
        """Test update_fact() with only importance field."""
        fact_id = memory.write_fact("Content", importance=0.5)

        updated = memory.update_fact(fact_id, importance=0.8)
        assert updated is True

        fact = memory.get_fact(fact_id)
        assert fact["importance"] == 0.8

    def test_update_fact_tags_only(self, temp_db):
        """Test update_fact() with only tags field."""
        fact_id = memory.write_fact("Content", tags=["old"])

        updated = memory.update_fact(fact_id, tags=["new", "tags"])
        assert updated is True

        fact = memory.get_fact(fact_id)
        assert json.loads(fact["tags"]) == ["new", "tags"]

    def test_update_fact_multiple_fields(self, temp_db):
        """Test update_fact() with multiple fields."""
        fact_id = memory.write_fact("Original", tier="relevant", importance=0.5)

        updated = memory.update_fact(
            fact_id, content="Updated", tier="core", importance=0.9
        )
        assert updated is True

        fact = memory.get_fact(fact_id)
        assert fact["content"] == "Updated"
        assert fact["tier"] == "core"
        assert fact["importance"] == 0.9

    def test_update_fact_no_fields_returns_false(self, temp_db):
        """Test update_fact() returns False when no fields provided."""
        fact_id = memory.write_fact("Content")
        updated = memory.update_fact(fact_id)
        assert updated is False

    def test_update_fact_missing_returns_false(self, temp_db):
        """Test update_fact() returns False for non-existent fact."""
        updated = memory.update_fact(99999, content="Something")
        assert updated is False

    def test_delete_fact_success(self, temp_db):
        """Test delete_fact() deletes a fact and returns True."""
        fact_id = memory.write_fact("To delete")

        deleted = memory.delete_fact(fact_id)
        assert deleted is True

        # Verify it's gone
        fact = memory.get_fact(fact_id)
        assert fact is None

    def test_delete_fact_missing_returns_false(self, temp_db):
        """Test delete_fact() returns False for non-existent fact."""
        deleted = memory.delete_fact(99999)
        assert deleted is False


class TestSearchAndContext:
    """Tests for fact search and memory context building."""

    def test_search_facts_empty_query(self, temp_db):
        """Test search_facts() with no matches."""
        memory.write_fact("Unrelated content", tier="relevant")

        results = memory.search_facts("nonexistent")
        assert results == []

    def test_search_facts_single_match(self, temp_db):
        """Test search_facts() with single matching term."""
        memory.write_fact("The cat sat on the mat", tier="relevant")
        memory.write_fact("A dog runs fast", tier="relevant")

        results = memory.search_facts("cat")
        assert len(results) == 1
        assert "cat" in results[0]

    def test_search_facts_multi_term_scoring(self, temp_db):
        """Test search_facts() ranks results by term frequency."""
        memory.write_fact("python python python", tier="relevant")
        memory.write_fact("python java", tier="relevant")
        memory.write_fact("javascript only", tier="relevant")

        results = memory.search_facts("python")
        assert len(results) >= 2
        # "python python python" should rank higher
        assert "python python python" in results[0]

    def test_search_facts_excludes_archived(self, temp_db):
        """Test search_facts() excludes archived facts."""
        memory.write_fact("Important python concept", tier="core")
        memory.write_fact("Archived python info", tier="archive")

        results = memory.search_facts("python")
        assert len(results) == 1
        assert "Important" in results[0]

    def test_search_facts_limit(self, temp_db):
        """Test search_facts() respects limit parameter."""
        for i in range(15):
            memory.write_fact(f"Python fact {i}", tier="relevant")

        results = memory.search_facts("python", limit=5)
        assert len(results) <= 5

    def test_search_facts_bumps_access_count(self, temp_db):
        """Test search_facts() increments access_count on results."""
        fact_id = memory.write_fact("Test python fact", tier="relevant")
        original = memory.get_fact(fact_id)
        assert original["access_count"] == 0

        memory.search_facts("python")

        updated = memory.get_fact(fact_id)
        assert updated["access_count"] == 1

    def test_get_core_facts(self, temp_db):
        """Test get_core_facts() returns only core-tier facts."""
        memory.write_fact("Core fact 1", tier="core")
        memory.write_fact("Core fact 2", tier="core")
        memory.write_fact("Relevant fact", tier="relevant")

        results = memory.get_core_facts()
        assert len(results) == 2
        assert all("Core" in r for r in results)

    def test_get_core_facts_sorted_by_importance(self, temp_db):
        """Test get_core_facts() returns facts sorted by importance."""
        memory.write_fact("Low importance core", tier="core", importance=0.3)
        memory.write_fact("High importance core", tier="core", importance=0.9)

        results = memory.get_core_facts()
        assert "High importance" in results[0]
        assert "Low importance" in results[1]

    def test_get_core_facts_bumps_access(self, temp_db):
        """Test get_core_facts() increments access_count."""
        fact_id = memory.write_fact("Core fact", tier="core")
        original = memory.get_fact(fact_id)
        assert original["access_count"] == 0

        memory.get_core_facts()

        updated = memory.get_fact(fact_id)
        assert updated["access_count"] == 1

    def test_build_memory_context_empty(self, temp_db):
        """Test build_memory_context() with no facts."""
        context = memory.build_memory_context("test query")
        assert context == ""

    def test_build_memory_context_core_only(self, temp_db):
        """Test build_memory_context() with only core facts."""
        memory.write_fact("Core fact 1", tier="core")
        memory.write_fact("Core fact 2", tier="core")

        context = memory.build_memory_context("anything")
        assert "## Core facts" in context
        assert "Core fact 1" in context
        assert "Core fact 2" in context
        assert "## Relevant facts" not in context

    def test_build_memory_context_relevant_only(self, temp_db):
        """Test build_memory_context() with only relevant facts."""
        memory.write_fact("Test relevant fact", tier="relevant")

        context = memory.build_memory_context("test")
        assert "## Relevant facts" in context
        assert "Test relevant fact" in context
        assert "## Core facts" not in context

    def test_build_memory_context_deduplicates(self, temp_db):
        """Test build_memory_context() deduplicates core and relevant."""
        # Create a fact that will match both searches
        core_id = memory.write_fact("Shared fact content", tier="core")

        context = memory.build_memory_context("Shared")
        # Should appear only once, under Core facts
        lines = context.split("\n")
        fact_lines = [l for l in lines if "Shared fact" in l]
        assert len(fact_lines) == 1

    def test_build_memory_context_both_sections(self, temp_db):
        """Test build_memory_context() includes both core and relevant."""
        memory.write_fact("Core python concept", tier="core")
        memory.write_fact("Relevant python tutorial", tier="relevant")

        context = memory.build_memory_context("python")
        assert "## Core facts" in context
        assert "## Relevant facts" in context


class TestSessionManagement:
    """Tests for conversation session tracking."""

    def test_start_session_returns_uuid_string(self, temp_db):
        """Test start_session() returns a valid UUID string."""
        session_id = memory.start_session()

        assert isinstance(session_id, str)
        # Should be parseable as UUID
        uuid.UUID(session_id)

    def test_start_session_unique(self, temp_db):
        """Test start_session() returns unique IDs."""
        s1 = memory.start_session()
        s2 = memory.start_session()
        assert s1 != s2

    def test_save_turn_returns_id(self, temp_db):
        """Test save_turn() returns a turn ID."""
        session_id = memory.start_session()
        turn_id = memory.save_turn(session_id, "user", "Hello")

        assert isinstance(turn_id, int)
        assert turn_id > 0

    def test_save_turn_with_all_fields(self, temp_db):
        """Test save_turn() with all fields including tool_name."""
        session_id = memory.start_session()
        turn_id = memory.save_turn(
            session_id, "tool", "Tool result", tool_name="memory_write"
        )

        assert turn_id > 0

    def test_save_turn_without_tool_name(self, temp_db):
        """Test save_turn() with None tool_name."""
        session_id = memory.start_session()
        turn_id = memory.save_turn(session_id, "user", "Message", tool_name=None)

        assert turn_id > 0

    def test_get_session_turns_empty(self, temp_db):
        """Test get_session_turns() on session with no turns."""
        session_id = memory.start_session()
        turns = memory.get_session_turns(session_id)

        assert turns == []

    def test_get_session_turns_single(self, temp_db):
        """Test get_session_turns() with one turn."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Hello")

        turns = memory.get_session_turns(session_id)
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "Hello"

    def test_get_session_turns_multiple(self, temp_db):
        """Test get_session_turns() with multiple turns."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Hello")
        memory.save_turn(session_id, "assistant", "Hi there")
        memory.save_turn(session_id, "user", "How are you?")

        turns = memory.get_session_turns(session_id)
        assert len(turns) == 3
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"
        assert turns[2]["role"] == "user"

    def test_get_session_turns_ordered_by_created_at(self, temp_db):
        """Test get_session_turns() returns turns in chronological order."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "First")
        memory.save_turn(session_id, "assistant", "Second")
        memory.save_turn(session_id, "user", "Third")

        turns = memory.get_session_turns(session_id)
        assert [t["content"] for t in turns] == ["First", "Second", "Third"]

    def test_get_session_turns_respects_limit(self, temp_db):
        """Test get_session_turns() respects the limit parameter."""
        session_id = memory.start_session()
        for i in range(30):
            memory.save_turn(session_id, "user", f"Message {i}")

        turns = memory.get_session_turns(session_id, limit=10)
        assert len(turns) == 10

    def test_get_session_turns_mismatched_session(self, temp_db):
        """Test get_session_turns() returns empty for non-existent session."""
        fake_session = str(uuid.uuid4())
        turns = memory.get_session_turns(fake_session)
        assert turns == []

    def test_get_session_turns_only_matching_session(self, temp_db):
        """Test get_session_turns() returns only turns from that session."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Session 1 message")
        memory.save_turn(s2, "user", "Session 2 message")

        s1_turns = memory.get_session_turns(s1)
        assert len(s1_turns) == 1
        assert "Session 1" in s1_turns[0]["content"]


class TestConversationManagement:
    """Tests for conversation listing and deletion."""

    def test_list_conversations_empty(self, temp_db):
        """Test list_conversations() on empty database."""
        conversations = memory.list_conversations()
        assert conversations == []

    def test_list_conversations_single(self, temp_db):
        """Test list_conversations() with one conversation."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Hello world")

        conversations = memory.list_conversations()
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv["session_id"] == session_id
        assert conv["first_message"] == "Hello world"
        assert conv["turn_count"] == 1

    def test_list_conversations_multiple_sessions(self, temp_db):
        """Test list_conversations() with multiple sessions."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Session 1")
        memory.save_turn(s2, "user", "Session 2")

        conversations = memory.list_conversations()
        assert len(conversations) == 2

    def test_list_conversations_first_message_is_user_message(self, temp_db):
        """Test list_conversations() extracts first user message."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "First user message")
        memory.save_turn(session_id, "assistant", "Response")
        memory.save_turn(session_id, "user", "Second user message")

        conversations = memory.list_conversations()
        assert conversations[0]["first_message"] == "First user message"

    def test_list_conversations_turn_count(self, temp_db):
        """Test list_conversations() counts all turns (not just user)."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Message")
        memory.save_turn(session_id, "assistant", "Response")
        memory.save_turn(session_id, "tool", "Tool output", tool_name="search")

        conversations = memory.list_conversations()
        assert conversations[0]["turn_count"] == 3

    def test_list_conversations_ordered_by_created_at_desc(self, temp_db):
        """Test list_conversations() returns newest first."""
        s1 = memory.start_session()
        s2 = memory.start_session()
        s3 = memory.start_session()

        memory.save_turn(s1, "user", "Msg")
        memory.save_turn(s2, "user", "Msg")
        memory.save_turn(s3, "user", "Msg")

        conversations = memory.list_conversations()
        # Should be reverse order: s3, s2, s1
        assert conversations[0]["session_id"] == s3
        assert conversations[1]["session_id"] == s2
        assert conversations[2]["session_id"] == s1

    def test_list_conversations_limit(self, temp_db):
        """Test list_conversations() respects limit parameter."""
        for _ in range(30):
            session_id = memory.start_session()
            memory.save_turn(session_id, "user", "Message")

        conversations = memory.list_conversations(limit=10)
        assert len(conversations) == 10

    def test_delete_conversation_success(self, temp_db):
        """Test delete_conversation() removes all turns and returns count."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Msg 1")
        memory.save_turn(session_id, "assistant", "Msg 2")

        count = memory.delete_conversation(session_id)
        assert count == 2

        # Verify turns are gone
        turns = memory.get_session_turns(session_id)
        assert turns == []

    def test_delete_conversation_nonexistent_returns_zero(self, temp_db):
        """Test delete_conversation() returns 0 for non-existent session."""
        fake_session = str(uuid.uuid4())
        count = memory.delete_conversation(fake_session)
        assert count == 0

    def test_delete_conversation_doesnt_affect_other_sessions(self, temp_db):
        """Test delete_conversation() only removes targeted session."""
        s1 = memory.start_session()
        s2 = memory.start_session()

        memory.save_turn(s1, "user", "Session 1")
        memory.save_turn(s2, "user", "Session 2")

        memory.delete_conversation(s1)

        s2_turns = memory.get_session_turns(s2)
        assert len(s2_turns) == 1


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_fact_with_empty_string(self, temp_db):
        """Test storing a fact with empty content."""
        # Empty strings are allowed, but unusual
        fact_id = memory.write_fact("")
        fact = memory.get_fact(fact_id)
        assert fact["content"] == ""

    def test_fact_with_very_long_content(self, temp_db):
        """Test storing a fact with very long content."""
        long_content = "x" * 100000
        fact_id = memory.write_fact(long_content)
        fact = memory.get_fact(fact_id)
        assert fact["content"] == long_content

    def test_fact_with_special_characters(self, temp_db):
        """Test storing facts with special characters."""
        content = "Test with 'quotes', \"double\", and \\ backslash; special chars: <>{}[]"
        fact_id = memory.write_fact(content)
        fact = memory.get_fact(fact_id)
        assert fact["content"] == content

    def test_fact_with_unicode(self, temp_db):
        """Test storing facts with unicode characters."""
        content = "Hello 世界 🌍 مرحبا мир"
        fact_id = memory.write_fact(content)
        fact = memory.get_fact(fact_id)
        assert fact["content"] == content

    def test_fact_with_newlines(self, temp_db):
        """Test storing facts with newlines."""
        content = "Line 1\nLine 2\nLine 3"
        fact_id = memory.write_fact(content)
        fact = memory.get_fact(fact_id)
        assert fact["content"] == content

    def test_importance_zero(self, temp_db):
        """Test fact with importance = 0."""
        fact_id = memory.write_fact("Low priority", importance=0.0)
        fact = memory.get_fact(fact_id)
        assert fact["importance"] == 0.0

    def test_importance_one(self, temp_db):
        """Test fact with importance = 1.0."""
        fact_id = memory.write_fact("High priority", importance=1.0)
        fact = memory.get_fact(fact_id)
        assert fact["importance"] == 1.0

    def test_tags_empty_list(self, temp_db):
        """Test fact with empty tags list."""
        fact_id = memory.write_fact("No tags", tags=[])
        fact = memory.get_fact(fact_id)
        assert json.loads(fact["tags"]) == []

    def test_tags_with_special_characters(self, temp_db):
        """Test tags with special characters."""
        tags = ["tag:1", "tag-2", "tag_3", "tag.4"]
        fact_id = memory.write_fact("Tagged", tags=tags)
        fact = memory.get_fact(fact_id)
        assert json.loads(fact["tags"]) == tags

    def test_multiple_turns_same_content(self, temp_db):
        """Test saving identical turns in same session."""
        session_id = memory.start_session()
        memory.save_turn(session_id, "user", "Same message")
        memory.save_turn(session_id, "user", "Same message")

        turns = memory.get_session_turns(session_id)
        assert len(turns) == 2

    def test_turn_with_json_content(self, temp_db):
        """Test saving turn with JSON content."""
        session_id = memory.start_session()
        json_content = json.dumps({"key": "value", "nested": {"a": 1}})
        memory.save_turn(session_id, "tool", json_content, tool_name="search")

        turns = memory.get_session_turns(session_id)
        assert turns[0]["content"] == json_content
