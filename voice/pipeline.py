"""Wake word → VAD → Moonshine → WebSocket pipeline."""
import asyncio
import json
import struct
from pathlib import Path

import numpy as np
import sounddevice as sd
import webrtcvad

from voice.transcribe import Transcriber

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
# After wake word: skip this many porcupine frames to flush echo/noise.
WAKE_DRAIN_FRAMES = 4


class Pipeline:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.hub_url: str = cfg.get("hub_url", "ws://localhost:7865/ws")

    def run(self) -> None:
        access_key = self.cfg.get("picovoice_access_key", "")
        ppn_path = self.cfg.get("wake_word_ppn_path")
        keyword = self.cfg.get("wake_word_model", "computer")

        import pvporcupine  # type: ignore

        if ppn_path and Path(ppn_path).exists():
            porcupine = pvporcupine.create(
                access_key=access_key, keyword_paths=[ppn_path]
            )
        else:
            porcupine = pvporcupine.create(
                access_key=access_key, keywords=[keyword]
            )

        vad = webrtcvad.Vad(3)  # aggressiveness 0–3; 3 = most aggressive
        transcriber = Transcriber()

        print(f"IRIS voice — listening for '{keyword}' on {SAMPLE_RATE} Hz")

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            ) as stream:
                self._loop(stream, porcupine, vad, transcriber)
        finally:
            porcupine.delete()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _loop(self, stream, porcupine, vad, transcriber: Transcriber) -> None:
        frame_len = porcupine.frame_length  # typically 512 at 16 kHz

        while True:
            # --- Wake word phase ---
            raw, _ = stream.read(frame_len)
            pcm = list(struct.unpack_from(f"{frame_len}h", bytes(raw)))
            if porcupine.process(pcm) < 0:
                continue

            print("\n[wake] detected — listening…")

            # Drain a few frames to clear echo from the wake word itself.
            for _ in range(WAKE_DRAIN_FRAMES):
                stream.read(frame_len)

            # --- VAD recording phase ---
            audio = self._record_utterance(stream, vad)
            if audio is None:
                print("[vad] nothing heard, back to standby")
                continue

            print("[transcribe] processing…", end=" ", flush=True)
            text = transcriber.transcribe(audio).strip()
            if not text:
                print("(empty transcript)")
                continue
            print(f'"{text}"')

            asyncio.run(self._send(text))

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

    async def _send(self, text: str) -> None:
        import websockets  # type: ignore

        print("IRIS:", end=" ", flush=True)
        try:
            async with websockets.connect(self.hub_url) as ws:
                await ws.send(json.dumps({"type": "message", "text": text}))
                async for raw_msg in ws:
                    msg = json.loads(raw_msg)
                    if msg["type"] == "token":
                        print(msg["text"], end="", flush=True)
                    elif msg["type"] == "error":
                        print(f"\n[hub error] {msg.get('text', '')}")
                        break
                    elif msg["type"] == "done":
                        print()
                        break
        except Exception as exc:
            print(f"\n[voice] connection error: {exc}")
