# Keyword Spotter ML Pipeline

Complete training and quantization pipeline for the FPGA keyword spotter.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Train the model
```bash
python train.py
```

Options:
- `--keyword yes` — keyword to detect (default: "yes")
- `--epochs 30` — number of training epochs
- `--lr 0.001` — learning rate
- `--batch 64` — batch size
- `--output weights.pt` — output model file

The script will:
- Download Google Speech Commands v2 (~2.3GB) on first run
- Extract log-mel features from audio clips
- Train a 2-layer MLP: 40 → 64 → 2
- Save the best model to `hardware/ml/weights.pt`
- Print final validation accuracy

### 3. Quantize and export weights
```bash
python quantize.py
```

This will:
- Load the trained model
- Quantize weights to INT16 (symmetric per-tensor)
- Export to Verilog .mem files:
  - `hardware/rtl/weights/w1.mem` (2560 values = 40×64 row-major)
  - `hardware/rtl/weights/w2.mem` (128 values = 64×2 row-major)
  - `hardware/rtl/weights/b1.mem` (64 values, for reference)
  - `hardware/rtl/weights/b2.mem` (2 values, for reference)
- Print scale factors needed to interpret logits in hardware

## Architecture

**Feature Extraction** (`features.py`)
- Input: 16kHz mono audio (-1 to +1 normalized)
- Process: STFT → log-mel spectrogram (40 bins)
- Output: (40,) mean-pooled features per audio clip

**Dataset** (`dataset.py`)
- Source: Google Speech Commands v2 (~2GB)
- Positive class: target keyword samples
- Negative class: random samples from other keywords + background noise mixing
- 80/20 train/val split

**Model** (`model.py`)
- 2-layer MLP: Linear(40→64) → ReLU → Linear(64→2)
- Simple, deterministic, exactly matches Verilog implementation

**Training** (`train.py`)
- Adam optimizer with CrossEntropyLoss
- Saves best model on validation accuracy
- CPU-friendly (also supports CUDA)

**Quantization** (`quantize.py`)
- Symmetric per-tensor INT16 quantization
- Formula: `scale = 32767.0 / max(|W|)`, then `W_int16 = round(W * scale)`
- Two's complement hex export for Verilog `$readmemh`

## Weight File Format

Each .mem file is plain text, one hexadecimal value per line (4 digits, two's complement):
```
0000  # zero
0001  # one
ffff  # -1
8000  # -32768 (min)
7fff  # 32767 (max)
```

### w1.mem (2560 lines)
40×64 weight matrix, row-major order:
```
Line 0:     w1[0, 0]
Line 1:     w1[0, 1]
...
Line 63:    w1[0, 63]
Line 64:    w1[1, 0]
...
Line 2559:  w1[39, 63]
```

### w2.mem (128 lines)
64×2 weight matrix, row-major order:
```
Line 0:     w2[0, 0]
Line 1:     w2[0, 1]
Line 2:     w2[1, 0]
...
Line 127:   w2[63, 1]
```

## Output Interpretation

After forward pass in hardware:
```
logits_float = [logit_0_int16, logit_1_int16] / w2_scale / b2_scale

confidence = softmax(logits_float)
prediction = argmax(confidence)  # 0 = not keyword, 1 = keyword detected
```

The scale factors are printed at the end of quantization.
