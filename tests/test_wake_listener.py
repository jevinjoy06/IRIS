"""Tests for voice/wake_listener.py — UARTWakeListener class."""
import threading
from unittest.mock import MagicMock, patch

from voice.wake_listener import UARTWakeListener


class TestUARTWakeListenerConstructor:
    """Test UARTWakeListener constructor and initial state."""

    def test_constructor_stores_port(self):
        """Constructor should store the serial port string."""
        listener = UARTWakeListener("COM3")
        assert listener.port == "COM3"

    def test_constructor_stores_baud(self):
        """Constructor should store a custom baud rate."""
        listener = UARTWakeListener("COM3", baud=9600)
        assert listener.baud == 9600

    def test_constructor_default_baud(self):
        """Default baud rate should be 115200."""
        listener = UARTWakeListener("COM3")
        assert listener.baud == 115200

    def test_constructor_default_wake_byte(self):
        """Default wake byte should be 0x57 ('W')."""
        listener = UARTWakeListener("COM3")
        assert listener.wake_byte == 0x57

    def test_constructor_custom_wake_byte(self):
        """Constructor should store a custom wake byte."""
        listener = UARTWakeListener("COM3", wake_byte=0xAA)
        assert listener.wake_byte == 0xAA

    def test_constructor_thread_initially_none(self):
        """_thread should be None before start() is called."""
        listener = UARTWakeListener("COM3")
        assert listener._thread is None

    def test_constructor_ser_initially_none(self):
        """_ser should be None before the listener thread opens a port."""
        listener = UARTWakeListener("COM3")
        assert listener._ser is None

    def test_constructor_stop_event_is_threading_event(self):
        """_stop_event should be a threading.Event."""
        listener = UARTWakeListener("COM3")
        assert isinstance(listener._stop_event, type(threading.Event()))

    def test_constructor_wake_event_is_threading_event(self):
        """_wake_event should be a threading.Event."""
        listener = UARTWakeListener("COM3")
        assert isinstance(listener._wake_event, type(threading.Event()))


class TestUARTWakeListenerTriggered:
    """Test UARTWakeListener.triggered() method."""

    def test_triggered_returns_false_initially(self):
        """triggered() should return False when no wake event has been set."""
        listener = UARTWakeListener("COM3")
        assert listener.triggered() is False

    def test_triggered_returns_true_when_event_set(self):
        """triggered() should return True when _wake_event is set."""
        listener = UARTWakeListener("COM3")
        listener._wake_event.set()
        assert listener.triggered() is True

    def test_triggered_clears_event_after_returning_true(self):
        """triggered() should clear _wake_event so the flag is consumed."""
        listener = UARTWakeListener("COM3")
        listener._wake_event.set()
        listener.triggered()
        assert not listener._wake_event.is_set()

    def test_triggered_returns_false_on_second_call(self):
        """Second consecutive call to triggered() should return False (flag consumed)."""
        listener = UARTWakeListener("COM3")
        listener._wake_event.set()
        first = listener.triggered()
        second = listener.triggered()
        assert first is True
        assert second is False


class TestUARTWakeListenerStartStop:
    """Test UARTWakeListener.start() and stop() methods."""

    def test_start_creates_daemon_thread(self):
        """start() should create a daemon=True background thread."""
        real_thread = threading.Thread
        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock(spec=real_thread)
            mock_thread_cls.return_value = mock_thread

            listener = UARTWakeListener("COM3")
            listener.start()

            mock_thread_cls.assert_called_once()
            call_kwargs = mock_thread_cls.call_args[1]
            assert call_kwargs.get("daemon") is True
            mock_thread.start.assert_called_once()

    def test_start_clears_stop_event(self):
        """start() should clear _stop_event so a restarted listener runs."""
        listener = UARTWakeListener("COM3")
        listener._stop_event.set()  # Simulate previously stopped state

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            listener.start()

        assert not listener._stop_event.is_set()

    def test_start_clears_wake_event(self):
        """start() should clear any stale _wake_event from a previous run."""
        listener = UARTWakeListener("COM3")
        listener._wake_event.set()

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            listener.start()

        assert not listener._wake_event.is_set()

    def test_stop_sets_stop_event(self):
        """stop() should set _stop_event to signal the thread to exit."""
        listener = UARTWakeListener("COM3")
        listener._thread = MagicMock()

        listener.stop()

        assert listener._stop_event.is_set()

    def test_stop_joins_thread_with_timeout(self):
        """stop() should join the listener thread with a 2-second timeout."""
        listener = UARTWakeListener("COM3")
        mock_thread = MagicMock()
        listener._thread = mock_thread

        listener.stop()

        mock_thread.join.assert_called_once_with(timeout=2.0)

    def test_stop_closes_open_serial_port(self):
        """stop() should close the serial port if it is open."""
        listener = UARTWakeListener("COM3")
        mock_ser = MagicMock()
        mock_ser.is_open = True
        listener._ser = mock_ser
        listener._thread = MagicMock()

        listener.stop()

        mock_ser.close.assert_called_once()

    def test_stop_skips_close_when_port_not_open(self):
        """stop() should not call close() when the serial port is already closed."""
        listener = UARTWakeListener("COM3")
        mock_ser = MagicMock()
        mock_ser.is_open = False
        listener._ser = mock_ser
        listener._thread = MagicMock()

        listener.stop()

        mock_ser.close.assert_not_called()
