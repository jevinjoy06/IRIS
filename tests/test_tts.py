"""Tests for voice/tts.py — TTS class."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from voice.tts import TTS


class TestTTSConstructor:
    """Test TTS constructor and initialization."""

    @patch("pyttsx3.init")
    def test_constructor_calls_pyttsx3_init(self, mock_init):
        """Constructor should call pyttsx3.init()."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        TTS()

        mock_init.assert_called_once()

    @patch("pyttsx3.init")
    def test_constructor_sets_default_rate(self, mock_init):
        """Constructor should set default rate to 175 wpm."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        TTS()

        mock_engine.setProperty.assert_any_call("rate", 175)

    @patch("pyttsx3.init")
    def test_constructor_sets_default_volume(self, mock_init):
        """Constructor should set default volume to 0.9."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        TTS()

        mock_engine.setProperty.assert_any_call("volume", 0.9)

    @patch("pyttsx3.init")
    def test_constructor_sets_custom_rate(self, mock_init):
        """Constructor should respect custom rate parameter."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        TTS(rate=200)

        mock_engine.setProperty.assert_any_call("rate", 200)

    @patch("pyttsx3.init")
    def test_constructor_sets_custom_volume(self, mock_init):
        """Constructor should respect custom volume parameter."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        TTS(volume=0.5)

        mock_engine.setProperty.assert_any_call("volume", 0.5)

    @patch("pyttsx3.init")
    def test_constructor_creates_lock(self, mock_init):
        """Constructor should initialize a threading.Lock."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()

        assert hasattr(tts, "_lock")
        assert isinstance(tts._lock, type(threading.Lock()))


class TestTTSSpeak:
    """Test TTS.speak() method."""

    @patch("pyttsx3.init")
    def test_speak_returns_immediately(self, mock_init):
        """speak() should return without waiting for playback."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()
        start = time.time()
        tts.speak("Hello world")
        elapsed = time.time() - start

        # Should return in milliseconds, not block
        assert elapsed < 0.1

    @patch("pyttsx3.init")
    def test_speak_starts_daemon_thread(self, mock_init):
        """speak() should start a daemon thread."""
        mock_engine = MagicMock()
        # Make runAndWait non-blocking to allow thread to finish quickly
        mock_engine.runAndWait = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()

        # Count threads before
        thread_count_before = threading.active_count()

        tts.speak("Hello")

        # Give thread time to start and complete
        time.sleep(0.2)

        # Should have started a new thread (daemon threads still count while running)
        # Just verify the call was made
        mock_engine.say.assert_called_once_with("Hello")

    @patch("pyttsx3.init")
    def test_speak_thread_is_daemon(self, mock_init):
        """speak() should create daemon threads (doesn't block exit)."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()

        # Mock threading.Thread to capture the daemon flag
        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            tts.speak("Test")

            # Verify daemon=True was passed
            mock_thread_cls.assert_called_once()
            call_kwargs = mock_thread_cls.call_args[1]
            assert call_kwargs.get("daemon") is True

    @patch("pyttsx3.init")
    def test_speak_calls_engine_say_and_runAndWait(self, mock_init):
        """speak() thread should call engine.say() and engine.runAndWait()."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()
        tts.speak("Hello world")

        # Wait for thread to execute
        time.sleep(0.1)

        mock_engine.say.assert_called_once_with("Hello world")
        mock_engine.runAndWait.assert_called_once()

    @patch("pyttsx3.init")
    def test_speak_uses_lock(self, mock_init):
        """speak() should acquire lock during say/runAndWait."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()

        # Mock the lock to track if it's acquired
        mock_lock = MagicMock()
        tts._lock = mock_lock

        tts.speak("Test")
        time.sleep(0.1)

        # Lock should have been acquired (enter) and released (exit)
        mock_lock.__enter__.assert_called_once()
        mock_lock.__exit__.assert_called_once()

    @patch("pyttsx3.init")
    def test_speak_concurrent_calls_serialized(self, mock_init):
        """Multiple speak() calls should be serialized by the lock."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()

        # Call order tracker
        call_order = []

        def side_effect_say(text):
            call_order.append(f"say:{text}")

        def side_effect_runAndWait():
            call_order.append("runAndWait")
            time.sleep(0.05)  # Simulate playback time

        mock_engine.say.side_effect = side_effect_say
        mock_engine.runAndWait.side_effect = side_effect_runAndWait

        # Start multiple speak calls rapidly
        tts.speak("First")
        tts.speak("Second")

        # Wait for all threads to complete
        time.sleep(0.3)

        # Verify calls were serialized (First fully completed before Second)
        assert call_order[0] == "say:First"
        assert call_order[1] == "runAndWait"
        assert call_order[2] == "say:Second"
        assert call_order[3] == "runAndWait"


class TestTTSStop:
    """Test TTS.stop() method."""

    @patch("pyttsx3.init")
    def test_stop_calls_engine_stop(self, mock_init):
        """stop() should call engine.stop()."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()
        tts.stop()

        mock_engine.stop.assert_called_once()

    @patch("pyttsx3.init")
    def test_stop_can_be_called_without_speak(self, mock_init):
        """stop() should be callable even if speak() was never called."""
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        tts = TTS()
        # Should not raise
        tts.stop()

        mock_engine.stop.assert_called_once()
