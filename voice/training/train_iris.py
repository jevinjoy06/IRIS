"""
Train a custom 'iris' wake-word classifier and export it as ONNX.

Reads data from:
    voice/training/data/positive/   (WAV clips containing "iris")
    voice/training/data/negative/   (WAV clips without "iris")

Writes:
    voice/models/iris.onnx
    (updates voice/config.json → wake_word_model)

Usage:
    python voice/training/train_iris.py [--epochs 30] [--batch-size 64]
"""

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VOICE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
POS_DIR = DATA_DIR / "positive"
NEG_DIR = DATA_DIR / "negative"
MODEL_OUT = VOICE_DIR / "models" / "iris.onnx"
CONFIG_PATH = VOICE_DIR / "config.json"

SAMPLE_RATE = 16_000
EMBEDDING_DIM = 96    # OWW embedding output dimension
WINDOW_FRAMES = 16    # OWW classifier input: 16 consecutive embedding frames


# ---------------------------------------------------------------------------
# Audio I/O
# ---------------------------------------------------------------------------

def load_wav_int16(path: Path) -> np.ndarray:
    """
    Load a WAV file as int16 mono at SAMPLE_RATE.
    OWW's AudioFeatures expects raw int16 at 16 kHz.
    """
    with wave.open(str(path), "r") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    # Decode samples
    if sw == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    else:
        audio = np.frombuffer(raw, dtype=np.float32)

    # Stereo → mono
    if n_ch == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)

    # Resample to 16 kHz if needed
    if sr != SAMPLE_RATE:
        try:
            from scipy.signal import resample_poly
            g = math.gcd(SAMPLE_RATE, sr)
            audio = resample_poly(audio, SAMPLE_RATE // g, sr // g).astype(np.float32)
        except ImportError:
            n_out = int(len(audio) * SAMPLE_RATE / sr)
            indices = np.linspace(0, len(audio) - 1, n_out)
            audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    # Return as int16
    return (audio * 32767).clip(-32768, 32767).astype(np.int16)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_all_embeddings(
    wav_paths: list[Path],
) -> list[np.ndarray | None]:
    """
    Extract OWW embeddings from each WAV file.

    Returns a list of (N_frames, 96) float32 arrays (or None if extraction fails).
    """
    from openwakeword.utils import AudioFeatures  # type: ignore

    af = AudioFeatures()
    results = []
    for path in wav_paths:
        try:
            audio = load_wav_int16(path)
            emb = af._get_embeddings(audio)
            if emb is not None and len(emb) > 0:
                results.append(np.array(emb, dtype=np.float32))
            else:
                results.append(None)
        except Exception as exc:
            print(f"  [warn] embedding failed for {path.name}: {exc}")
            results.append(None)
    return results


def make_windows(
    embeddings: np.ndarray, label: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Slide a WINDOW_FRAMES window over an embedding sequence.

    embeddings: (N_frames, 96)
    Returns X: (M, 16, 96), y: (M,) filled with `label`.
    """
    n = len(embeddings)
    if n < WINDOW_FRAMES:
        empty_x = np.empty((0, WINDOW_FRAMES, EMBEDDING_DIM), dtype=np.float32)
        empty_y = np.empty(0, dtype=np.float32)
        return empty_x, empty_y

    windows = [embeddings[i: i + WINDOW_FRAMES] for i in range(n - WINDOW_FRAMES + 1)]
    X = np.array(windows, dtype=np.float32)
    y = np.full(len(X), label, dtype=np.float32)
    return X, y


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

def build_model(hidden: int = 128):
    """
    Build a PyTorch DNN matching the OWW classifier architecture.

    Input:  (batch, 16, 96)
    Output: (batch, 1) — sigmoid probability
    """
    import torch.nn as nn

    class WakeWordNet(nn.Module):
        def __init__(self):
            super().__init__()
            in_dim = WINDOW_FRAMES * EMBEDDING_DIM  # 1536
            self.net = nn.Sequential(
                nn.Flatten(),
                nn.Linear(in_dim, hidden),
                nn.LayerNorm(hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.LayerNorm(hidden),
                nn.ReLU(),
                nn.Linear(hidden, 1),
                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.net(x)

    return WakeWordNet()


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_model(
    model,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int = 30,
    batch_size: int = 64,
):
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")

    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.BCELoss()

    train_ds = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.float32).unsqueeze(1),
    )
    loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    X_v = torch.tensor(X_val, dtype=torch.float32).to(device)
    y_v = torch.tensor(y_val, dtype=torch.float32).unsqueeze(1).to(device)

    best_val_loss = float("inf")
    best_state: dict | None = None

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(xb)

        model.eval()
        with torch.no_grad():
            val_pred = model(X_v)
            val_loss = criterion(val_pred, y_v).item()
            val_acc = ((val_pred > 0.5).float() == y_v).float().mean().item()

        avg_loss = total_loss / max(len(X_train), 1)
        print(
            f"  Epoch {epoch:3d}/{epochs}  "
            f"train_loss={avg_loss:.4f}  "
            f"val_loss={val_loss:.4f}  "
            f"val_acc={val_acc:.3f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    return model.cpu()


# ---------------------------------------------------------------------------
# ONNX export
# ---------------------------------------------------------------------------

def export_onnx(model, out_path: Path) -> None:
    import torch

    model.eval()
    dummy = torch.zeros(1, WINDOW_FRAMES, EMBEDDING_DIM)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["input"],
        output_names=["iris"],          # OWW uses output name as model key
        dynamic_axes={"input": {0: "batch"}, "iris": {0: "batch"}},
        opset_version=11,
        dynamo=False,                   # force legacy TorchScript exporter
    )
    print(f"  Saved: {out_path}")

    # Quick validation
    try:
        import onnx
        model_proto = onnx.load(str(out_path))
        onnx.checker.check_model(model_proto)
        print("  ONNX validation: OK")
    except ImportError:
        pass
    except Exception as exc:
        print(f"  [warn] ONNX validation: {exc}")


# ---------------------------------------------------------------------------
# Config update
# ---------------------------------------------------------------------------

def update_config(model_path: Path) -> None:
    if not CONFIG_PATH.exists():
        print(f"  [warn] {CONFIG_PATH} not found — skipping config update")
        return

    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    # Store path relative to voice/ so the pipeline can locate it
    try:
        rel = model_path.relative_to(VOICE_DIR)
    except ValueError:
        rel = model_path  # fallback: absolute

    cfg["wake_word_model"] = str(rel).replace("\\", "/")

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"  Updated {CONFIG_PATH.name}: wake_word_model = {cfg['wake_word_model']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train IRIS wake-word classifier and export to ONNX"
    )
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Mini-batch size")
    parser.add_argument(
        "--val-split", type=float, default=0.15, help="Validation fraction"
    )
    args = parser.parse_args()

    # ---- Load file lists ---------------------------------------------------
    pos_files = sorted(POS_DIR.glob("*.wav"))
    neg_files = sorted(NEG_DIR.glob("*.wav"))

    if not pos_files:
        sys.exit(
            f"No positive samples found in {POS_DIR}.\n"
            "Run:  python voice/training/generate_data.py"
        )
    if not neg_files:
        sys.exit(
            f"No negative samples found in {NEG_DIR}.\n"
            "Run:  python voice/training/generate_data.py"
        )

    print(f"Positive samples: {len(pos_files)}")
    print(f"Negative samples: {len(neg_files)}")

    # ---- Extract embeddings ------------------------------------------------
    print("\nExtracting embeddings (may take a few minutes)...")
    pos_embs = extract_all_embeddings(pos_files)
    neg_embs = extract_all_embeddings(neg_files)

    X_parts, y_parts = [], []
    for emb in pos_embs:
        if emb is not None:
            x, y = make_windows(emb, label=1)
            if len(x):
                X_parts.append(x)
                y_parts.append(y)
    for emb in neg_embs:
        if emb is not None:
            x, y = make_windows(emb, label=0)
            if len(x):
                X_parts.append(x)
                y_parts.append(y)

    if not X_parts:
        sys.exit(
            "No usable windows extracted.\n"
            "Make sure clips are at least 1.6 s at 16 kHz."
        )

    X = np.concatenate(X_parts, axis=0)
    y = np.concatenate(y_parts, axis=0)

    # ---- Shuffle and split -------------------------------------------------
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    X, y = X[idx], y[idx]

    n_val = max(1, int(len(X) * args.val_split))
    X_val, y_val = X[:n_val], y[:n_val]
    X_train, y_train = X[n_val:], y[n_val:]

    pos_count = int(y.sum())
    neg_count = len(y) - pos_count
    print(f"\nDataset: {len(X)} windows  (pos={pos_count}, neg={neg_count})")
    print(f"  Train: {len(X_train)}  |  Val: {len(X_val)}")

    # ---- Build & train model -----------------------------------------------
    print("\nBuilding model...")
    model = build_model()

    print("\nTraining...")
    model = train_model(
        model, X_train, y_train, X_val, y_val,
        epochs=args.epochs, batch_size=args.batch_size,
    )

    # ---- Export ONNX -------------------------------------------------------
    print("\nExporting to ONNX...")
    export_onnx(model, MODEL_OUT)

    # ---- Update config -----------------------------------------------------
    print("\nUpdating config...")
    update_config(MODEL_OUT)

    print(
        "\nAll done!\n"
        "Test with:  python clients/desktop/main.py\n"
        "Say 'iris' to wake the assistant."
    )


if __name__ == "__main__":
    main()
