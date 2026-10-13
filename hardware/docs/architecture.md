# Hardware Accelerator Architecture

Target: Basys 3 (Artix-7 XC7A35T). Replaces the software wake-word step in IRIS with a hardware equivalent.

## Phase roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Single MAC unit (`rtl/mac_unit.v`) | **Complete** — 7/7 tests passing |
| 2 | Systolic array (chained MACs) | Next up |
| 3 | Wake-word NN (2–3 layers) on real audio | Not started |
| 3a | Custom audio front-end PCB (MEMS mic → ADC/PDM, Adom KiCad Bridge) | Not started |
| 4 | IRIS UART integration + live demo | Not started |

## Phase 1 implementation notes
- Parameterized: DATA_WIDTH=16, ACC_WIDTH=32; targets DSP48E1 slices on Artix-7
- Signed multiply via `$signed(a) * $signed(b)` — required for two's-complement correctness and DSP48E1 inference
- Testbench: 4 unsigned + 3 signed cases; simulated with iverilog/vvp
- VCD waveform output: `hardware/sim/tb_mac_unit.vcd`

## Open design decisions
- Fixed-point number format (bit width, fractional bits) for MAC operands
- ADC vs. PDM-to-PCM for microphone interface on the PCB
- Neural net architecture for keyword spotting (size, quantization)
- PCB order timing (fab/shipping lead time)

## PCB toolchain
Phase 3a PCB design uses **Adom Bridge** (Adom Industries MCP integration that drives KiCad, Altium Designer, or Autodesk Fusion 360 from Claude). Will use the KiCad bridge — free and open-source.

## IRIS link
FPGA detects wake word → sends single byte over UART (Basys 3 onboard USB-to-serial, no external chip needed) → `voice/wake_listener.py` serial thread unblocks → normal conversation pipeline runs.
