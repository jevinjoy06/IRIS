"""Shell command execution tool with basic safety checks."""
import subprocess
import re


DANGEROUS_PATTERNS = [
    r'rm\s+-rf',
    r'format\s+',
    r'del\s+/f\s+/s\s+/q\s+[cC]:',
    r'mkfs',
    r'dd\s+if=',
    r'shred\s+',
]


def is_destructive_pattern(command: str) -> bool:
    """Return True if the command matches a known destructive pattern."""
    command_lower = command.lower()
    return any(re.search(pattern, command_lower) for pattern in DANGEROUS_PATTERNS)


def execute(command: str, timeout: int = 30) -> dict:
    """
    Execute a shell command with a timeout limit. Does not perform safety checks;
    callers that need to gate destructive commands should call is_destructive_pattern().

    Args:
        command: The command to run
        timeout: Max execution time in seconds (capped at 30)

    Returns:
        Dict with ok, stdout, stderr, and returncode
    """
    # Enforce max timeout of 30 seconds
    timeout = min(timeout, 30)

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


def run_command(command: str, timeout: int = 30) -> dict:
    """
    Backward-compatible wrapper: refuses destructive commands, then executes.
    Kept so the existing shell_run dispatch path behaves as before. Slated for
    removal when the shell_run tool is retired.
    """
    if is_destructive_pattern(command):
        return {
            "ok": False,
            "error": "Refused: command matches dangerous pattern",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
        }
    return execute(command, timeout)
