"""Wake word → VAD → Moonshine → WebSocket pipeline with active session mode.

State machine:
1. SLEEPING: Listen for wake word via openWakeWord
2. ACTIVE: Record utterances in a loop, transcribe, send to hub, speak responses
   - Session ends on: stop phrase, 30s silence timeout, or hub error

Dependencies:
- openWakeWord: wake word detection
- webrtcvad: silence/speech detection
- Moonshine: speech-to-text
- pyttsx3: text-to-speech (async, non-blocking)
- websockets: hub communication
"""
import asyncio
import json
import time
from enum import Enum

import numpy as np
import sounddevice as sd
import webrtcvad

from voice.transcribe import Transcriber
from voice.tts import TTS

SAMPLE_RATE = 16_000
CHANNELS = 1

# webrtcvad requires 10/20/30 ms frames at 8/16/32 kHz.
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = SAMPLE_RATE * VAD_FRAME_MS // 1000  # 480

# Stop recording after this many consecutive silent frames (600 ms).
SILENCE_CUTOFF_FRAMES = 20
# Discard clips shorter than this many speech frames (240 ms).
MIN_SPEECH_FRAMES = 8
# Hard cap: abort recording after 30 s if VAD never triggers silence.
MAX_RECORD_FRAMES = (SAMPLE_RATE * 30) // VAD_FRAME_SAMPLES


class PipelineState(Enum):
    """Pipeline state."""
    SLEEPING = "sleeping"
    ACTIVE = "active"


