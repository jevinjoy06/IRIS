"""Tests for hub/tools/file_system.py — especially sandbox-escape edge cases.

_ALLOWED_ROOT is computed once at import time from FILE_SYSTEM_ROOT, so every
test monkeypatches the module's _ALLOWED_ROOT attribute directly (same
pattern conftest.py uses for memory._DB_PATH) rather than the env var, which
would be read too late to matter.
"""
import os
from pathlib import Path

import pytest

from hub.tools import file_system


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the file-system tool's allowed root at an isolated temp dir."""
    root = tmp_path / "sandbox_root"
    root.mkdir()
    monkeypatch.setattr(file_system, "_ALLOWED_ROOT", root.resolve())
    return root.resolve()


class TestReadFile:
    def test_read_file_success(self, sandbox):
        (sandbox / "foo.txt").write_text("hello", encoding="utf-8")
        result = file_system.read_file("foo.txt")
        assert result == {"ok": True, "path": str(sandbox / "foo.txt"), "content": "hello"}

    def test_read_file_nested(self, sandbox):
        nested = sandbox / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "c.txt").write_text("nested", encoding="utf-8")
        result = file_system.read_file("a/b/c.txt")
        assert result["ok"] is True
        assert result["content"] == "nested"

    def test_read_file_not_found(self, sandbox):
        result = file_system.read_file("does_not_exist.txt")
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_read_file_unicode_content(self, sandbox):
        (sandbox / "unicode.txt").write_text("café \U0001F600", encoding="utf-8")
        result = file_system.read_file("unicode.txt")
        assert result["ok"] is True
        assert result["content"] == "café \U0001F600"

    def test_read_file_on_a_directory(self, sandbox):
        (sandbox / "adir").mkdir()
        result = file_system.read_file("adir")
        assert result["ok"] is False  # IsADirectoryError, caught by the generic except


class TestWriteFile:
    def test_write_file_basic(self, sandbox):
        result = file_system.write_file("new.txt", "content")
        assert result["ok"] is True
        assert result["bytes_written"] == len(b"content")
        assert (sandbox / "new.txt").read_text(encoding="utf-8") == "content"

    def test_write_file_creates_parent_dirs(self, sandbox):
        result = file_system.write_file("x/y/z.txt", "deep")
        assert result["ok"] is True
        assert (sandbox / "x" / "y" / "z.txt").read_text(encoding="utf-8") == "deep"

    def test_write_file_overwrites_existing(self, sandbox):
        file_system.write_file("over.txt", "first")
        result = file_system.write_file("over.txt", "second")
        assert result["ok"] is True
        assert (sandbox / "over.txt").read_text(encoding="utf-8") == "second"

    def test_write_file_empty_content(self, sandbox):
        result = file_system.write_file("empty.txt", "")
        assert result["ok"] is True
        assert result["bytes_written"] == 0
        assert (sandbox / "empty.txt").read_text(encoding="utf-8") == ""

    def test_write_file_bytes_written_counts_utf8_bytes_not_chars(self, sandbox):
        # Each of these characters is multiple bytes in UTF-8 but one
        # Python str character — bytes_written must reflect the encoded
        # size, not len(content).
        content = "ééé"  # 3 chars, 6 bytes in UTF-8
        result = file_system.write_file("multibyte.txt", content)
        assert result["ok"] is True
        assert result["bytes_written"] == 6
        assert result["bytes_written"] != len(content)

    def test_write_file_unicode_filename(self, sandbox):
        result = file_system.write_file("café.txt", "data")
        assert result["ok"] is True
        assert (sandbox / "café.txt").exists()


