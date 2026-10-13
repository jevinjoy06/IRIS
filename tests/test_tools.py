"""Comprehensive pytest tests for IRIS hub computer-control tools."""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import subprocess
import json
import asyncio
from typing import Any


# ============================================================================
# SHELL TESTS
# ============================================================================

class TestShell:
    """Tests for hub/tools/shell.py — run_command()"""

    def test_run_simple_command_success(self):
        """Test running a safe command returns stdout."""
        from hub.tools import shell

        # Use 'echo' which works on both Windows and Unix
        result = shell.run_command("echo hello")
        assert result["ok"] is True
        assert "hello" in result["stdout"]
        assert result["returncode"] == 0
        assert "stderr" in result

    def test_run_command_with_non_zero_returncode(self):
        """Test command that returns non-zero exit code."""
        from hub.tools import shell

        # Command that fails (false exists on Windows via Git Bash/WSL context, but use 'exit 1')
        result = shell.run_command("cmd /c exit 1" if True else "false")
        assert result["ok"] is True  # Still ok=True, but returncode != 0
        assert result["returncode"] == 1

    def test_dangerous_pattern_rm_rf(self):
        """Test rejection of 'rm -rf' pattern."""
        from hub.tools import shell

        result = shell.run_command("rm -rf /tmp")
        assert result["ok"] is False
        assert "dangerous pattern" in result["error"].lower() or "refused" in result["error"].lower()

    def test_dangerous_pattern_format(self):
        """Test rejection of 'format' pattern."""
        from hub.tools import shell

        result = shell.run_command("format c:")
        assert result["ok"] is False
        assert "refused" in result["error"].lower()

    def test_dangerous_pattern_del_fsfq(self):
        """Test rejection of 'del /f /s /q C:' pattern."""
        from hub.tools import shell

        result = shell.run_command("del /f /s /q C:")
        assert result["ok"] is False
        assert "refused" in result["error"].lower()

    def test_dangerous_pattern_mkfs(self):
        """Test rejection of 'mkfs' pattern."""
        from hub.tools import shell

        result = shell.run_command("mkfs /dev/sda1")
        assert result["ok"] is False
        assert "refused" in result["error"].lower()

    def test_dangerous_pattern_dd_if(self):
        """Test rejection of 'dd if=' pattern."""
        from hub.tools import shell

        result = shell.run_command("dd if=/dev/zero of=/dev/sda")
        assert result["ok"] is False
        assert "refused" in result["error"].lower()

    def test_dangerous_pattern_shred(self):
        """Test rejection of 'shred' pattern."""
        from hub.tools import shell

        result = shell.run_command("shred -u /important/file")
        assert result["ok"] is False
        assert "refused" in result["error"].lower()

    def test_timeout_default_capped_at_30(self):
        """Test that timeout is capped at 30 seconds."""
        from hub.tools import shell

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
            shell.run_command("echo test", timeout=999)

            # Check that subprocess.run was called with timeout=30, not 999
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 30

    def test_timeout_expired_error(self):
        """Test handling of subprocess.TimeoutExpired exception."""
        from hub.tools import shell

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", timeout=5)

            result = shell.run_command("echo test", timeout=5)
            assert result["ok"] is False
            assert "timed out" in result["error"].lower()
            assert result["returncode"] == -1

    def test_exception_handling(self):
        """Test handling of unexpected exceptions."""
        from hub.tools import shell

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("Something went wrong")

            result = shell.run_command("echo test")
            assert result["ok"] is False
            assert "Something went wrong" in result["error"]

    def test_response_structure(self):
        """Test that all required fields are present in response."""
        from hub.tools import shell

        result = shell.run_command("echo test")
        assert "ok" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "returncode" in result


# ============================================================================
# CLIPBOARD TESTS
# ============================================================================

