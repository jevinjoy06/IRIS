"""INT16 quantization and weight export for Verilog."""

import argparse
import torch
import numpy as np
from pathlib import Path
from model import KeywordMLP


def quantize_weights(model_path="hardware/ml/weights.pt", output_dir="hardware/rtl/weights"):
    """
    Load trained model, quantize to INT16, and export as .mem files.

    Args:
        model_path: path to trained model (weights.pt)
        output_dir: directory to write w1.mem and w2.mem

    Returns:
        dict: {w1_scale, w2_scale, b1_scale, b2_scale}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load model
    print(f"Loading model from {model_path}")
    model = KeywordMLP(in_features=40, hidden=64, classes=2)
    state_dict = torch.load(model_path, map_location='cpu')
    model.load_state_dict(state_dict)

    weights = model.get_weights()

    # Quantize weights
    print("\nQuantizing weights to INT16...")
    scales = {}
    quantized = {}

    # W1: (64, 40) but we store row-major, so shape is (40, 64) in memory
    w1 = weights['w1'].numpy()  # (64, 40) from nn.Linear
    w1_transposed = w1.T  # (40, 64) for memory layout
    w1_max = np.abs(w1_transposed).max()
    w1_scale = 32767.0 / w1_max if w1_max > 0 else 1.0
    w1_quantized = np.round(w1_transposed * w1_scale).clip(-32768, 32767).astype(np.int16)
    scales['w1'] = w1_scale
    quantized['w1'] = w1_quantized
    print(f"  w1 (40×64): max={w1_max:.6f}, scale={w1_scale:.6f}")

    # B1: (64,)
    b1 = weights['b1'].numpy()
    b1_max = np.abs(b1).max()
    b1_scale = 32767.0 / b1_max if b1_max > 0 else 1.0
    b1_quantized = np.round(b1 * b1_scale).clip(-32768, 32767).astype(np.int16)
    scales['b1'] = b1_scale
    quantized['b1'] = b1_quantized
    print(f"  b1 (64,): max={b1_max:.6f}, scale={b1_scale:.6f}")

    # W2: (2, 64) -> transpose to (64, 2) for memory layout
    w2 = weights['w2'].numpy()  # (2, 64) from nn.Linear
    w2_transposed = w2.T  # (64, 2) for memory layout
    w2_max = np.abs(w2_transposed).max()
    w2_scale = 32767.0 / w2_max if w2_max > 0 else 1.0
    w2_quantized = np.round(w2_transposed * w2_scale).clip(-32768, 32767).astype(np.int16)
    scales['w2'] = w2_scale
    quantized['w2'] = w2_quantized
    print(f"  w2 (64×2): max={w2_max:.6f}, scale={w2_scale:.6f}")

    # B2: (2,)
    b2 = weights['b2'].numpy()
    b2_max = np.abs(b2).max()
    b2_scale = 32767.0 / b2_max if b2_max > 0 else 1.0
    b2_quantized = np.round(b2 * b2_scale).clip(-32768, 32767).astype(np.int16)
    scales['b2'] = b2_scale
    quantized['b2'] = b2_quantized
    print(f"  b2 (2,): max={b2_max:.6f}, scale={b2_scale:.6f}")

    # Write .mem files
    print("\nWriting weight files...")
    _write_mem_file(output_dir / "w1.mem", w1_quantized)
    print(f"  {output_dir / 'w1.mem'} ({w1_quantized.size} values)")

    _write_mem_file(output_dir / "w2.mem", w2_quantized)
    print(f"  {output_dir / 'w2.mem'} ({w2_quantized.size} values)")

    # Also save biases for reference (not used in FPGA inference, but useful for testing)
    _write_mem_file(output_dir / "b1.mem", b1_quantized)
    print(f"  {output_dir / 'b1.mem'} ({b1_quantized.size} values)")

    _write_mem_file(output_dir / "b2.mem", b2_quantized)
    print(f"  {output_dir / 'b2.mem'} ({b2_quantized.size} values)")

    print("\nScale factors (for logit interpretation):")
    print(f"  w1_scale = {w1_scale:.6f}")
    print(f"  b1_scale = {b1_scale:.6f}")
    print(f"  w2_scale = {w2_scale:.6f}")
    print(f"  b2_scale = {b2_scale:.6f}")

    return scales


def _write_mem_file(path, data):
    """
    Write quantized weights to Verilog .mem file.

    Format: one value per line, in 4-digit hex (two's complement)

    Args:
        path: output file path
        data: 1D or 2D numpy int16 array
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Flatten if needed
    if data.ndim > 1:
        data = data.flatten()

    with open(path, 'w') as f:
        for val in data:
            # Convert to two's complement hex
            hex_str = format(val & 0xFFFF, '04x')
            f.write(hex_str + '\n')


def main():
    parser = argparse.ArgumentParser(description="Quantize and export weights")
    parser.add_argument("--model", type=str, default="hardware/ml/weights.pt",
                        help="Path to trained model")
    parser.add_argument("--output", type=str, default="hardware/rtl/weights",
                        help="Output directory for .mem files")
    args = parser.parse_args()

    quantize_weights(model_path=args.model, output_dir=args.output)
    print("\nQuantization complete!")


if __name__ == "__main__":
    main()
