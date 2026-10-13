"""Window and application control tool (Windows-focused)."""
import subprocess
import os
import sys

try:
    import pygetwindow
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False


def list_windows() -> dict:
    """List open windows on the system."""
    if not PYGETWINDOW_AVAILABLE:
        return {
            "ok": False,
            "error": "pygetwindow not installed",
            "windows": [],
        }

    try:
        windows = []
        for win in pygetwindow.getAllWindows():
            windows.append({
                "title": win.title,
                "x": win.left,
                "y": win.top,
                "width": win.width,
                "height": win.height,
            })
        return {
            "ok": True,
            "windows": windows,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "windows": [],
        }


def focus_window(title: str) -> dict:
    """Focus a window by title (partial match)."""
    if not PYGETWINDOW_AVAILABLE:
        return {
            "ok": False,
            "error": "pygetwindow not installed",
        }

    try:
        # Find windows matching the title
        matching = [w for w in pygetwindow.getAllWindows() if title.lower() in w.title.lower()]

        if not matching:
            return {
                "ok": False,
                "error": f"No window found matching '{title}'",
            }

        # Focus the first match
        matching[0].activate()
        return {
            "ok": True,
            "focused": matching[0].title,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


def open_app(app_name: str) -> dict:
    """Open an application by name."""
    try:
        if sys.platform == "win32":
            # On Windows, use os.startfile for .exe names or paths
            # or subprocess for commands
            try:
                os.startfile(app_name)
            except (FileNotFoundError, OSError):
                # Try as a command
                subprocess.Popen(app_name, shell=True)
        else:
            # On non-Windows, use subprocess
            subprocess.Popen([app_name])

        return {
            "ok": True,
            "app": app_name,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