class TestClipboard:
    """Tests for hub/tools/clipboard.py — read() and write()"""

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.paste")
    def test_read_clipboard_success(self, mock_paste):
        """Test reading clipboard when pyperclip is available."""
        from hub.tools import clipboard

        mock_paste.return_value = "test clipboard content"
        result = clipboard.read_clipboard()

        assert result["ok"] is True
        assert result["text"] == "test clipboard content"
        mock_paste.assert_called_once()

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", False)
    def test_read_clipboard_not_available(self):
        """Test reading clipboard when pyperclip is not available."""
        from hub.tools import clipboard

        result = clipboard.read_clipboard()
        assert result["ok"] is False
        assert "not installed" in result["error"]
        assert result["text"] == ""

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.paste")
    def test_read_clipboard_exception(self, mock_paste):
        """Test read handling exception from pyperclip."""
        from hub.tools import clipboard

        mock_paste.side_effect = RuntimeError("Clipboard error")
        result = clipboard.read_clipboard()

        assert result["ok"] is False
        assert "Clipboard error" in result["error"]

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.copy")
    def test_write_clipboard_success(self, mock_copy):
        """Test writing to clipboard when pyperclip is available."""
        from hub.tools import clipboard

        result = clipboard.write_clipboard("hello world")

        assert result["ok"] is True
        mock_copy.assert_called_once_with("hello world")

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.copy")
    def test_write_clipboard_empty_string(self, mock_copy):
        """Test writing empty string to clipboard."""
        from hub.tools import clipboard

        result = clipboard.write_clipboard("")

        assert result["ok"] is True
        mock_copy.assert_called_once_with("")

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", False)
    def test_write_clipboard_not_available(self):
        """Test writing to clipboard when pyperclip is not available."""
        from hub.tools import clipboard

        result = clipboard.write_clipboard("text")
        assert result["ok"] is False
        assert "not installed" in result["error"]

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.copy")
    def test_write_clipboard_exception(self, mock_copy):
        """Test write handling exception from pyperclip."""
        from hub.tools import clipboard

        mock_copy.side_effect = RuntimeError("Write failed")
        result = clipboard.write_clipboard("text")

        assert result["ok"] is False
        assert "Write failed" in result["error"]

    @patch("hub.tools.clipboard.PYPERCLIP_AVAILABLE", True)
    @patch("hub.tools.clipboard.pyperclip.copy")
    def test_write_clipboard_large_text(self, mock_copy):
        """Test writing large text to clipboard."""
        from hub.tools import clipboard

        large_text = "x" * 100000
        result = clipboard.write_clipboard(large_text)

        assert result["ok"] is True
        mock_copy.assert_called_once_with(large_text)


# ============================================================================
# SYSTEM INFO TESTS
# ============================================================================

class TestSystemInfo:
    """Tests for hub/tools/system_info.py — get_system_info()"""

    @patch("hub.tools.system_info.PSUTIL_AVAILABLE", False)
    def test_system_info_psutil_not_available(self):
        """Test when psutil is not installed."""
        from hub.tools import system_info

        result = system_info.get_system_info()
        assert result["ok"] is False
        assert "not installed" in result["error"]

    @patch("hub.tools.system_info.PSUTIL_AVAILABLE", True)
    @patch("hub.tools.system_info.psutil.cpu_percent")
    @patch("hub.tools.system_info.psutil.virtual_memory")
    @patch("hub.tools.system_info.psutil.disk_usage")
    @patch("hub.tools.system_info.psutil.sensors_battery")
    @patch("hub.tools.system_info.platform.uname")
    def test_system_info_success_with_battery(
        self, mock_uname, mock_battery, mock_disk, mock_vm, mock_cpu
    ):
        """Test successful system info retrieval with battery present."""
        from hub.tools import system_info

        # Mock CPU
        mock_cpu.return_value = 45.2

        # Mock Virtual Memory
        mock_memory = Mock()
        mock_memory.used = 8 * (1024**3)
        mock_memory.total = 16 * (1024**3)
        mock_memory.percent = 50.0
        mock_vm.return_value = mock_memory

        # Mock Disk
        mock_disk_obj = Mock()
        mock_disk_obj.percent = 75.0
        mock_disk.return_value = mock_disk_obj

        # Mock Battery
        mock_batt = Mock()
        mock_batt.percent = 85.0
        mock_battery.return_value = mock_batt

        # Mock platform.uname()
        mock_uname.return_value = Mock(
            nodename="test-pc",
            system="Windows",
            release="10"
        )

        result = system_info.get_system_info()

        assert result["ok"] is True
        assert result["hostname"] == "test-pc"
        assert result["os"] == "Windows"
        assert result["os_version"] == "10"
        assert result["cpu_percent"] == 45.2
        assert result["ram_percent"] == 50.0
        assert result["ram_used_gb"] == 8.0
        assert result["ram_total_gb"] == 16.0
        assert result["disk_percent"] == 75.0
        assert result["battery_percent"] == 85.0

    @patch("hub.tools.system_info.PSUTIL_AVAILABLE", True)
    @patch("hub.tools.system_info.psutil.cpu_percent")
    @patch("hub.tools.system_info.psutil.virtual_memory")
    @patch("hub.tools.system_info.psutil.disk_usage")
    @patch("hub.tools.system_info.psutil.sensors_battery")
    @patch("hub.tools.system_info.platform.uname")
    def test_system_info_no_battery(
        self, mock_uname, mock_battery, mock_disk, mock_vm, mock_cpu
    ):
        """Test system info on desktop with no battery."""
        from hub.tools import system_info

        mock_cpu.return_value = 20.0

        mock_memory = Mock()
        mock_memory.used = 4 * (1024**3)
        mock_memory.total = 16 * (1024**3)
        mock_memory.percent = 25.0
        mock_vm.return_value = mock_memory

        mock_disk_obj = Mock()
        mock_disk_obj.percent = 50.0
        mock_disk.return_value = mock_disk_obj

        # No battery on desktop
        mock_battery.return_value = None

        mock_uname.return_value = Mock(
            nodename="desktop",
            system="Linux",
            release="5.10"
        )

        result = system_info.get_system_info()

        assert result["ok"] is True
        assert result["battery_percent"] is None

    @patch("hub.tools.system_info.PSUTIL_AVAILABLE", True)
    @patch("hub.tools.system_info.psutil.cpu_percent")
    def test_system_info_exception(self, mock_cpu):
        """Test exception handling in system info."""
        from hub.tools import system_info

        mock_cpu.side_effect = RuntimeError("CPU error")

        result = system_info.get_system_info()
        assert result["ok"] is False
        assert "CPU error" in result["error"]


