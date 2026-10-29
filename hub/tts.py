"""Server-side TTS synthesis using Kokoro ONNX.

Unlike voice/tts.py (which plays audio locally for the standalone voice
pipeline), this returns WAV bytes so the hub can stream synthesized speech to
any connected client over the WebSocket — one shared voice for every client
(desktop, laptop, dashboard) instead of each device needing its own copy of
the ~350MB model.
"""
import io
import wave
from pathlib import Path

import numpy as np

_MODEL = Path(__file__).parent.parent / "voice" / "models" / "kokoro-v1.0.onnx"
_VOICES = Path(__file__).parent.parent / "voice" / "models" / "voices-v1.0.bin"

_kokoro = None


def available() -> bool:
    return _MODEL.exists() and _VOICES.exists()


def _load():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro  # type: ignore
        _kokoro = Kokoro(str(_MODEL), str(_VOICES))
    return _kokoro


def synthesize_wav(text: str, voice: str = "af_heart", speed: float = 1.0) -> bytes:
    """Synthesize text to 16-bit PCM WAV bytes. Blocking — call via an executor."""
    kokoro = _load()
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
