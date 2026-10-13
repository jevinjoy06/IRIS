"""Clipboard read/write tool."""
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False


def read_clipboard() -> dict:
    """Read the system clipboard."""
    if not PYPERCLIP_AVAILABLE:
        return {
            "ok": False,
            "error": "pyperclip not installed",
            "text": "",
        }

    try:
        text = pyperclip.paste()
        return {
            "ok": True,
            "text": text,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "text": "",
        }


def write_clipboard(text: str) -> dict:
    """Write text to the system clipboard."""
    if not PYPERCLIP_AVAILABLE:
        return {
            "ok": False,
            "error": "pyperclip not installed",
        }

    try:
        pyperclip.copy(text)
        return {"ok": True}
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