class TestListDirectory:
    def test_list_directory_root(self, sandbox):
        (sandbox / "f1.txt").write_text("a", encoding="utf-8")
        (sandbox / "subdir").mkdir()
        result = file_system.list_directory("")
        assert result["ok"] is True
        names = {e["name"]: e for e in result["entries"]}
        assert names["f1.txt"]["type"] == "file"
        assert names["f1.txt"]["size"] == 1
        assert names["subdir"]["type"] == "dir"
        assert names["subdir"]["size"] is None

    def test_list_directory_subpath(self, sandbox):
        (sandbox / "sub").mkdir()
        (sandbox / "sub" / "inner.txt").write_text("x", encoding="utf-8")
        result = file_system.list_directory("sub")
        assert result["ok"] is True
        assert result["entries"][0]["name"] == "inner.txt"

    def test_list_directory_nonexistent(self, sandbox):
        result = file_system.list_directory("ghost")
        assert result["ok"] is False
        assert "not a directory" in result["error"].lower()

    def test_list_directory_on_a_file(self, sandbox):
        (sandbox / "plain.txt").write_text("x", encoding="utf-8")
        result = file_system.list_directory("plain.txt")
        assert result["ok"] is False


class TestSandboxEscape:
    """_safe_path must confine every operation to _ALLOWED_ROOT.

    These are the highest-value tests in this file: file_read/file_write/
    file_list are the hub's only tools with direct, unrestricted filesystem
    access, so a confinement bug here is a real vulnerability, not just a
    correctness nit.
    """

    def test_plain_dotdot_traversal_rejected(self, sandbox):
        # Escapes to the parent of the sandbox root, no name collision involved.
        outside = sandbox.parent / "plain_outside.txt"
        outside.write_text("secret", encoding="utf-8")
        result = file_system.read_file("../plain_outside.txt")
        assert result["ok"] is False
        assert "escapes allowed root" in result["error"]

    def test_sibling_prefix_collision_rejected(self, sandbox):
        # Regression test for the original bug: a naive
        # str(candidate).startswith(str(_ALLOWED_ROOT)) check treats any
        # sibling directory whose name happens to start with the root's
        # name as "inside" the sandbox, because it has no notion of a
        # path-segment boundary. e.g. root ".../sandbox_root" and sibling
        # ".../sandbox_rootSecrets" — the string "sandbox_rootSecrets"
        # starts with "sandbox_root" even though it's a wholly separate
        # directory.
        sibling_name = sandbox.name + "Secrets"
        sibling = sandbox.parent / sibling_name
        sibling.mkdir()
        (sibling / "secret.txt").write_text("top secret", encoding="utf-8")

        result = file_system.read_file(f"../{sibling_name}/secret.txt")
        assert result["ok"] is False
        assert "escapes allowed root" in result["error"]

    def test_sibling_prefix_collision_rejected_for_write(self, sandbox):
        sibling_name = sandbox.name + "Evil"
        sibling = sandbox.parent / sibling_name
        sibling.mkdir()

        result = file_system.write_file(f"../{sibling_name}/planted.txt", "pwned")
        assert result["ok"] is False
        assert not (sibling / "planted.txt").exists()

    def test_sibling_prefix_collision_rejected_for_list(self, sandbox):
        sibling_name = sandbox.name + "Other"
        sibling = sandbox.parent / sibling_name
        sibling.mkdir()
        (sibling / "inner.txt").write_text("x", encoding="utf-8")

        result = file_system.list_directory(f"../{sibling_name}")
        assert result["ok"] is False

    def test_absolute_path_outside_root_rejected(self, sandbox, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        secret = elsewhere / "secret.txt"
        secret.write_text("nope", encoding="utf-8")

        result = file_system.read_file(str(secret))
        assert result["ok"] is False
        assert "escapes allowed root" in result["error"]

    def test_deep_dotdot_traversal_rejected(self, sandbox):
        result = file_system.read_file("a/b/../../../../../../etc_like_escape.txt")
        assert result["ok"] is False

    def test_exact_root_is_allowed(self, sandbox):
        # The root itself must remain accessible — relative_to(root) on
        # root returns "." without raising, so this must not be rejected.
        (sandbox / "at_root.txt").write_text("fine", encoding="utf-8")
        result = file_system.read_file("at_root.txt")
        assert result["ok"] is True
