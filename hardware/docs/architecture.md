# Hardware Accelerator Architecture

Target: Basys 3 (Artix-7 XC7A35T). Replaces the software wake-word step in IRIS with a hardware equivalent.

## Phase roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Single MAC unit (`rtl/mac_unit.v`) | **Complete** — 7/7 tests passing |
| 2 | Systolic array (chained MACs) | **Complete** — 6/6 tests passing |
| 3 | Wake-word NN (2–3 layers) on real audio | **Complete** — 4/4 tests passing |
| 3a | Custom audio front-end PCB (MEMS mic → ADC/PDM, Adom KiCad Bridge) | **Complete** — schematic + routed PCB + Gerbers generated |
| 4 | UART TX + top-level integration | **Complete** — 2 testbenches, 5/5 tests passing |

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

## Phase 3 implementation notes
- **RTL files:** `rtl/relu.v` (combinational ReLU+saturation) + `rtl/nn_2layer.v` (FSM-driven 2-layer FC network)
- **Computation:** logits = W2 · ReLU(W1 · x) — two systolic arrays chained with ReLU quantization between layers
- **Parameters:** IN_FEATURES=4, HIDDEN_SIZE=4, CLASSES=2, DATA_WIDTH=16, ACC_WIDTH=32
- **ReLU:** clips negative values to 0, saturates > 32767 to 32767, otherwise takes lower 16 bits of 32-bit accumulator
- **FSM states:** IDLE → L1_LOAD → L1_STREAM (IN_FEATURES cy) → L1_DRAIN → L2_LOAD → L2_STREAM (HIDDEN_SIZE cy) → L2_DRAIN → OUTPUT → IDLE
- **Latency:** ~15 cycles from `start` pulse to `valid_out` at 100 MHz (150 ns)
- **Resources:** 4 DSP48E1 slices for L1 (4×4) + 2 for L2 (4×2) = 6 DSPs total (90 available on XC7A35T)
- **Testbench:** `tb/tb_nn_2layer.v` (4/4); VCD in `hardware/sim/tb_nn_2layer.vcd`
- **argmax:** combinational comparison of 2 logits; outputs 1-bit class index

## Phase 3a implementation notes
- **PCB files:** `hardware/pcb/iris_mic_pmod/` (KiCad project)
- **Schematic:** `iris_mic_pmod.kicad_sch` — SPH0645LM4H MEMS mic, 100 nF + 10 µF decoupling, 0 Ω L/R select, 2×6 PMOD connector; I2S_DATA/CLK/WS as global labels
- **PCB:** 30×22 mm, 2-layer FR4 1.6 mm, ENIG; all 6 nets routed (GND, +3V3, I2S_DATA, I2S_CLK, I2S_WS, L_R)
- **Components:** U1 SPH0645LM4H, C1 100 nF, C2 10 µF, R1 0 Ω, J1 PMOD 2×6
- **Gerbers:** `iris_mic_pmod/gerbers/` — 7 layers (F.Cu, B.Cu, F/B SilkS, F/B Mask, Edge.Cuts) + PTH/NPTH drill files
- **BOM:** `iris_mic_pmod/bom.csv` — 5 component groups
- **Gerber script:** `hardware/pcb/gen_gerbers.py` — KiCad 10 pcbnew API; run with `"C:/Program Files/KiCad/10.0/bin/python.exe" gen_gerbers.py`

## Phase 4 implementation notes
- **RTL files:** `rtl/uart_tx.v` (8N1 serial transmitter) + `rtl/iris_top.v` (top-level integration)
- **UART TX:** 8N1 protocol, 115200 baud, FSM-driven (IDLE → START → DATA → STOP), 100 MHz clock divider (~868 cycles/bit)
  - Ports: `clk`, `rst_n` (active-low), `data_in[7:0]`, `send` (pulse), `tx` (output), `busy` (status)
  - Parameterized: CLK_FREQ=100 MHz, BAUD_RATE=115200 (overridable)
  - LSB-first data transmission, idle line=high, single start/stop bits
- **IRIS Top:** wraps `nn_2layer` + `uart_tx`; detects wake word (class_out=1) and sends 0x57 ('W') byte
  - Ports: `clk`, `rst_btn` (active-high), `act_in[(IN_FEATURES*DATA_WIDTH)-1:0]`, `start`, `uart_tx`, `led_wake`
  - Rising-edge detection on wake signal; latching LED on detection, reset by rst_btn
  - Inverts reset button: `rst_n = ~rst_btn` (for active-low internal logic)
  - Parameterized: DATA_WIDTH=16, IN_FEATURES=4, HIDDEN_SIZE=4, CLASSES=2, ACC_WIDTH=32
- **Testbenches:** `tb/tb_uart_tx.v` (5/5 tests) + `tb/tb_iris_top.v` (smoke test); VCD in `hardware/sim/`
  - uart_tx tests: bit transmission, busy pulse, idle line, send while busy
  - iris_top smoke test: reset, inference, neural network pipeline
- **Constraints:** `hardware/constraints/basys3.xdc` — UART TX on A18, RST on U18 (BTNC), LED_WAKE on U16

## Open design decisions
- Fixed-point number format (bit width, fractional bits) for MAC operands
- ADC vs. PDM-to-PCM for microphone interface on the PCB
- Neural net architecture for keyword spotting (size, quantization)
- PCB order timing (fab/shipping lead time)

## PCB toolchain
Phase 3a PCB design uses **Adom Bridge** (Adom Industries MCP integration that drives KiCad, Altium Designer, or Autodesk Fusion 360 from Claude). Will use the KiCad bridge — free and open-source.

## IRIS link
FPGA detects wake word → sends single byte over UART (Basys 3 onboard USB-to-serial, no external chip needed) → `voice/wake_listener.py` serial thread unblocks → normal conversation pipeline runs.
