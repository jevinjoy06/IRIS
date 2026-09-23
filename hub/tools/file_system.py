"""File system tool — sandboxed to FILE_SYSTEM_ROOT (defaults to user home)."""
import os
from pathlib import Path

_ALLOWED_ROOT = Path(os.environ.get("FILE_SYSTEM_ROOT", str(Path.home()))).resolve()


def _safe_path(raw: str) -> Path:
    """Resolve path and reject traversals outside the allowed root."""
    candidate = (_ALLOWED_ROOT / raw).resolve()
    if not str(candidate).startswith(str(_ALLOWED_ROOT)):
        raise PermissionError(f"Path '{raw}' escapes allowed root '{_ALLOWED_ROOT}'")
    return candidate


def read_file(path: str) -> dict:
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8")
        return {"ok": True, "path": str(p), "content": content}
    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except FileNotFoundError:
        return {"ok": False, "error": f"File not found: {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def write_file(path: str, content: str) -> dict:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p), "bytes_written": len(content.encode())}
    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_directory(path: str = "") -> dict:
    try:
        p = _safe_path(path) if path else _ALLOWED_ROOT
        if not p.is_dir():
            return {"ok": False, "error": f"Not a directory: {path}"}
        entries = []
        for entry in sorted(p.iterdir()):
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {"ok": True, "path": str(p), "entries": entries}
    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
