# IRIS

Voice assistant + FPGA wake-word accelerator. Hub-and-spoke: GPU desktop runs the hub, clients (desktop/laptop) connect over WebSocket.

## Structure
- `hub/` — FastAPI + WebSocket server; Ollama brain (OpenAI-compat API); SQLite memory
- `clients/desktop/` — local client for the GPU PC (hub at localhost)
- `clients/laptop/` — remote client that connects to the hub over LAN or tunnel
- `voice/` — shared Python voice pipeline (wake word → VAD → transcription)
- `hardware/` — Verilog FPGA accelerator (Basys 3, Artix-7 XC7A35T)
- `docs/` — design docs and plans

## Hub
- Entry: `python -m hub` (reads `hub/.env`)
- Config: copy `hub/.env.template` → `hub/.env` and fill in keys
- Brain: Ollama at `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`), model `OLLAMA_MODEL`
- UI: `http://localhost:7865` (WebSocket at `/ws`)

## Clients
- Entry: `python clients/desktop/main.py` or `python clients/laptop/main.py`
- Config: copy `config.json.template` → `config.json` in the client dir and set `hub_url`
- Desktop default: `ws://localhost:7865/ws`
- Laptop: set `hub_url` to desktop LAN IP or tunnel URL

## Voice layer (shared pipeline)
- Wake word (openWakeWord) → VAD recording → transcription (Moonshine) → hub WebSocket → Ollama → Kokoro ONNX TTS
- Async pipeline: TTS non-blocking; smart session lifecycle
- Set `KERAS_BACKEND=torch` before running
- Wake word: OWW model, fallback `"computer"`; live score test: `python voice/training/test_wake_word.py`
- Config: `voice/config.json.template` → `voice/config.json`

## Hardware
- Target: Basys 3 (Artix-7 XC7A35T)
- Phase 1: MAC unit — done (`hardware/rtl/mac_unit.v`)
- Phase 2: systolic array — done
- Phase 3: 40→64→2 MLP wake-word classifier — RTL + weight ROMs done (`hardware/rtl/`)
- Phase 3a: audio front-end PCB — routed, gerbers in `hardware/pcb/iris_mic_pmod/gerbers/`; 15 DRC violations pending fix before fab
- ML training pipeline: `hardware/ml/` — quantized INT16 weights for Vivado block RAM
- IRIS link: FPGA UART trigger → voice pipeline (listener not yet wired)
- Testbenches: `hardware/tb/`, constraints: `hardware/constraints/basys3.xdc`

## Secrets
Never commit `voice/config.json`, `hub/.env`, or `clients/*/config.json`.
