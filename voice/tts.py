"""Kokoro ONNX TTS wrapper — speaks text in a daemon thread so it doesn't block.

Model files must be placed in voice/models/:
  kokoro-v1.0.onnx
  voices-v1.0.bin

Download from: https://github.com/thewh1teagle/kokoro-onnx/releases
"""
import threading
from pathlib import Path

import sounddevice as sd


_DEFAULT_MODEL = Path(__file__).parent / "models" / "kokoro-v1.0.onnx"
_DEFAULT_VOICES = Path(__file__).parent / "models" / "voices-v1.0.bin"


class TTS:
    """Text-to-speech wrapper using Kokoro ONNX.

    Speaks text asynchronously in a background thread so audio playback
    doesn't block the voice pipeline or VAD recording.
    """

    def __init__(
        self,
        rate: int = 175,
        volume: float = 0.9,
        voice: str = "af_heart",
        model_path: str | None = None,
        voices_path: str | None = None,
    ) -> None:
        self._speed = rate / 175.0  # 175 WPM baseline → 1.0x
        self._volume = volume
        self._voice = voice
        self._model_path = str(model_path or _DEFAULT_MODEL)
        self._voices_path = str(voices_path or _DEFAULT_VOICES)
        self._kokoro = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        """Lazy-load Kokoro model on first use."""
        if self._kokoro is not None:
            return
        from kokoro_onnx import Kokoro  # type: ignore
        self._kokoro = Kokoro(self._model_path, self._voices_path)

    def speak(self, text: str) -> None:
        """Speak text. Returns immediately; audio plays in background thread."""
        def _run():
            with self._lock:
                self._load()
                samples, sample_rate = self._kokoro.create(
                    text,
                    voice=self._voice,
                    speed=self._speed,
                    lang="en-us",
                )
                sd.play(samples * self._volume, sample_rate)
                sd.wait()

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        """Stop any ongoing speech."""
        sd.stop()
