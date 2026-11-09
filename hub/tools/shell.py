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
    # PowerShell Remove-Item with recursive and/or force flags, in either
    # order (e.g. "Remove-Item -Recurse -Force").
    r'remove-item(?=.*-recurse)(?=.*-force)',
    # Bare del/erase of anything, beyond the narrow /f /s /q C: pattern above.
    r'\b(del|erase)\s+',
    # Recursive directory removal (rd/rmdir /s).
    r'\b(rd|rmdir)\b.*/s',
    # rm with -r and -f combined into a single flag cluster, in either order
    # (e.g. "rm -fr", not just the exact "-rf" substring above).
    r'rm\s+-[rfvid]*r[rfvid]*f[rfvid]*\b|rm\s+-[rfvid]*f[rfvid]*r[rfvid]*\b',
    # rm with -r and -f as separate flags, in either order (e.g. "rm -f -r").
    r'rm\s+-[rfvid]*r[rfvid]*\s+-[rfvid]*f[rfvid]*\b|rm\s+-[rfvid]*f[rfvid]*\s+-[rfvid]*r[rfvid]*\b',
    # Process termination.
    r'taskkill',
    r'stop-process',
    # Registry deletion.
    r'reg\s+delete',
    # Disk partitioning.
    r'diskpart',
    # Truncating output redirect: a single ">" (overwrites the target file),
    # but not ">>" (appends) and not "N>&M" (fd duplication, e.g. "2>&1").
    r'(?<!>)>(?!>|&)\s*\S',
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
