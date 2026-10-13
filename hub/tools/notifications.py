"""Desktop notifications tool."""
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


def send_notification(title: str, message: str) -> dict:
    """Send a desktop notification."""
    if not PLYER_AVAILABLE:
        # Fallback: just print to console
        print(f"[NOTIFICATION] {title}: {message}")
        return {
            "ok": True,
            "method": "console",
        }

    try:
        notification.notify(
            title=title,
            message=message,
            timeout=5,
        )
        return {
            "ok": True,
            "method": "native",
        }
    except Exception as e:
        # Fallback to console on error
        print(f"[NOTIFICATION] {title}: {message}")
        return {
            "ok": True,
            "method": "console",
            "note": f"Native notification failed, using console: {str(e)}",
        }
