"""Tests for voice/tts.py — TTS class (Kokoro ONNX backend)."""
import sys
import threading
import time
import types
from unittest.mock import MagicMock, patch

import pytest

from voice.tts import TTS


def _make_tts(**kwargs) -> TTS:
    """Create a TTS instance with dummy model paths (no real files needed)."""
    return TTS(
        model_path="/fake/kokoro.onnx",
        voices_path="/fake/voices.bin",
        **kwargs,
    )


class TestTTSConstructor:
    """Test TTS constructor and initialization."""

    def test_default_speed_is_1x(self):
        """Default rate=175 should produce speed=1.0."""
        tts = _make_tts()
        assert tts._speed == pytest.approx(1.0)

    def test_custom_rate_maps_to_speed(self):
        """rate=350 → speed=2.0."""
        tts = _make_tts(rate=350)
        assert tts._speed == pytest.approx(2.0)

    def test_default_volume(self):
        tts = _make_tts()
        assert tts._volume == pytest.approx(0.9)

    def test_custom_volume(self):
        tts = _make_tts(volume=0.5)
        assert tts._volume == pytest.approx(0.5)

    def test_default_voice_is_af_heart(self):
        tts = _make_tts()
        assert tts._voice == "af_heart"

    def test_custom_voice(self):
        tts = _make_tts(voice="am_fenrir")
        assert tts._voice == "am_fenrir"

    def test_constructor_creates_lock(self):
        tts = _make_tts()
        assert hasattr(tts, "_lock")
        assert isinstance(tts._lock, type(threading.Lock()))

    def test_kokoro_not_loaded_at_init(self):
        """Model should be lazy-loaded, not at construction time."""
        tts = _make_tts()
        assert tts._kokoro is None


class TestTTSLoad:
    """Test lazy model loading."""

    def _fake_kokoro_module(self, mock_cls):
        """Inject a fake kokoro_onnx module so lazy imports succeed."""
        fake_mod = types.ModuleType("kokoro_onnx")
        fake_mod.Kokoro = mock_cls
        return patch.dict(sys.modules, {"kokoro_onnx": fake_mod})

    def test_load_creates_kokoro_instance(self):
        tts = _make_tts()
        mock_instance = MagicMock()
        mock_cls = MagicMock(return_value=mock_instance)

        with self._fake_kokoro_module(mock_cls):
            tts._load()

        mock_cls.assert_called_once_with("/fake/kokoro.onnx", "/fake/voices.bin")
        assert tts._kokoro is mock_instance

    def test_load_only_once(self):
        tts = _make_tts()
        mock_cls = MagicMock(return_value=MagicMock())

        with self._fake_kokoro_module(mock_cls):
            tts._load()
            tts._load()

        mock_cls.assert_called_once()


class TestTTSSpeak:
    """Test TTS.speak() method."""

    def _make_tts_with_mock_kokoro(self, **kwargs):
        """Return (tts, mock_kokoro) with Kokoro pre-loaded."""
        import numpy as np
        tts = _make_tts(**kwargs)
        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (
            np.zeros(24000, dtype="float32"),  # 1s of silence at 24kHz
            24000,
        )
        tts._kokoro = mock_kokoro
        return tts, mock_kokoro

    def test_speak_returns_immediately(self):
        """speak() should return without waiting for audio playback."""
        tts, _ = self._make_tts_with_mock_kokoro()

        with patch("sounddevice.play"), patch("sounddevice.wait"):
            start = time.time()
            tts.speak("Hello world")
            elapsed = time.time() - start

        assert elapsed < 0.1

    def test_speak_starts_daemon_thread(self):
        """speak() should launch a daemon thread."""
        tts, _ = self._make_tts_with_mock_kokoro()

        with patch("sounddevice.play"), patch("sounddevice.wait"):
            with patch("threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                tts.speak("Test")

                mock_thread_cls.assert_called_once()
                assert mock_thread_cls.call_args[1].get("daemon") is True
                mock_thread.start.assert_called_once()

    def test_speak_calls_kokoro_create(self):
        """speak() thread should call kokoro.create with correct args."""
        tts, mock_kokoro = self._make_tts_with_mock_kokoro(voice="bf_emma", rate=175)

        with patch("sounddevice.play"), patch("sounddevice.wait"):
            tts.speak("Hello IRIS")
            time.sleep(0.1)

        mock_kokoro.create.assert_called_once_with(
            "Hello IRIS",
            voice="bf_emma",
            speed=pytest.approx(1.0),
            lang="en-us",
        )

    def test_speak_applies_volume(self):
        """speak() should scale samples by volume before playback."""
        import numpy as np
        tts, mock_kokoro = self._make_tts_with_mock_kokoro(volume=0.5)
        samples = np.ones(100, dtype="float32")
        mock_kokoro.create.return_value = (samples, 24000)

        captured = {}

        def fake_play(audio, sr):
            captured["audio"] = audio.copy()
            captured["sr"] = sr

        with patch("sounddevice.play", side_effect=fake_play), patch("sounddevice.wait"):
            tts.speak("Test")
            time.sleep(0.1)

        assert captured["audio"] == pytest.approx(0.5 * np.ones(100))
        assert captured["sr"] == 24000

    def test_speak_uses_lock(self):
        """speak() should acquire the lock during synthesis/playback."""
        tts, _ = self._make_tts_with_mock_kokoro()
        mock_lock = MagicMock()
        tts._lock = mock_lock

        with patch("sounddevice.play"), patch("sounddevice.wait"):
            tts.speak("Test")
            time.sleep(0.1)

        mock_lock.__enter__.assert_called_once()
        mock_lock.__exit__.assert_called_once()

    def test_speak_concurrent_calls_serialized(self):
        """Multiple speak() calls should be serialized by the lock."""
        import numpy as np
        tts = _make_tts()
        call_order = []

        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (np.zeros(100, dtype="float32"), 24000)
        tts._kokoro = mock_kokoro

        def fake_play(audio, sr):
            call_order.append("play")

        def fake_wait():
            call_order.append("wait")
            time.sleep(0.05)

        with patch("sounddevice.play", side_effect=fake_play):
            with patch("sounddevice.wait", side_effect=fake_wait):
                tts.speak("First")
                tts.speak("Second")
                time.sleep(0.4)

        assert call_order == ["play", "wait", "play", "wait"]


class TestTTSStop:
    """Test TTS.stop() method."""

    def test_stop_calls_sd_stop(self):
        tts = _make_tts()
        with patch("sounddevice.stop") as mock_stop:
            tts.stop()
        mock_stop.assert_called_once()

    def test_stop_callable_before_speak(self):
        """stop() should not raise even if speak() was never called."""
        tts = _make_tts()
        with patch("sounddevice.stop"):
            tts.stop()  # should not raise