# ============================================================================
# NOTIFICATIONS TESTS
# ============================================================================

class TestNotifications:
    """Tests for hub/tools/notifications.py — send_notification()"""

    @patch("hub.tools.notifications.PLYER_AVAILABLE", False)
    @patch("builtins.print")
    def test_send_notification_fallback_to_console(self, mock_print):
        """Test fallback to console when plyer is not available."""
        from hub.tools import notifications

        result = notifications.send_notification("Test", "Message")

        assert result["ok"] is True
        assert result["method"] == "console"
        mock_print.assert_called_once()

    @patch("builtins.print")
    def test_send_notification_native_success(self, mock_print):
        """Test native notification when plyer is available."""
        # Mock plyer.notification directly
        mock_notification = Mock()
        mock_notification.notify = Mock()

        with patch.dict("sys.modules", {"plyer": Mock(), "plyer.notification": mock_notification}):
            # Reload the module to pick up the mocked plyer
            import importlib
            from hub.tools import notifications
            importlib.reload(notifications)

            result = notifications.send_notification("Title", "Message")

            # Should call the native notify
            if notifications.PLYER_AVAILABLE:
                assert result["ok"] is True
                assert result["method"] == "native"

    @patch("builtins.print")
    def test_send_notification_native_exception_fallback(self, mock_print):
        """Test fallback to console when native notification fails."""
        mock_notification = Mock()
        mock_notification.notify = Mock(side_effect=RuntimeError("Notification failed"))

        with patch.dict("sys.modules", {"plyer": Mock(), "plyer.notification": mock_notification}):
            import importlib
            from hub.tools import notifications
            importlib.reload(notifications)

            result = notifications.send_notification("Title", "Message")

            # Should fall back to console on error
            assert result["ok"] is True

    @patch("builtins.print")
    def test_send_notification_with_empty_title(self, mock_print):
        """Test sending notification with empty title."""
        mock_notification = Mock()
        mock_notification.notify = Mock()

        with patch.dict("sys.modules", {"plyer": Mock(), "plyer.notification": mock_notification}):
            import importlib
            from hub.tools import notifications
            importlib.reload(notifications)

            result = notifications.send_notification("", "Just message")

            assert result["ok"] is True


# ============================================================================
# TIMERS TESTS
# ============================================================================