class Pipeline:
    """Voice pipeline with openWakeWord and active session state machine."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.hub_url: str = cfg.get("hub_url", "ws://localhost:7865/ws")
        self.wake_word_model: str = cfg.get("wake_word_model", "hey_jarvis")
        self.wake_word_threshold: float = cfg.get("wake_word_threshold", 0.5)
        self.active_session_timeout: int = cfg.get("active_session_timeout_seconds", 30)
        self.stop_phrases: list[str] = cfg.get(
            "stop_phrases", ["stop", "goodbye", "that's all", "sleep", "nevermind"]
        )
        self.tts_rate: int = cfg.get("tts_rate", 175)
        self.tts_volume: float = cfg.get("tts_volume", 0.9)

    def run(self) -> None:
        """Main entry point: initialize pipeline and run state machine."""
        from openwakeword.model import Model  # type: ignore

        # Initialize components
        oww_model = Model(
            wakeword_models=[self.wake_word_model], inference_framework="onnx"
        )
        vad = webrtcvad.Vad(3)  # aggressiveness 0–3; 3 = most aggressive
        transcriber = Transcriber()
        tts = TTS(rate=self.tts_rate, volume=self.tts_volume)

        print(
            f"IRIS voice — openWakeWord '{self.wake_word_model}' "
            f"at {SAMPLE_RATE} Hz, threshold={self.wake_word_threshold}"
        )

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            ) as stream:
                self._main_loop(stream, oww_model, vad, transcriber, tts)
        except KeyboardInterrupt:
            print("\n[pipeline] shutting down")
        finally:
            tts.stop()

    def _main_loop(
        self, stream, oww_model, vad, transcriber: Transcriber, tts: TTS
    ) -> None:
        """Run state machine: SLEEPING ↔ ACTIVE."""
        state = PipelineState.SLEEPING

        while True:
            if state == PipelineState.SLEEPING:
                state = self._sleeping_loop(stream, oww_model, vad, transcriber, tts)
            elif state == PipelineState.ACTIVE:
                state = self._active_loop(stream, vad, transcriber, tts)

    def _sleeping_loop(
        self, stream, oww_model, vad, transcriber: Transcriber, tts: TTS
    ) -> PipelineState:
        """Listen for wake word. Return ACTIVE on detection."""
        # openWakeWord frame length is typically 1280 samples (80 ms at 16 kHz)
        frame_len = 1280

        while True:
            raw, _ = stream.read(frame_len)
            audio_chunk = np.frombuffer(bytes(raw), dtype=np.int16).astype(np.float32)

            # Feed to openWakeWord model
            oww_model.predict(audio_chunk)
            score = oww_model.prediction_buffer[self.wake_word_model][-1]

            if score > self.wake_word_threshold:
                print(f"\n[wake] {self.wake_word_model} detected (score={score:.2f})")
                tts.speak("Yes")  # Give audio feedback on wake
                return PipelineState.ACTIVE

    def _active_loop(
        self, stream, vad, transcriber: Transcriber, tts: TTS
    ) -> PipelineState:
        """Active listening mode: record utterances in a loop.

        Returns SLEEPING on: stop phrase, timeout, or hub error.
        """
        session_start = time.time()
        last_speech_time = time.time()

        while True:
            # Check timeout: 30 s of no new speech
            if time.time() - last_speech_time > self.active_session_timeout:
                print("[session] timeout (30s no speech)")
                tts.speak("Okay, going back to sleep")
                return PipelineState.SLEEPING

            # Record one utterance with VAD
            audio = self._record_utterance(stream, vad)
            if audio is None:
                # VAD timeout (5 s no speech detected)
                print("[vad] nothing heard")
                continue

            last_speech_time = time.time()

            # Transcribe
            print("[transcribe] processing…", end=" ", flush=True)
            text = transcriber.transcribe(audio).strip()
            if not text:
                print("(empty transcript)")
                continue
            print(f'"{text}"')

            # Check for stop phrase
            text_lower = text.lower().strip()
            if any(phrase in text_lower for phrase in self.stop_phrases):
                print("[session] stop phrase detected")
                tts.speak("Goodbye")
                return PipelineState.SLEEPING

            # Send to hub and collect response
            response_ok = asyncio.run(self._send_and_speak(text, tts))
            if not response_ok:
                # Hub error
                print("[session] hub error, returning to sleep")
                return PipelineState.SLEEPING

    def _record_utterance(self, stream, vad) -> "np.ndarray | None":
        """Record until post-speech silence; return float32 audio or None."""
        frames: list[np.ndarray] = []
        silence_count = 0
        speech_started = False
        total = 0

        while total < MAX_RECORD_FRAMES:
            raw, _ = stream.read(VAD_FRAME_SAMPLES)
            raw_bytes = bytes(raw)
            is_speech = vad.is_speech(raw_bytes, SAMPLE_RATE)
            total += 1

            if is_speech:
                speech_started = True
                silence_count = 0
                frames.append(np.frombuffer(raw_bytes, dtype=np.int16).copy())
            elif speech_started:
                silence_count += 1
                frames.append(np.frombuffer(raw_bytes, dtype=np.int16).copy())
                if silence_count >= SILENCE_CUTOFF_FRAMES:
                    break
            elif total > (5_000 // VAD_FRAME_MS):
                # No speech in first 5 s — bail out.
                break

        if len(frames) < MIN_SPEECH_FRAMES:
            return None

        audio_i16 = np.concatenate(frames)
        return audio_i16.astype(np.float32) / 32_768.0

    async def _send_and_speak(self, text: str, tts: TTS) -> bool:
        """Send text to hub, stream response, speak aloud. Return success."""
        import websockets  # type: ignore

        print("IRIS:", end=" ", flush=True)
        try:
            async with websockets.connect(self.hub_url) as ws:
                await ws.send(json.dumps({"type": "message", "text": text}))
                response_text = ""

                async for raw_msg in ws:
                    msg = json.loads(raw_msg)
                    if msg["type"] == "token":
                        token = msg["text"]
                        print(token, end="", flush=True)
                        response_text += token
                    elif msg["type"] == "error":
                        print(f"\n[hub error] {msg.get('text', '')}")
                        return False
                    elif msg["type"] == "done":
                        print()
                        break

                # Speak the collected response in background
                if response_text:
                    tts.speak(response_text)

                return True
        except Exception as exc:
            print(f"\n[voice] connection error: {exc}")
            return False
