"""Google Speech Commands v2 dataset loader."""

import os
import tarfile
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from io import BytesIO

try:
    import torchaudio
    HAS_TORCHAUDIO = True
except ImportError:
    HAS_TORCHAUDIO = False
    from scipy.io import wavfile

from features import extract_features


DATASET_URL = "http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz"
DATASET_SIZE = 2.3e9  # ~2.3GB


def download_dataset(data_dir="hardware/ml/data"):
    """
    Download and extract Google Speech Commands v2 if not already present.

    Args:
        data_dir: directory to extract into

    Returns:
        Path to extracted data directory
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Check if already extracted (look for a few common keywords)
    common_keywords = ["yes", "no", "up", "down"]
    if all((data_dir / kw).exists() for kw in common_keywords):
        print(f"Dataset already exists at {data_dir}")
        return data_dir

    tar_path = data_dir / "speech_commands.tar.gz"

    # Download if not present
    if not tar_path.exists():
        print(f"Downloading dataset from {DATASET_URL}")
        print(f"Size: ~2.3 GB (this may take several minutes)")

        try:
            with urlopen(DATASET_URL) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB
                data = BytesIO()

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    data.write(chunk)
                    downloaded += len(chunk)

                    # Print progress every 10MB
                    if downloaded % (10 * 1024 * 1024) == 0:
                        pct = 100 * downloaded / total_size if total_size > 0 else 0
                        print(f"  {pct:.1f}% ({downloaded / 1e9:.2f}GB / {total_size / 1e9:.2f}GB)")

                # Write to file
                with open(tar_path, 'wb') as f:
                    f.write(data.getvalue())
                print("Download complete!")

        except Exception as e:
            raise RuntimeError(f"Failed to download dataset: {e}")

    # Extract
    print(f"Extracting to {data_dir}...")
    with tarfile.open(tar_path, 'r:gz') as tar:
        tar.extractall(data_dir)
    print("Extraction complete!")

    return data_dir


def _load_audio(wav_path, sr=16000):
    """
    Load a WAV file and resample to target sample rate.

    Args:
        wav_path: path to .wav file
        sr: target sample rate (default 16000)

    Returns:
        (audio, sample_rate) as float32 normalized to [-1, 1]
    """
    if HAS_TORCHAUDIO:
        waveform, original_sr = torchaudio.load(str(wav_path))
        waveform = waveform.squeeze(0).numpy()
        if original_sr != sr:
            resampler = torchaudio.transforms.Resample(original_sr, sr)
            waveform = resampler(torch.from_numpy(waveform)).numpy()
    else:
        original_sr, waveform = wavfile.read(str(wav_path))
        waveform = waveform.astype(np.float32)

        # Normalize to [-1, 1] if using PCM int16
        if waveform.dtype == np.int16:
            waveform = waveform / 32768.0
        elif waveform.max() > 1.0:
            waveform = waveform / np.abs(waveform).max()

        # Resample if needed (simple linear interpolation)
        if original_sr != sr:
            num_samples = int(len(waveform) * sr / original_sr)
            indices = np.linspace(0, len(waveform) - 1, num_samples)
            waveform = np.interp(indices, np.arange(len(waveform)), waveform)

    return waveform.astype(np.float32), sr


def load_dataset(keyword="yes", data_dir="hardware/ml/data", val_split=0.2):
    """
    Load Google Speech Commands dataset for a specific keyword.

    Args:
        keyword: keyword to use as positive class (e.g., "yes", "no", "up")
        data_dir: directory containing extracted dataset
        val_split: fraction of data for validation (default 0.2)

    Returns:
        (X_train, y_train, X_val, y_val)
        - X shape: (N, 40) float32 log-mel features
        - y shape: (N,) int (0 or 1)
    """
    data_dir = Path(data_dir)

    # First ensure dataset is downloaded
    if not (data_dir / keyword).exists():
        print(f"Dataset not found. Downloading...")
        data_dir = download_dataset(str(data_dir))

    if not (data_dir / keyword).exists():
        raise FileNotFoundError(
            f"Keyword '{keyword}' not found in {data_dir}. "
            f"Available: {[d.name for d in data_dir.iterdir() if d.is_dir()]}"
        )

    print(f"Loading dataset for keyword: {keyword}")

    # Load positive class (target keyword)
    positive_files = list((data_dir / keyword).glob("*.wav"))
    print(f"  Positive samples: {len(positive_files)}")

    # Load negative class (random samples from other keywords)
    other_dirs = [
        d for d in data_dir.iterdir()
        if d.is_dir() and d.name != keyword and d.name != "_background_noise_"
    ]
    negative_files = []
    for other_dir in other_dirs:
        negative_files.extend(other_dir.glob("*.wav"))

    # Sample equal number of negatives as positives
    np.random.seed(42)
    if len(negative_files) > len(positive_files):
        indices = np.random.choice(len(negative_files), len(positive_files), replace=False)
        negative_files = [negative_files[i] for i in indices]
    print(f"  Negative samples: {len(negative_files)}")

    # Background noise augmentation: mix 20% of negatives with noise
    background_noise_dir = data_dir / "_background_noise_"
    noise_files = []
    if background_noise_dir.exists():
        noise_files = list(background_noise_dir.glob("*.wav"))
        print(f"  Background noise files: {len(noise_files)}")

    # Extract features and create dataset
    X = []
    y = []

    # Positive samples
    for wav_file in positive_files:
        try:
            audio, sr = _load_audio(wav_file, sr=16000)
            features = extract_features(audio, sr=16000)
            X.append(features)
            y.append(1)
        except Exception as e:
            print(f"  Warning: failed to load {wav_file}: {e}")

    # Negative samples (with augmentation)
    for i, wav_file in enumerate(negative_files):
        try:
            audio, sr = _load_audio(wav_file, sr=16000)

            # 20% chance: mix with background noise
            if np.random.rand() < 0.2 and noise_files:
                noise_file = np.random.choice(noise_files)
                noise, _ = _load_audio(noise_file, sr=16000)
                # Mix: 70% speech + 30% noise
                if len(noise) < len(audio):
                    noise = np.pad(noise, (0, len(audio) - len(noise)))
                else:
                    noise = noise[:len(audio)]
                audio = 0.7 * audio + 0.3 * noise

            features = extract_features(audio, sr=16000)
            X.append(features)
            y.append(0)
        except Exception as e:
            print(f"  Warning: failed to load {wav_file}: {e}")

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int64)

    print(f"Loaded {len(X)} samples total")

    # Shuffle and split
    indices = np.random.permutation(len(X))
    X = X[indices]
    y = y[indices]

    split_idx = int(len(X) * (1 - val_split))
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    print(f"  Train: {len(X_train)}, Val: {len(X_val)}")

    return X_train, y_train, X_val, y_val
