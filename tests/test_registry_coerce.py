"""Tests for the loosely-typed-value coercion helpers in hub/tools/registry.py.

These exist specifically because a real LLM was observed (live testing) to
emit "destructive"/"timeout" as JSON strings instead of a bool/int, and the
destructive-flag coercion is a security-relevant fail-closed gate — a
coercion bug here silently weakens the confirmation requirement. Despite
that, neither helper had any dedicated test before this file.
"""
from hub.tools.registry import _coerce_bool, _coerce_timeout


class TestCoerceBool:
    def test_real_bool_true_passes_through(self):
        assert _coerce_bool(True, False) is True

    def test_real_bool_false_passes_through(self):
        assert _coerce_bool(False, True) is False

    def test_string_true_variants(self):
        for v in ["true", "True", "TRUE", " true ", "yes", "Yes", "YES", "1"]:
            assert _coerce_bool(v, False) is True, f"expected True for {v!r}"

    def test_string_false_variants(self):
        for v in ["false", "False", "FALSE", " false ", "no", "No", "NO", "0"]:
            assert _coerce_bool(v, True) is False, f"expected False for {v!r}"

    def test_empty_string_falls_back_to_default(self):
        # "" means absent/unset, not a clear "false" signal — it must fall
        # through to the caller's default, not silently resolve to False.
        assert _coerce_bool("", True) is True
        assert _coerce_bool("", False) is False

    def test_whitespace_only_string_falls_back_to_default(self):
        assert _coerce_bool("   ", True) is True

    def test_unrecognized_string_falls_back_to_default(self):
        assert _coerce_bool("maybe", True) is True
        assert _coerce_bool("maybe", False) is False

    def test_none_falls_back_to_default(self):
        assert _coerce_bool(None, True) is True
        assert _coerce_bool(None, False) is False

    def test_non_bool_non_string_types_fall_back_to_default(self):
        for v in [1, 0, 1.0, [], {}, ["true"]]:
            assert _coerce_bool(v, True) is True, f"expected default for {v!r}"

    def test_destructive_fail_closed_default_is_true(self):
        # This is the actual production call site's behavior
        # (async_dispatch passes default=True for "destructive"): any value
        # that doesn't unambiguously parse as a real bool must resolve to
        # True (treated as destructive), never silently False.
        garbage_values = [None, "", "   ", "unsure", 42, {}, []]
        for v in garbage_values:
            assert _coerce_bool(v, True) is True, f"{v!r} must fail CLOSED (True), not open"


class TestCoerceTimeout:
    def test_real_int_passes_through(self):
        assert _coerce_timeout(30, 99) == 30

    def test_negative_int_passes_through_unclamped(self):
        # Clamping to a sane range happens downstream in remote_exec.py —
        # this helper only coerces type, it doesn't validate range.
        assert _coerce_timeout(-5, 30) == -5

    def test_numeric_string(self):
        assert _coerce_timeout("45", 30) == 45

    def test_numeric_string_with_whitespace(self):
        assert _coerce_timeout("  45  ", 30) == 45

    def test_float_is_truncated_not_rejected(self):
        assert _coerce_timeout(30.9, 10) == 30

    def test_decimal_string_is_rejected_not_truncated(self):
        # int("30.5") raises ValueError in Python — unlike a real float,
        # a decimal *string* does not get truncated, it falls back to default.
        assert _coerce_timeout("30.5", 10) == 10

    def test_non_numeric_string_falls_back_to_default(self):
        assert _coerce_timeout("soon", 30) == 30

    def test_empty_string_falls_back_to_default(self):
        assert _coerce_timeout("", 30) == 30

    def test_none_falls_back_to_default(self):
        assert _coerce_timeout(None, 30) == 30

    def test_bool_true_falls_back_to_default_not_1(self):
        # Guards against int(True) == 1 silently "succeeding" — a bool
        # must never pass as a legitimate timeout value.
        assert _coerce_timeout(True, 30) == 30

    def test_bool_false_falls_back_to_default_not_0(self):
        assert _coerce_timeout(False, 30) == 30

    def test_very_large_numeric_string_passes_through_unclamped(self):
        assert _coerce_timeout("99999999999", 30) == 99999999999

    def test_list_or_dict_falls_back_to_default(self):
        assert _coerce_timeout([1, 2], 30) == 30
        assert _coerce_timeout({"a": 1}, 30) == 30