class TestTimers:
    """Tests for hub/tools/timers.py — set_timer() and set_timer_task()"""

    def test_set_timer_returns_confirmation(self):
        """Test set_timer returns confirmation dict immediately."""
        from hub.tools import timers

        result = timers.set_timer(60, "Timer fired!")

        assert result["ok"] is True
        assert result["message"] == "Timer fired!"
        assert result["fires_in_seconds"] == 60

    def test_set_timer_caps_at_24_hours(self):
        """Test set_timer caps timeout at 24 hours."""
        from hub.tools import timers

        result = timers.set_timer(999999, "Far future")

        assert result["fires_in_seconds"] == 86400  # 24 hours in seconds

    def test_set_timer_minimum_1_second(self):
        """Test set_timer enforces minimum of 1 second."""
        from hub.tools import timers

        result = timers.set_timer(0, "Instant")

        assert result["fires_in_seconds"] == 1

    def test_set_timer_negative_becomes_1_second(self):
        """Test set_timer converts negative to 1 second."""
        from hub.tools import timers

        result = timers.set_timer(-10, "Negative")

        assert result["fires_in_seconds"] == 1

    @pytest.mark.asyncio
    async def test_set_timer_task_sends_json_on_sleep(self):
        """Test set_timer_task sends WebSocket message after sleep."""
        from hub.tools import timers

        mock_ws = AsyncMock()

        # Run with short sleep
        await timers.set_timer_task(1, "Alarm!", mock_ws)

        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "timer"
        assert call_args["message"] == "Alarm!"
        assert call_args["seconds_elapsed"] == 1

    @pytest.mark.asyncio
    async def test_set_timer_task_handles_websocket_close(self):
        """Test set_timer_task handles WebSocket closure gracefully."""
        from hub.tools import timers

        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = RuntimeError("WebSocket closed")

        # Should not raise, just catch exception
        try:
            await timers.set_timer_task(1, "Test", mock_ws)
            # Success if no exception raised
        except Exception:
            pytest.fail("set_timer_task should catch WebSocket exceptions")


# ============================================================================
# WINDOW CONTROL TESTS
# ============================================================================

class TestWindowControl:
    """Tests for hub/tools/window_control.py"""

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", False)
    def test_list_windows_not_available(self):
        """Test list_windows when pygetwindow is not available."""
        from hub.tools import window_control

        result = window_control.list_windows()

        assert result["ok"] is False
        assert "not installed" in result["error"]
        assert result["windows"] == []

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_list_windows_success(self, mock_get_windows):
        """Test list_windows returns window list."""
        from hub.tools import window_control

        mock_win1 = Mock(title="Notepad", left=10, top=20, width=800, height=600)
        mock_win2 = Mock(title="Chrome", left=0, top=0, width=1920, height=1080)
        mock_get_windows.return_value = [mock_win1, mock_win2]

        result = window_control.list_windows()

        assert result["ok"] is True
        assert len(result["windows"]) == 2
        assert result["windows"][0]["title"] == "Notepad"
        assert result["windows"][1]["title"] == "Chrome"

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_list_windows_exception(self, mock_get_windows):
        """Test list_windows exception handling."""
        from hub.tools import window_control

        mock_get_windows.side_effect = RuntimeError("Window list error")

        result = window_control.list_windows()

        assert result["ok"] is False
        assert "error" in result

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", False)
    def test_focus_window_not_available(self):
        """Test focus_window when pygetwindow is not available."""
        from hub.tools import window_control

        result = window_control.focus_window("Notepad")

        assert result["ok"] is False
        assert "not installed" in result["error"]

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_focus_window_match_found(self, mock_get_windows):
        """Test focus_window with matching window."""
        from hub.tools import window_control

        mock_win = Mock(title="Notepad - test.txt")
        mock_win.activate = Mock()
        mock_get_windows.return_value = [mock_win]

        result = window_control.focus_window("Notepad")

        assert result["ok"] is True
        assert result["focused"] == "Notepad - test.txt"
        mock_win.activate.assert_called_once()

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_focus_window_no_match(self, mock_get_windows):
        """Test focus_window with no matching window."""
        from hub.tools import window_control

        mock_get_windows.return_value = []

        result = window_control.focus_window("NonexistentWindow")

        assert result["ok"] is False
        assert "window" in result["error"].lower() and "found" in result["error"].lower()

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_focus_window_case_insensitive(self, mock_get_windows):
        """Test focus_window partial match is case-insensitive."""
        from hub.tools import window_control

        mock_win = Mock(title="Google Chrome")
        mock_win.activate = Mock()
        mock_get_windows.return_value = [mock_win]

        result = window_control.focus_window("chrome")

        assert result["ok"] is True
        mock_win.activate.assert_called_once()

    @patch("hub.tools.window_control.PYGETWINDOW_AVAILABLE", True)
    @patch("hub.tools.window_control.pygetwindow.getAllWindows")
    def test_focus_window_exception(self, mock_get_windows):
        """Test focus_window exception handling."""
        from hub.tools import window_control

        mock_get_windows.side_effect = RuntimeError("Focus error")

        result = window_control.focus_window("Test")

        assert result["ok"] is False
        assert "error" in result

    @patch("hub.tools.window_control.sys.platform", "win32")
    @patch("hub.tools.window_control.os.startfile")
    def test_open_app_windows_via_startfile(self, mock_startfile):
        """Test open_app on Windows using os.startfile."""
        from hub.tools import window_control

        result = window_control.open_app("notepad.exe")

        assert result["ok"] is True
        assert result["app"] == "notepad.exe"
        mock_startfile.assert_called_once_with("notepad.exe")

    @patch("hub.tools.window_control.sys.platform", "win32")
    @patch("hub.tools.window_control.os.startfile")
    @patch("hub.tools.window_control.subprocess.Popen")
    def test_open_app_windows_fallback_to_popen(self, mock_popen, mock_startfile):
        """Test open_app fallback to Popen when startfile fails."""
        from hub.tools import window_control

        mock_startfile.side_effect = FileNotFoundError()

        result = window_control.open_app("myapp")

        assert result["ok"] is True
        mock_popen.assert_called_once_with("myapp", shell=True)

    @patch("hub.tools.window_control.sys.platform", "linux")
    @patch("hub.tools.window_control.subprocess.Popen")
    def test_open_app_linux(self, mock_popen):
        """Test open_app on Linux/Unix."""
        from hub.tools import window_control

        result = window_control.open_app("gedit")

        assert result["ok"] is True
        mock_popen.assert_called_once_with(["gedit"])

    @patch("hub.tools.window_control.sys.platform", "win32")
    @patch("hub.tools.window_control.os.startfile")
    def test_open_app_exception(self, mock_startfile):
        """Test open_app exception handling."""
        from hub.tools import window_control

        mock_startfile.side_effect = RuntimeError("Cannot open app")

        result = window_control.open_app("app")

        assert result["ok"] is False
        assert "error" in result


