"""pyttsx3 TTS wrapper — speaks text in a daemon thread so it doesn't block."""
import threading

import pyttsx3


class TTS:
    """Text-to-speech wrapper using pyttsx3.

    Speaks text asynchronously in a background thread so audio playback
    doesn't block the voice pipeline or VAD recording.
    """

    def __init__(self, rate: int = 175, volume: float = 0.9) -> None:
        """Initialize TTS engine.

        Args:
            rate: Speech rate in words per minute (default 175).
            volume: Volume level 0.0-1.0 (default 0.9).
        """
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        """Speak text. Returns immediately; audio plays in background thread.

        Args:
            text: Text to speak aloud.
        """
        def _run():
            with self._lock:
                self._engine.say(text)
                self._engine.runAndWait()

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        """Stop any ongoing speech."""
        self._engine.stop()
