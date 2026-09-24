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
- Wake word → VAD recording → transcription (Moonshine) → hub WebSocket
- Set `KERAS_BACKEND=torch` before running
- Wake word: `"computer"` fallback until Picovoice `.ppn` file is trained and added
- Config: `voice/config.json.template` → `voice/config.json`

## Hardware
- Target: Basys 3 (Artix-7 XC7A35T)
- Phase 1: single MAC unit (`hardware/rtl/mac_unit.v`)
- Phase 2: systolic array
- Phase 3: wake-word NN + audio front-end PCB (KiCad)
- IRIS link: FPGA UART trigger → voice pipeline takes over
- Testbenches: `hardware/tb/`, constraints: `hardware/constraints/basys3.xdc`

## Secrets
Never commit `voice/config.json`, `hub/.env`, or `clients/*/config.json`.