# ============================================================================
# REGISTRY TESTS
# ============================================================================

class TestRegistry:
    """Tests for hub/tools/registry.py — dispatch() and async_dispatch()"""

    @patch("hub.tools.shell.run_command")
    def test_dispatch_shell_run(self, mock_run_cmd):
        """Test dispatch routes shell_run to shell.run_command."""
        from hub.tools import registry

        mock_run_cmd.return_value = {"ok": True, "stdout": "test", "stderr": "", "returncode": 0}

        result_json = registry.dispatch("shell_run", {"command": "echo test"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_run_cmd.assert_called_once_with("echo test", 30)

    @patch("hub.tools.clipboard.read_clipboard")
    def test_dispatch_clipboard_read(self, mock_read):
        """Test dispatch routes clipboard_read."""
        from hub.tools import registry

        mock_read.return_value = {"ok": True, "text": "clipboard content"}

        result_json = registry.dispatch("clipboard_read", {})
        result = json.loads(result_json)

        assert result["ok"] is True
        assert result["text"] == "clipboard content"

    @patch("hub.tools.clipboard.write_clipboard")
    def test_dispatch_clipboard_write(self, mock_write):
        """Test dispatch routes clipboard_write."""
        from hub.tools import registry

        mock_write.return_value = {"ok": True}

        result_json = registry.dispatch("clipboard_write", {"text": "new text"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_write.assert_called_once_with("new text")

    @patch("hub.tools.system_info.get_system_info")
    def test_dispatch_system_info(self, mock_sysinfo):
        """Test dispatch routes system_info."""
        from hub.tools import registry

        mock_sysinfo.return_value = {
            "ok": True,
            "cpu_percent": 50.0,
            "ram_percent": 60.0,
            "disk_percent": 70.0
        }

        result_json = registry.dispatch("system_info", {})
        result = json.loads(result_json)

        assert result["ok"] is True
        assert "cpu_percent" in result

    @patch("hub.tools.notifications.send_notification")
    def test_dispatch_notify(self, mock_notify):
        """Test dispatch routes notify (notifications)."""
        from hub.tools import registry

        mock_notify.return_value = {"ok": True, "method": "console"}

        result_json = registry.dispatch("notify", {"title": "Test", "message": "Msg"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_notify.assert_called_once_with("Test", "Msg")

    @patch("hub.tools.timers.set_timer")
    def test_dispatch_timer_set(self, mock_timer):
        """Test dispatch routes timer_set."""
        from hub.tools import registry

        mock_timer.return_value = {"ok": True, "fires_in_seconds": 60}

        result_json = registry.dispatch("timer_set", {"seconds": 60, "message": "Alert!"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_timer.assert_called_once_with(60, "Alert!")

    @patch("hub.tools.window_control.list_windows")
    def test_dispatch_window_list(self, mock_list):
        """Test dispatch routes window_list."""
        from hub.tools import registry

        mock_list.return_value = {"ok": True, "windows": []}

        result_json = registry.dispatch("window_list", {})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_list.assert_called_once()

    @patch("hub.tools.window_control.focus_window")
    def test_dispatch_window_focus(self, mock_focus):
        """Test dispatch routes window_focus."""
        from hub.tools import registry

        mock_focus.return_value = {"ok": True, "focused": "Test Window"}

        result_json = registry.dispatch("window_focus", {"title": "Test"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_focus.assert_called_once_with("Test")

    @patch("hub.tools.window_control.open_app")
    def test_dispatch_app_open(self, mock_open):
        """Test dispatch routes app_open."""
        from hub.tools import registry

        mock_open.return_value = {"ok": True, "app": "notepad"}

        result_json = registry.dispatch("app_open", {"name": "notepad"})
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_open.assert_called_once_with("notepad")

    def test_dispatch_unknown_tool(self):
        """Test dispatch with unknown tool name."""
        from hub.tools import registry

        result_json = registry.dispatch("nonexistent_tool", {})
        result = json.loads(result_json)

        assert result["ok"] is False
        assert "Unknown tool" in result["error"]

    def test_dispatch_exception_handling(self):
        """Test dispatch exception handling."""
        from hub.tools import registry

        with patch("hub.tools.shell.run_command") as mock_shell:
            mock_shell.side_effect = RuntimeError("Shell error")

            result_json = registry.dispatch("shell_run", {"command": "test"})
            result = json.loads(result_json)

            assert result["ok"] is False

    @pytest.mark.asyncio
    @patch("hub.tools.timers.set_timer_task")
    @patch("hub.tools.timers.set_timer")
    async def test_async_dispatch_timer_set(self, mock_timer, mock_timer_task):
        """Test async_dispatch spawns timer task for timer_set."""
        from hub.tools import registry

        mock_timer.return_value = {"ok": True, "fires_in_seconds": 60}

        mock_ws = AsyncMock()

        # We need to handle asyncio.create_task properly
        with patch("asyncio.create_task") as mock_create_task:
            result_json = await registry.async_dispatch("timer_set", {"seconds": 60, "message": "Alert!"}, mock_ws)
            result = json.loads(result_json)

        assert result["ok"] is True
        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("hub.tools.shell.run_command")
    async def test_async_dispatch_delegates_to_sync(self, mock_run_cmd):
        """Test async_dispatch delegates non-timer tools to sync dispatch."""
        from hub.tools import registry

        mock_run_cmd.return_value = {"ok": True, "stdout": "output", "stderr": "", "returncode": 0}

        mock_ws = AsyncMock()

        result_json = await registry.async_dispatch("shell_run", {"command": "echo test"}, mock_ws)
        result = json.loads(result_json)

        assert result["ok"] is True
        mock_run_cmd.assert_called_once()


# ============================================================================
# TOOL DEFINITIONS TESTS
# ============================================================================

class TestToolDefinitions:
    """Tests for TOOL_DEFINITIONS in registry.py"""

    def test_tool_definitions_structure(self):
        """Test TOOL_DEFINITIONS has correct structure."""
        from hub.tools import registry

        assert isinstance(registry.TOOL_DEFINITIONS, list)
        assert len(registry.TOOL_DEFINITIONS) > 0

        # Check first tool has required structure
        tool = registry.TOOL_DEFINITIONS[0]
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_tool_definitions_names(self):
        """Test that expected tools are defined."""
        from hub.tools import registry

        tool_names = [t["function"]["name"] for t in registry.TOOL_DEFINITIONS]

        expected = [
            "shell_run",
            "clipboard_read",
            "clipboard_write",
            "system_info",
            "notify",
            "timer_set",
            "window_list",
            "window_focus",
            "app_open",
        ]

        for exp in expected:
            assert exp in tool_names, f"Expected tool '{exp}' not found in definitions"

    def test_tool_definitions_have_descriptions(self):
        """Test all tools have descriptions."""
        from hub.tools import registry

        for tool in registry.TOOL_DEFINITIONS:
            name = tool["function"]["name"]
            desc = tool["function"]["description"]
            assert desc and len(desc) > 0, f"Tool '{name}' missing description"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
