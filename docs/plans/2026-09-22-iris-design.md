# IRIS — Full System Design
*2026-09-22*

IRIS (Intelligent Responsive Interface System) is a personal AI hub that runs across all your devices — voice at your desk, app on your phone, chat on any laptop — with one brain, one memory, and one identity everywhere.

---

## Architecture

Hub-and-spoke. The GPU PC is the hub — it runs the IRIS server, holds all memory, executes all tools, and calls the Claude API. Every device is a spoke — a lightweight client that sends input and receives responses over WebSocket.

```
                    ┌──────────────────────────────────────┐
                    │            GPU PC (Hub)               │
                    │                                       │
                    │  ┌─────────────────────────────────┐  │
                    │  │  Voice Client                   │  │
                    │  │  [Basys 3 FPGA] ──UART──►       │  │
                    │  │  VAD → Moonshine transcription  │  │
                    │  │  → IRIS Server (WebSocket)      │  │
                    │  └─────────────────────────────────┘  │
                    │                                       │
                    │  ┌─────────────────────────────────┐  │
                    │  │     IRIS Server                 │  │
                    │  │  FastAPI + WebSocket            │  │
                    │  │  Claude API (brain)             │  │
                    │  │  SQLite (world model)           │  │
                    │  │  Tool Layer                     │  │
                    │  └─────────────────────────────────┘  │
                    └──────────────┬────────────────────────┘
                                   │ Cloudflare Tunnel
                    ┌──────────────┼──────────────┐
                    │              │               │
               Mobile app    Other laptops    iMessage/Twilio
               (Flutter)     (laptop agent)   (existing bridges)
```

---

## Brain

**Claude API** — one model, always on. One consistent personality and memory regardless of which device is talking to IRIS. Model is hot-swappable (local via Ollama as a future option) but IRIS is always one coherent identity. Not a chatbot routing layer — one brain.

---

## Memory

IRIS doesn't remember conversations. It knows your life.

A persistent **world model** lives in SQLite on the GPU PC and is continuously updated:

| Layer | What it stores |
|---|---|
| You | Name, preferences, devices, people you mention |
| Tasks & commitments | Deadlines, to-dos, things IRIS is handling |
| Active projects | What you're working on, status, relevant files |
| Learned context | Your file structure, recurring patterns, how you like things done |

**How it works:**
- After every turn, Claude extracts any facts worth keeping and writes them to the world model
- Each call injects only the top relevant facts — not a full dump
- Hard token budget: ~2,000 tokens max for memory injection per call
- Three tiers: Core (always injected, ~200 tokens), Relevant (fetched per query, ~500 tokens), Archive (never injected, searchable on demand)
- Nightly consolidation: merges duplicates, archives stale facts, marks completed tasks done
- Facts decay: accessed less than once in 90 days below importance threshold → archived automatically

---

## Tool Layer

Tools are Python classes registered on the hub. Claude calls them when it decides to.

**Day 1 tools:**

| Tool | Capability |
|---|---|
| `file_system` | Read/write files on the GPU PC |
| `web_search` | Tavily web lookups |
| `calendar` | Google Calendar — read, create, update |
| `email` | Gmail — read, compose, send |
| `code_exec` | Run code on the GPU PC |
| `memory_write` | Save/update a fact in the world model |
| `memory_recall` | Search the world model on demand |
| `notify` | Push a message to all active devices |

**Cross-device file access:** Each laptop runs a lightweight IRIS agent (~100 lines of Python) connected to the hub via WebSocket. When IRIS needs to touch files on that machine, it sends the command to the agent. No SSH, no VPN — same Cloudflare Tunnel.

**Self-generating tools:** When IRIS can't fulfill a request, it researches how, writes the tool, shows it to you once for approval, then saves it permanently. Over time IRIS builds a personal tool library shaped by what you actually ask it to do. Approval required once per new tool before it runs anything that touches files, sends messages, or calls external services.

**Workflows:** Multi-step recurring tasks (morning briefing, deadline reminders) are written by IRIS on request and scheduled via a background job.

---

## Input Channels

| Channel | Interaction | Notes |
|---|---|---|
| Voice (GPU PC desk) | Wake word → always-on, hands-free | FPGA hardware wake word (Phase H3); Picovoice fallback until then |
| Mobile app | Tap to talk or type | Flutter — new build |
| Desktop / other laptops | Browser web UI | Served by hub — no install |
| iMessage | Text IRIS like a contact | Existing bridge, refactored |
| Phone call | Call a number, it answers | Twilio, existing, refactored |

Response mirrors input: voice → TTS + text, chat → text (TTS optional), iMessage → text reply.

IRIS always knows which device sent the request — enabling "send this to your phone" or "open that file on your laptop."

---

## The JARVIS Feel

Four things that make IRIS feel alive rather than functional:

1. **Personality** — defined once in the system prompt, consistent across every channel and device. Tone, name, brevity, how she addresses you. Never changes.

2. **Streaming** — responses start appearing immediately. On voice, TTS speaks the first sentence while the rest is still generating. On chat, it types in real time.

3. **Proactive push** — a background process watches the world model for things worth surfacing unprompted: upcoming deadlines, watched tasks completing, important emails arriving. IRIS speaks up.

4. **Brevity** — short answers unless depth is asked for. Actions confirmed in one line. Never re-explains what you already know.

---

## Build Order

Two parallel tracks — software and hardware — independent until Phase H4 where the UART trigger slots into the voice client.

### Software Track

**Phase 1 — The Hub**
FastAPI server, WebSocket support, Claude API with tool calling, SQLite world model, memory extraction, `file_system` + `web_search` tools, simple browser web client, Cloudflare Tunnel.
*End state: IRIS is usable from a browser on your GPU PC.*

**Phase 2 — Daily Driver**
Refactor voice client to send transcribed text to hub (replaces Claude Code CLI path), add `calendar` + `email` tools, memory retrieval + injection fully working, streaming responses, TTS on voice client.
*End state: IRIS is your real desk experience.*

**Phase 3 — Multi-Device**
Flutter mobile app (voice + chat), lightweight laptop agent for cross-device file access, push notifications to all devices, iMessage + Twilio refactored as hub clients.
*End state: IRIS is everywhere.*

**Phase 4 — Tool Synthesis**
Tool generation + single-approval flow, workflow scheduler, nightly memory consolidation.
*End state: IRIS grows its own capabilities.*

### Hardware Track (parallel, starts now)

**Phase H1** — Single MAC unit in Verilog, testbench, simulate in Vivado
**Phase H2** — Systolic array (chained MACs)
**Phase H3** — Wake-word neural net (2–3 layers) running on FPGA
**Phase H3a** — Custom audio front-end PCB (KiCad, MEMS mic → ADC/PDM)
**Phase H4** — UART integration with voice client — hardware and software meet

The hardware track is IRIS's entry into hardware engineering: RTL design, FPGA bring-up, timing closure, hardware/software co-design. Each phase is a concrete deliverable.

---

## What This Is Not

- Not a chatbot with conversation history
- Not a multi-model routing layer (one brain, always)
- Not cloud-hosted (your data stays on your GPU PC)
- Not JARVIS V2 — that is legacy. Everything is IRIS.
