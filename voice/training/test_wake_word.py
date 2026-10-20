"""
Live wake-word test — no hub required.

Streams mic audio through the IRIS OWW model and prints the score in real time.
Say "iris" to see the score spike above the threshold.

Usage:
    python voice/training/test_wake_word.py [--threshold 0.5]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

VOICE_DIR = Path(__file__).resolve().parent.parent
CHUNK = 1280  # 80 ms at 16 kHz (OWW's native chunk size)
SAMPLE_RATE = 16_000


def load_config() -> dict:
    cfg_path = VOICE_DIR / "config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text())
    return {}


def resolve_model_path(model_val: str) -> str:
    """Resolve model path relative to voice/ if it's not absolute."""
    p = Path(model_val)
    if p.is_absolute() and p.exists():
        return str(p)
    candidate = VOICE_DIR / p
    if candidate.exists():
        return str(candidate)
    return model_val  # let OWW handle it (pre-trained name)


def bar(score: float, width: int = 30) -> str:
    filled = int(score * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description="Live IRIS wake-word test")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Detection threshold (default: from config.json)")
    args = parser.parse_args()

    cfg = load_config()
    model_val = cfg.get("wake_word_model", "iris")
    threshold = args.threshold or cfg.get("wake_word_threshold", 0.5)
    model_path = resolve_model_path(model_val)
    model_key = os.path.basename(model_path).split(".")[0]

    print(f"Model : {model_path}")
    print(f"Key   : {model_key}")
    print(f"Thresh: {threshold}")
    print()

    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice not installed: py -m pip install sounddevice")

    try:
        from openwakeword.model import Model
        oww = Model(wakeword_models=[model_path], inference_framework="onnx")
    except Exception as e:
        sys.exit(f"Failed to load OWW model: {e}")

    print("Listening... say 'iris'  (Ctrl+C to quit)\n")

    detections = 0
    buf = np.zeros(0, dtype=np.int16)

    def callback(indata, frames, time_info, status):
        nonlocal buf, detections
        chunk_i16 = (indata[:, 0] * 32767).astype(np.int16)
        buf = np.concatenate([buf, chunk_i16])

        while len(buf) >= CHUNK:
            frame, buf = buf[:CHUNK], buf[CHUNK:]
            oww.predict(frame)
            scores = oww.prediction_buffer.get(model_key, [0.0])
            score = float(scores[-1]) if scores else 0.0

            triggered = score >= threshold
            if triggered:
                detections += 1

            # Build display line
            indicator = "  <<< IRIS DETECTED!" if triggered else ""
            line = f"\r  score: {score:.3f}  {bar(score)}  detections: {detections}{indicator}"
            print(line, end="", flush=True)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                        dtype="float32", blocksize=CHUNK,
                        callback=callback):
        try:
            while True:
                sd.sleep(100)
        except KeyboardInterrupt:
            print(f"\n\nStopped. Total detections: {detections}")


if __name__ == "__main__":
    main()
