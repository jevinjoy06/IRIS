# Hardware Accelerator Architecture

Target: Basys 3 (Artix-7 XC7A35T). Replaces the software wake-word step in IRIS with a hardware equivalent.

## Phase roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Single MAC unit (`rtl/mac_unit.v`) | **Complete** — 7/7 tests passing |
| 2 | Systolic array (chained MACs) | **Complete** — 6/6 tests passing |
| 3 | Wake-word NN (2–3 layers) on real audio | Not started |
| 3a | Custom audio front-end PCB (MEMS mic → ADC/PDM, Adom KiCad Bridge) | Not started |
| 4 | IRIS UART integration + live demo | Not started |

## Phase 1 implementation notes
- Parameterized: DATA_WIDTH=16, ACC_WIDTH=32; targets DSP48E1 slices on Artix-7
- Signed multiply via `$signed(a) * $signed(b)` — required for two's-complement correctness and DSP48E1 inference
- Testbench: 4 unsigned + 3 signed cases; simulated with iverilog/vvp
- VCD waveform output: `hardware/sim/tb_mac_unit.vcd`

## Phase 2 implementation notes
- **RTL files:** `rtl/pe.v` (processing element) + `rtl/systolic_array.v` (NxM array)
- **Computation:** weight-stationary y = W·x — each column produces one output neuron
- **Parameters:** ROWS=4 (dot-product depth), COLS=4 (parallel outputs), DATA_WIDTH=16, ACC_WIDTH=32
- **Dataflow:** broadcast activation to all columns; valid_in fires row 0, valid propagates down the chain (row r fires one cycle after row r-1); partial sums accumulate top-to-bottom
- **Latency:** ROWS+1 cycles from valid_in pulse to valid_out (e.g. 5 cycles for 4×4)
- **Interface:** present x[r] on act_in at cycle r; valid_in=1 only on cycle 0
- **DSP48E1:** one DSP slice per column × COLS = 4 DSPs for default 4×4 array (90 available on XC7A35T)
- **Testbenches:** `tb/tb_pe.v` (5/5) + `tb/tb_systolic_array.v` (6/6); VCD in `hardware/sim/`
- Signed arithmetic inherited from mac_unit's `$signed()` multiply

## Open design decisions
- Fixed-point number format (bit width, fractional bits) for MAC operands
- ADC vs. PDM-to-PCM for microphone interface on the PCB
- Neural net architecture for keyword spotting (size, quantization)
- PCB order timing (fab/shipping lead time)

## PCB toolchain
Phase 3a PCB design uses **Adom Bridge** (Adom Industries MCP integration that drives KiCad, Altium Designer, or Autodesk Fusion 360 from Claude). Will use the KiCad bridge — free and open-source.

## IRIS link
FPGA detects wake word → sends single byte over UART (Basys 3 onboard USB-to-serial, no external chip needed) → `voice/wake_listener.py` serial thread unblocks → normal conversation pipeline runs.
