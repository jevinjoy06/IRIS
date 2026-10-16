"""
Generate training data for the custom 'iris' wake-word model.

Output layout:
    voice/training/data/positive/   – 2-second WAV clips containing "iris"
    voice/training/data/negative/   – 2-second WAV clips without "iris"

Usage:
    python voice/training/generate_data.py [--record N]

Options:
    --record N    Also record N real mic utterances of "iris" (default 0)
"""

import argparse
import math
import os
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
VOICE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
POS_DIR = DATA_DIR / "positive"
NEG_DIR = DATA_DIR / "negative"

SAMPLE_RATE = 16_000
CLIP_SAMPLES = SAMPLE_RATE * 2  # 2-second clips


# ---------------------------------------------------------------------------
# Audio utilities
# ---------------------------------------------------------------------------

def _resample(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resample float32 mono audio from orig_sr to SAMPLE_RATE."""
    if orig_sr == SAMPLE_RATE:
        return audio
    try:
        from scipy.signal import resample_poly
        g = math.gcd(SAMPLE_RATE, orig_sr)
        return resample_poly(audio, SAMPLE_RATE // g, orig_sr // g).astype(np.float32)
    except ImportError:
        n_out = int(len(audio) * SAMPLE_RATE / orig_sr)
        indices = np.linspace(0, len(audio) - 1, n_out)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Load WAV file → (float32 mono, sample_rate)."""
    with wave.open(str(path), "r") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    if sw == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    else:
        audio = np.frombuffer(raw, dtype=np.float32)

    if n_ch == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)
    return audio, sr


def _save_wav(path: Path, audio: np.ndarray) -> None:
    """Save float32 mono audio as 16-bit WAV at SAMPLE_RATE."""
    samples = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.tobytes())


def _to_clip(audio: np.ndarray, word_offset: float = 0.5) -> np.ndarray:
    """
    Embed audio into a CLIP_SAMPLES-length clip.
    word_offset: target start time (seconds) for the word within the clip.
    """
    clip = np.zeros(CLIP_SAMPLES, dtype=np.float32)
    start = int(word_offset * SAMPLE_RATE)
    end = min(start + len(audio), CLIP_SAMPLES)
    clip[start:end] = audio[: end - start]
    return clip


def _add_noise(audio: np.ndarray, snr_db: float = 20.0) -> np.ndarray:
    """Add white Gaussian noise at the given SNR."""
    rms = np.sqrt(np.mean(audio ** 2)) + 1e-9
    noise_rms = rms / (10 ** (snr_db / 20))
    noise = np.random.randn(len(audio)).astype(np.float32) * noise_rms
    return np.clip(audio + noise, -1.0, 1.0)


def _speed_perturb(audio: np.ndarray, factor: float) -> np.ndarray:
    """Approximate speed perturbation by resampling ratio."""
    n_out = int(len(audio) / factor)
    indices = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def generate_pyttsx3_clips(texts: list[str], out_dir: Path, prefix: str) -> int:
    """
    Use pyttsx3 to synthesise `texts` at multiple voices and rates.
    Returns the number of WAV files written.
    """
    try:
        import pyttsx3
    except ImportError:
        print("[warn] pyttsx3 not installed — skipping offline TTS")
        return 0

    # Gather voices once
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    del engine

    count = 0
    rates = [145, 165, 185, 205]
    speed_factors = [0.90, 1.00, 1.10]

    for vi, voice in enumerate(voices):
        for rate in rates:
            for ti, text in enumerate(texts):
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                try:
                    eng = pyttsx3.init()
                    eng.setProperty("voice", voice.id)
                    eng.setProperty("rate", rate)
                    eng.save_to_file(text, tmp.name)
                    eng.runAndWait()
                    del eng

                    raw, sr = _load_wav(Path(tmp.name))
                    audio = _resample(raw, sr)

                    for fi, spd in enumerate(speed_factors):
                        perturbed = _speed_perturb(audio, spd)
                        # Random word offset between 0.3–0.8 s
                        offset = 0.3 + np.random.rand() * 0.5
                        clip = _to_clip(perturbed, offset)

                        fname = out_dir / f"{prefix}_v{vi}_r{rate}_t{ti}_s{fi}.wav"
                        _save_wav(fname, clip)
                        count += 1

                        # Noisy augment
                        noisy = _add_noise(clip, snr_db=15 + np.random.rand() * 15)
                        _save_wav(
                            out_dir / f"{prefix}_v{vi}_r{rate}_t{ti}_s{fi}_n.wav",
                            noisy,
                        )
                        count += 1

                except Exception as exc:
                    print(f"[warn] TTS failed (voice={vi}, rate={rate}, t={ti}): {exc}")
                finally:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass

    return count


