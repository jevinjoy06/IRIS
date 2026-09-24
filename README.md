# IRIS

**Intelligent Responsive Interface System** — a personal voice assistant with an FPGA wake-word accelerator.

Hub-and-spoke architecture: a GPU desktop runs the hub (brain + memory), and any client device connects over WebSocket to talk to it.

---

## Architecture

```
Desktop PC (hub)
├── FastAPI + WebSocket server  ← brain lives here
├── Ollama LLM (llama3.1:8b)
├── SQLite memory
└── Web UI at http://localhost:7865

Clients (connect over Tailscale)
├── clients/desktop/  ← local UI on the same machine
└── clients/laptop/   ← connects via ws://100.74.253.30:7865/ws
```

---

## Quick Start

### 1. Hub (run on your GPU desktop)

```bash
# Install deps
pip install -r hub/requirements.txt

# Configure
cp hub/.env.template hub/.env
# Edit hub/.env — set OLLAMA_BASE_URL and OLLAMA_MODEL

# Run Ollama (separate terminal)
ollama serve
ollama pull llama3.1:8b

# Start the hub
python -m hub
# → http://localhost:7865
```

### 2. Laptop Client

```bash
pip install -r clients/laptop/requirements.txt

# Install Tailscale on the laptop, log into the same account as the desktop
# Then:
cp clients/laptop/config.json.template clients/laptop/config.json
python clients/laptop/main.py
```

---

## Repo Layout

| Path | What it is |
|---|---|
| `hub/` | FastAPI + WebSocket server, Ollama brain, SQLite memory |
| `clients/desktop/` | Local client for the GPU PC |
| `clients/laptop/` | Remote client — connects over Tailscale |
| `voice/` | Shared voice pipeline: wake word → VAD → transcription (Moonshine) |
| `hardware/` | Verilog FPGA accelerator (Basys 3, Artix-7 XC7A35T) |
| `docs/` | Design docs |

---

## Networking

Clients connect to the hub over [Tailscale](https://tailscale.com) — a free mesh VPN that gives every device a stable private IP regardless of network. No port forwarding or domain needed.

1. Install Tailscale on all devices
2. Log into the same account
3. Desktop Tailscale IP: `100.74.253.30` (set in `clients/laptop/config.json`)

---

## Hardware (FPGA Accelerator)

Target: **Basys 3** (Artix-7 XC7A35T)

| Phase | What | Status |
|---|---|---|
| 1 | Single MAC unit (`hardware/rtl/mac_unit.v`) | In progress |
| 2 | Systolic array (chained MACs) | Planned |
| 3 | Wake-word neural net on FPGA + audio front-end PCB (KiCad) | Planned |

When the FPGA detects the wake word it sends a UART trigger → voice pipeline takes over.

---

## Voice Pipeline

```
Wake word ("computer") → VAD recording → Moonshine transcription → hub WebSocket → Ollama → response
```

Set `KERAS_BACKEND=torch` before running (avoids a TensorFlow install).

Custom wake word via Picovoice Porcupine — add your `.ppn` file to `voice/` when trained.

---

## Secrets

Never commit: `hub/.env`, `voice/config.json`, `clients/*/config.json`
