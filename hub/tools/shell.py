"""Shell command execution tool with basic safety checks."""
import subprocess
import re


def run_command(command: str, timeout: int = 30) -> dict:
    """
    Execute a shell command with safety limits.

    Args:
        command: The command to run
        timeout: Max execution time in seconds (capped at 30)

    Returns:
        Dict with stdout, stderr, and returncode
    """
    # Enforce max timeout of 30 seconds
    timeout = min(timeout, 30)

    # Safety checks: refuse obviously destructive patterns
    dangerous_patterns = [
        r'rm\s+-rf',
        r'format\s+',
        r'del\s+/f\s+/s\s+/q\s+[cC]:',
        r'mkfs',
        r'dd\s+if=',
        r'shred\s+',
    ]

    command_lower = command.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, command_lower):
            return {
                "ok": False,
                "error": f"Refused: command matches dangerous pattern",
                "stdout": "",
                "stderr": "",
                "returncode": -1,
            }

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Command timed out after {timeout}s",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "stdout": "",
            "stderr": "",
            "returncode": -1,
        }
