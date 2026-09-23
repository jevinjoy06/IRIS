# Hardware Accelerator Architecture

Target: Basys 3 (Artix-7 XC7A35T). Replaces the software wake-word step in IRIS with a hardware equivalent.

## Phase roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Single MAC unit (`rtl/mac_unit.v`) | Scaffolded |
| 2 | Systolic array (chained MACs) | Not started |
| 3 | Wake-word NN (2–3 layers) on real audio | Not started |
| 3a | Custom audio front-end PCB (KiCad, MEMS mic → ADC/PDM) | Not started |
| 4 | IRIS UART integration + live demo | Not started |

## Open design decisions
- Fixed-point number format (bit width, fractional bits) for MAC operands
- ADC vs. PDM-to-PCM for microphone interface on the PCB
- Neural net architecture for keyword spotting (size, quantization)
- PCB order timing (fab/shipping lead time)

## IRIS link
FPGA detects wake word → sends single byte over UART (Basys 3 onboard USB-to-serial, no external chip needed) → `voice/wake_listener.py` serial thread unblocks → normal conversation pipeline runs.
