"""Log-mel feature extraction for keyword spotting."""

import numpy as np

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    from scipy import signal
    from scipy.fft import rfft


def extract_features(audio_np, sr=16000, n_mels=40, n_fft=512, hop_length=160,
                      win_length=400, fmin=20, fmax=8000):
    """
    Extract log-mel spectrogram from audio.

    Args:
        audio_np: float32 numpy array, normalized to [-1, 1]
        sr: sample rate in Hz (default 16000)
        n_mels: number of mel bins (default 40)
        n_fft: FFT size (default 512)
        hop_length: hop size in samples (default 160 = 10ms @ 16kHz)
        win_length: window length in samples (default 400 = 25ms @ 16kHz)
        fmin: minimum frequency (default 20 Hz)
        fmax: maximum frequency (default 8000 Hz)

    Returns:
        (40,) float32 array = mean-pooled log-mel features across all frames
    """
    audio_np = np.asarray(audio_np, dtype=np.float32)

    if HAS_LIBROSA:
        # Use librosa for log-mel spectrogram
        mel_spec = librosa.feature.melspectrogram(
            y=audio_np,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length,
            n_mels=n_mels,
            fmin=fmin,
            fmax=fmax
        )
        # Convert to dB scale
        log_mel = librosa.power_to_db(mel_spec + 1e-9, ref=1.0)
    else:
        # Fallback: manual mel spectrogram using scipy
        log_mel = _mel_spectrogram_scipy(
            audio_np,
            sr=sr,
            n_mels=n_mels,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length,
            fmin=fmin,
            fmax=fmax
        )

    # Global average pooling: (n_frames, 40) -> (40,)
    features = np.mean(log_mel, axis=1, dtype=np.float32)
    return features


def _mel_spectrogram_scipy(y, sr, n_mels, n_fft, hop_length, win_length, fmin, fmax):
    """
    Compute mel spectrogram using scipy (fallback if librosa unavailable).

    Returns:
        (n_mels, n_frames) log power spectrogram
    """
    # Create mel filterbank
    mel_fb = _create_mel_filterbank(n_mels, n_fft, sr, fmin, fmax)

    # Compute STFT
    window = signal.windows.hann(win_length)
    # Pad signal appropriately
    n_frames = 1 + (len(y) - win_length) // hop_length
    frames = []
    for i in range(n_frames):
        start = i * hop_length
        end = start + win_length
        if end > len(y):
            frame = np.zeros(win_length, dtype=np.float32)
            frame[:len(y)-start] = y[start:]
        else:
            frame = y[start:end]
        frames.append(frame)

    # Compute power spectrum for each frame
    power_spec = []
    for frame in frames:
        windowed = frame * window
        # Use rfft to get positive frequencies only
        fft_result = rfft(windowed, n=n_fft)
        power = np.abs(fft_result) ** 2
        power_spec.append(power[:n_fft // 2 + 1])

    power_spec = np.array(power_spec).T  # (n_fft//2+1, n_frames)

    # Apply mel filterbank
    mel_spec = np.dot(mel_fb, power_spec)

    # Convert to dB
    log_mel = 10.0 * np.log10(np.maximum(mel_spec, 1e-9))
    return log_mel


def _create_mel_filterbank(n_mels, n_fft, sr, fmin, fmax):
    """
    Create mel filterbank matrix.

    Returns:
        (n_mels, n_fft//2+1) filterbank
    """
    # Frequency bins
    freqs = np.linspace(0, sr / 2, n_fft // 2 + 1)

    # Mel scale conversion
    def hz_to_mel(hz):
        return 2595 * np.log10(1 + hz / 700)

    def mel_to_hz(mel):
        return 700 * (10 ** (mel / 2595) - 1)

    # Mel points
    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)

    # Convert back to Hz
    hz_points = mel_to_hz(mel_points)

    # Create filterbank
    fb = np.zeros((n_mels, len(freqs)), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = hz_points[i:i+3]
        # Left slope
        left_mask = (freqs >= left) & (freqs <= center)
        fb[i, left_mask] = (freqs[left_mask] - left) / (center - left)
        # Right slope
        right_mask = (freqs >= center) & (freqs <= right)
        fb[i, right_mask] = (right - freqs[right_mask]) / (right - center)

    return fb