def generate_silence_noise_clips(out_dir: Path, n: int = 300) -> int:
    """Generate pure silence, white noise, and pink-ish noise clips."""
    count = 0
    third = n // 3

    for i in range(n):
        if i < third:
            # Silence with very low noise floor
            clip = np.random.randn(CLIP_SAMPLES).astype(np.float32) * 0.002
        elif i < 2 * third:
            # White noise
            amp = 0.005 + np.random.rand() * 0.02
            clip = np.random.randn(CLIP_SAMPLES).astype(np.float32) * amp
        else:
            # Pink-ish noise (cumsum ≈ 1/f)
            white = np.random.randn(CLIP_SAMPLES).astype(np.float32)
            pink = np.cumsum(white)
            pink -= pink.mean()
            rms = np.sqrt(np.mean(pink ** 2)) + 1e-9
            clip = (pink / rms * 0.015).astype(np.float32)

        _save_wav(out_dir / f"noise_{i:04d}.wav", clip)
        count += 1

    return count


def record_mic_samples(out_dir: Path, n: int) -> int:
    """
    Interactively record `n` real "iris" utterances from the microphone.
    The user has 3 seconds to say the word after a countdown.
    """
    try:
        import sounddevice as sd
    except ImportError:
        print("[warn] sounddevice not installed — skipping mic recording")
        return 0

    print(f"\nRecording {n} real 'iris' utterances.")
    print("Say 'iris' clearly when you see 'GO'. Each clip is 2 seconds.\n")
    count = 0

    for i in range(n):
        print(f"  [{i + 1}/{n}]  Ready in 3...", end="", flush=True)
        time.sleep(1)
        print(" 2...", end="", flush=True)
        time.sleep(1)
        print(" 1...", end="", flush=True)
        time.sleep(1)
        print(" GO")

        audio = sd.rec(
            CLIP_SAMPLES, samplerate=SAMPLE_RATE, channels=1, dtype="float32"
        )
        sd.wait()
        clip = audio.flatten()
        _save_wav(out_dir / f"real_{i:04d}.wav", clip)
        count += 1

    return count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate IRIS wake-word training data"
    )
    parser.add_argument(
        "--record",
        type=int,
        default=0,
        metavar="N",
        help="Record N real mic utterances of 'iris' (default 0)",
    )
    args = parser.parse_args()

    POS_DIR.mkdir(parents=True, exist_ok=True)
    NEG_DIR.mkdir(parents=True, exist_ok=True)

    np.random.seed(0)

    # ---- Positive samples: "iris" ----------------------------------------
    print("=== Positive samples ('iris') ===")
    pos_texts = ["iris", "Iris"]
    n_pos = generate_pyttsx3_clips(pos_texts, POS_DIR, "iris")
    print(f"  TTS clips: {n_pos}")

    if args.record > 0:
        n_rec = record_mic_samples(POS_DIR, args.record)
        print(f"  Mic recordings: {n_rec}")

    # ---- Negative samples: other words + silence -------------------------
    print("\n=== Negative samples ===")
    neg_texts = [
        # Phonetically similar / confusable
        "virus", "sirius", "lyric", "lyrics", "wrist", "serious", "curious",
        "various", "Paris", "area", "areas", "idris",
        # Common wake-word alternatives
        "hey", "hello", "okay", "computer", "jarvis", "alexa", "siri", "cortana",
        # Filler / common speech
        "yes", "no", "stop", "play", "pause", "next", "back",
        "the quick brown fox", "how are you",
    ]
    n_neg_tts = generate_pyttsx3_clips(neg_texts, NEG_DIR, "neg")
    n_neg_noise = generate_silence_noise_clips(NEG_DIR, n=300)
    print(f"  TTS clips: {n_neg_tts}")
    print(f"  Noise/silence clips: {n_neg_noise}")

    total_pos = len(list(POS_DIR.glob("*.wav")))
    total_neg = len(list(NEG_DIR.glob("*.wav")))
    print(f"\nDone.")
    print(f"  Positive: {total_pos} clips  ->  {POS_DIR}")
    print(f"  Negative: {total_neg} clips  ->  {NEG_DIR}")
    print(f"\nNext step: python voice/training/train_iris.py")


if __name__ == "__main__":
    main()
