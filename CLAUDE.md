# IRIS

Voice assistant + FPGA wake-word accelerator.

## Structure
- `voice/` — Python voice pipeline (wake word → VAD → transcription → Claude Code CLI)
- `hardware/` — Verilog FPGA accelerator (Basys 3, Artix-7 XC7A35T)

## Voice layer
- Entry points: `voice/iris_tray.py` (tray app) or `voice/wake_listener.py` (direct)
- Config: copy `voice/config.json.template` → `voice/config.json` and fill in keys
- Per-project notes live in `voice/iris_projects/` — Claude reads/writes these at runtime
- Set `KERAS_BACKEND=torch` before running (avoids a multi-hundred-MB TensorFlow install)
- Wake word: `"computer"` fallback until Picovoice `.ppn` file is trained and added

## Hardware
- Target: Basys 3 (Artix-7 XC7A35T)
- Phase 1: single MAC unit (`hardware/rtl/mac_unit.v`)
- Phase 2: systolic array
- Phase 3: wake-word NN + audio front-end PCB (KiCad)
- IRIS link: FPGA sends UART trigger → voice pipeline takes over
- Testbenches: `hardware/tb/`, constraints: `hardware/constraints/basys3.xdc`

## Secrets
Never commit `voice/config.json` — it contains the Picovoice access key.
