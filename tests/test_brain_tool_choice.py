"""Tests for the tool-selection heuristics in hub/brain.py: _tool_choice_for
and _needs_tools. Pure functions, zero previous dedicated coverage, despite
directly controlling whether a tool call gets forced on the model's first
round — the whole reason they exist is that generic tool_choice="required"
was observed to be silently ignored by Ollama for some tools.
"""
from hub.brain import _tool_choice_for, _needs_tools


def _forced_name(result):
    assert isinstance(result, dict)
    return result["function"]["name"]


class TestClipboardDisambiguation:
    def test_clipboard_without_copy_forces_read(self):
        assert _forced_name(_tool_choice_for("what's on my clipboard")) == "clipboard_read"

    def test_clipboard_with_copy_forces_write(self):
        assert _forced_name(_tool_choice_for("copy this to my clipboard")) == "clipboard_write"

    def test_clipboard_case_insensitive(self):
        assert _forced_name(_tool_choice_for("CLIPBOARD please")) == "clipboard_read"
        assert _forced_name(_tool_choice_for("Copy that to the CLIPBOARD")) == "clipboard_write"


class TestNoToolKeywordShortCircuit:
    def test_close_blocks_forcing_even_with_no_other_signal(self):
        assert _tool_choice_for("close that window") is None

    def test_kill_blocks_forcing_even_when_run_keyword_also_present(self):
        # Documented interaction: _NO_TOOL_KEYWORDS is checked before
        # _KEYWORD_TO_TOOL, so "kill" short-circuits to None even though
        # "run"/"command" would otherwise unambiguously force
        # execute_command. Not treated as a bug here — it's consistent
        # with the system prompt's own note that the model should still
        # reach execute_command via its own judgment (tool_choice="auto")
        # for close/kill/quit requests — but it's a real, non-obvious
        # precedence rule worth pinning down with a test.
        assert _tool_choice_for("run the command to kill chrome") is None

    def test_install_blocks_forcing(self):
        assert _tool_choice_for("install this new app for me") is None

    def test_download_blocks_forcing(self):
        assert _tool_choice_for("download the latest update") is None


class TestKeywordForcing:
    def test_single_keyword_forces_exact_tool(self):
        assert _forced_name(_tool_choice_for("search for python tutorials")) == "web_search"
        assert _forced_name(_tool_choice_for("what's the weather today")) == "web_search"
        assert _forced_name(_tool_choice_for("list the folder contents")) == "file_list"
        assert _forced_name(_tool_choice_for("run this command for me")) == "execute_command"
        assert _forced_name(_tool_choice_for("remember that I like tea")) == "memory_write"
        assert _forced_name(_tool_choice_for("send me a notification")) == "notify"
        assert _forced_name(_tool_choice_for("set a timer for 5 minutes")) == "timer_set"
        assert _forced_name(_tool_choice_for("what's my cpu usage")) == "system_info"

    def test_multiword_keyword_phrase_matches(self):
        assert _forced_name(_tool_choice_for("can you look up restaurants nearby")) == "web_search"
        assert _forced_name(_tool_choice_for("what did we talk about last time")) == "memory_recall"
        assert _forced_name(_tool_choice_for("did we discuss this before")) == "memory_recall"

    def test_synonym_overlap_within_same_tool_still_forces(self):
        # "search" and "find" both map to web_search — collecting by tool
        # name (a set) collapses duplicates, so two keywords for the SAME
        # tool is still unambiguous.
        assert _forced_name(_tool_choice_for("search and find info about this")) == "web_search"

    def test_cross_tool_overlap_is_ambiguous_and_not_forced(self):
        # "search" -> web_search, "folder" -> file_list: two DIFFERENT
        # tools matched, so this must NOT force either one.
        assert _tool_choice_for("search for the file in that folder") is None

    def test_no_keyword_match_returns_none(self):
        assert _tool_choice_for("tell me a joke") is None
        assert _tool_choice_for("what's the capital of France") is None

    def test_word_boundary_prevents_substring_false_positive(self):
        # "research" contains "search" as a substring but is a single word
        # with no boundary before "search" — must not force web_search.
        assert _tool_choice_for("I'm doing some research on this topic") is None
        # "running" contains "run" as a prefix with no boundary after
        # "run" — must not force execute_command.
        assert _tool_choice_for("the app keeps running slowly") is None

    def test_empty_string_returns_none(self):
        assert _tool_choice_for("") is None


class TestNeedsTools:
    def test_greetings_need_no_tools(self):
        for text in ["hi", "hey", "hello", "yo", "sup", "hey there"]:
            assert _needs_tools(text) is False, f"{text!r} should need no tools"

    def test_thanks_needs_no_tools(self):
        assert _needs_tools("thanks a lot") is False
        assert _needs_tools("thank you!") is False

    def test_identity_questions_need_no_tools(self):
        assert _needs_tools("who are you") is False
        assert _needs_tools("what's your name") is False

    def test_short_acknowledgments_need_no_tools(self):
        for text in ["ok", "okay", "cool", "alright", "sounds good", "sure"]:
            assert _needs_tools(text) is False, f"{text!r} should need no tools"

    def test_empty_or_whitespace_only_needs_no_tools(self):
        assert _needs_tools("") is False
        assert _needs_tools("   ") is False

    def test_normal_questions_need_tools(self):
        assert _needs_tools("what's the weather in Boston") is True
        assert _needs_tools("run ls on my home directory") is True
        assert _needs_tools("search for the best pizza place nearby") is True

    def test_chitchat_pattern_wins_even_with_tool_keyword_present(self):
        # Denylist priority: a message that matches a chitchat pattern
        # skips tools entirely even if a tool keyword also appears in it.
        assert _needs_tools("thanks for looking up the weather earlier") is False

    def test_short_acknowledgment_pattern_requires_full_match(self):
        # The acknowledgment patterns are anchored (^...$), so they must
        # NOT fire on a longer sentence that merely contains "ok".
        assert _needs_tools("ok so can you check my cpu usage right now") is True
