# IRIS — Full Project Doc

*IRIS = Intelligent Responsive Interface System. Consolidated from past chats — the voice assistant pipeline, wake-word naming, the JARVIS V2 predecessor it grew out of, and the hardware accelerator plan.*

---

## 0. How the pieces fit together

1. **JARVIS V2** — the original assistant: Google ADK backend + Flutter desktop app, multi-channel (chat, iMessage, Twilio calls), with the ILI industrial data pipeline as its flagship feature.
2. **IRIS** — the newer, lighter voice-interface layer at `claude-voice-assistant`: wake word → VAD recording → transcription → **Claude Code CLI** → spoken/printed response. Officially named **IRIS — Intelligent Responsive Interface System**.
3. **Hardware accelerator** — an FPGA doing the wake-word detection step in silicon instead of software, triggering the same kind of handoff IRIS already does.

Open question carried over from last time this was discussed: is IRIS the active line going forward (Claude Code CLI-based, simpler), with JARVIS V2 (ADK/Flutter) parked/legacy — or are both still active for different purposes?

---

## 1. IRIS — name & wake word

- Name locked in: **IRIS — Intelligent Responsive Interface System**
- Rolled out across the project: 3 files edited, pushed to the laptop
- Wake word: currently falls back to **"computer"** until the custom IRIS `.ppn` wake-word file is trained and dropped in via the **Picovoice console** (Porcupine) — not blocked on this to start testing
- Next moves flagged at the time: confirm Claude Code CLI is installed and logged in, get the Picovoice access key into `config.json`
- Note: an earlier attempt trained a custom wake word via the `dscripka/openWakeWord` Colab notebook instead of Picovoice and hit real bugs (broken `generate_samples` dependency, `torchaudio` API change) — that attempt was parked in favor of the built-in **"hey jarvis"** fallback at the time. The Picovoice/Porcupine `.ppn` route above looks like the current path forward instead — worth confirming which wake-word pipeline (openWakeWord vs. Picovoice) IRIS is actually on now, since both have come up.

---

## 2. IRIS — voice interface layer (architecture)

Repo: `claude-voice-assistant` at `C:\Users\jevin\source\repos\claude-voice-assistant`

### Pipeline
Wake word → VAD recording → transcription → **Claude Code CLI** → response (spoken/printed). Simpler and lighter than the ADK/Flutter path — no persistent backend server, just a CLI call per turn.

### Session model
Every fresh wake word starts a **brand-new Claude Code CLI session** (no `--continue`) — intentional fix (v4) to stop conversations from growing unbounded. Continuity across separate conversations comes from Claude reading/writing its own per-project notes files in `iris_projects\`, not from resuming old sessions.

### Instant acknowledgment (v8)
`quick_ack` ("Okay Jevin, getting right on it") used to print immediately on every turn, even near-instant ones. Now: the Claude Code CLI call runs in a background thread while a short timer (`ack_delay_seconds`, default `1.5`) runs alongside it — if Claude answers before the timer, no filler prints; if still working past that, the ack prints. `ack_delay_seconds: 0` restores old always-ack behavior.

### System tray app (`iris_tray.py`)
So IRIS doesn't need a terminal window or manual venv activation every time:
- `wake_listener.py`'s main loop refactored into `run_listener(config, pause_event, stop_event)` — runs under pause/stop control instead of only Ctrl+C
- `iris_tray.py` runs the listener in a background thread with a tray icon — right-click to pause/resume or quit; left-click also toggles pause/resume
- `SETUP_TRAY.md` covers: installing `pystray`/`Pillow`, testing with console visible first, switching to windowless `pythonw.exe`, and a PowerShell snippet for a Windows Startup shortcut. Pointing directly at the venv's `pythonw.exe`/`python.exe` means the venv never needs manual activation again.

### claude.ai Projects integration — not possible
Explored having IRIS write its project notes into an actual claude.ai Project instead of local markdown. Confirmed: **no official API or MCP connector exists** for claude.ai's consumer Projects feature — web-app-only, no public documented interface. Staying with the local `iris_projects\*.md` notes approach (already works, browsable in Explorer/VS Code).

### MCP filesystem server setup
`claude mcp add` kept failing on the `-y` flag regardless of quoting — turned out unrelated to flag parsing. Real fix: add the `filesystem` MCP server directly to `C:\Users\jevin\.claude.json`'s top-level `mcpServers` block, using `"command": "cmd", "args": ["/c", "npx -y ..."]` (bare `npx` fails on Windows since it's a `.cmd` shim) — same pattern the other working servers there already used.

**Security note (still open):** the `.claude.json` pasted into a past chat contained live API keys in plaintext (GitHub PAT, Tavily, Firecrawl, Stripe test key). These should be rotated since they were exposed in chat, if not already done.

### Local environment bugs — found & fixed
| Issue | Fix |
|---|---|
| `useful-moonshine @ git+https://...` failed to install (repo restructured upstream, no `setup.py`/`pyproject.toml` at root) | Pinned to `useful-moonshine==20241016` from PyPI instead — same API, no git clone needed |
| `webrtcvad` failed to build (needs MSVC C++ Build Tools, not installed) | Swapped to `webrtcvad-wheels` (prebuilt, same `import webrtcvad` name) |
| `ModuleNotFoundError: No module named 'tensorflow'` when transcribing | `useful-moonshine`'s Keras dependency defaults to TensorFlow backend; forced `KERAS_BACKEND=torch` at the top of `wake_listener.py` (torch already installed, avoids a multi-hundred-MB TensorFlow install) |
| `'claude' is not recognized` calling Claude Code CLI | Stale PATH in a terminal opened before Claude Code was installed — fixed with a fresh terminal window |
| Wake word + VAD recording worked, but transcription kept returning "heard nothing usable" | Pulled `_last_clip.wav` directly and analyzed it — clip was ~99% silence (max amplitude 567 of ~32,000). Not a code bug — pointed at a microphone input level problem (wrong default input device, input volume too low/muted, or a physical mute switch) |

### Current status
- Pipeline (wake word → VAD → transcription → Claude Code CLI → response) is code-complete, confirmed working end-to-end at least once ("Did you figure out what time it is?" heard and processed correctly)
- **Outstanding:** confirm the microphone input level fix, then a clean end-to-end retest
- Tray app + Startup-shortcut setup are built and documented but not yet confirmed tested
- Wake word: waiting on Picovoice access key + trained `.ppn` file; "computer" is the working fallback in the meantime
- Confirm Claude Code CLI is installed and logged in (flagged as a next step)

---

## 3. JARVIS V2 — ADK + Flutter (predecessor / possibly parallel)

### V1 — core
- **Ollama** for on-device LLM inference (no API calls, fully local)
- **Whisper** for speech-to-text
- Basic voice + text command handling

### V2 — production expansion

**ADK Backend (`jarvis_adk/`)**
- Built on **Google ADK** (Agent Development Kit), FastAPI server on port 8000
- **LiteLLM** for swapping model backends: Featherless.ai (OpenAI-compatible), Gemini, or any OpenAI-compatible endpoint
- `jarvis_agent/agent.py` defines a `root_agent` with 15+ registered tools
- `ili_api.py` runs as a **separate FastAPI service on port 8001** for the ILI pipeline — keeps LLM-routing separate from structured data APIs

**Flutter Frontend (`jarvis_app/`)**
- macOS + Windows desktop app, Flutter/Dart
- Talks to the ADK backend via `AdkService` (REST + WebSocket)
- Falls back to a local `AgentOrchestrator` (ReAct-style: LLM → tool call → execute → feed back) if ADK is unreachable
- Runs a **local HTTP bridge server on port 8765** for native OS tools that can't run inside the ADK Python process (Google Docs, calendar, email)
- State management via `ChatProvider`, `SettingsProvider`, `IliProvider`, etc.

**Input channels**
- Flutter chat UI (main interface)
- **iMessage bridge** (`imsg_bridge.py`) — watches Messages via `imsg` CLI tool, checks allowlisted phone numbers + "JARVIS" prefix, routes to ADK, replies via iMessage, keeps session IDs for context continuity
- **Twilio phone calls** (`voice_server.py`) — FastAPI server, answers via TwiML, gathers speech, routes to ADK, speaks the reply back (custom date/time formatting)

**Native OS tools (via the 8765 bridge)**
- `open_url`, `send_email`, `read_calendar` / `create_calendar_event` (Google Calendar API, natural-language date parsing), `read_emails` / Gmail API, `create_google_doc`

### ILI Pipeline — the flagship feature
Industrial pipeline inspection data analysis:
- Loads multi-decade inspection data (Excel: 2007 / 2015 / 2022 runs)
- Aligns girth welds across runs using piecewise linear interpolation (`scipy`) to correct odometer drift
- Matches anomalies across runs by distance, clock position, feature type, depth similarity, with confidence scoring
- Calculates corrosion growth rate (%/year) with severity classification (normal → critical)
- **DBSCAN clustering** (`scikit-learn`) for spatial anomaly clusters
- LLM-powered growth predictions + risk assessment via Featherless API
- Flutter UI: 5 tabs (Overview, Alignment, Matches, Growth, Predictions) with `fl_chart` visualizations

**Where AI is deliberately *not* used:** alignment, matching, and growth-rate calculation are deterministic algorithms — accuracy is safety-critical there. LLMs are scoped to the narrative/prediction layer only.

### Architectural rationale
- **Local inference over cloud API:** privacy + latency + no per-call cost, traded against being hardware/model-limited
- **FastAPI + ADK instead of calling the LLM straight from Flutter:** decouples tool execution from UI — Python gets pandas/scipy/sklearn/Google APIs, Flutter handles UX and native OS integration, the 8765 bridge covers the gap
- **Multi-model backend support:** cost/capability tradeoff — route heavy ILI analysis to a bigger model, simple tool calls to something cheap, LiteLLM makes it a one-line swap
- **Modular tool design:** each tool self-contained, add/remove without touching the core

---

## 4. Hardware accelerator (new, in planning)

### What it is
A small AI accelerator in Verilog that does real-time wake-word detection in hardware, then hands off to the existing IRIS/JARVIS software stack. Ongoing, all-year personal project, run in parallel with the ALU/RISC-V CPU pipeline — no hard deadline like those.

### Why this project
- Same category of problem AMD/NVIDIA's AI accelerator chips solve — MAC-heavy, dataflow-oriented compute
- Hits real AMD/Intel/Qualcomm intern posting skills: RTL design, FPGA bring-up/timing closure, board design & signal integrity, hardware/software co-design (via the IRIS link)
- Self-directed, connected to something already built and used — not an assigned project
- Directly replaces the software wake-word step in IRIS's pipeline with a hardware equivalent — same trigger, same handoff pattern

### Architecture (input → compute → output)

**1. Audio front-end (custom PCB, KiCad)**
- MEMS microphone → anti-aliasing filter → ADC or PDM-to-PCM → clean digitized audio into the FPGA
- Status: not yet designed

**2. FPGA compute (Basys 3, Artix-7 XC7A35T)**
- Phase 1: single MAC (multiply-accumulate) unit in Verilog
- Phase 2: chain MACs into a small systolic array
- Phase 3: small neural net (2-3 layers) for keyword spotting, running on real audio from the PCB
- Status: not started — begins once the ALU project (due Oct 31) wraps

**3. Link back to IRIS software**
- Interface: UART, via the Basys 3's onboard USB-to-serial chip (simplest option, board supports it natively, a wake-word trigger only needs to send a small signal — SPI considered but unnecessary)
- On detection: FPGA sends trigger over UART → IRIS process (listening on serial) takes over for the conversation/command handling
- Status: not yet implemented

### Phase timeline
| Phase | What | Status |
|---|---|---|
| 1 | MAC unit in Verilog | Not started |
| 2 | Systolic array (chained MACs) | Not started |
| 3 | Wake-word neural net on FPGA + audio front-end PCB | Not started |
| 3a | Custom audio front-end PCB (KiCad) | Not started |
| 4 (stretch) | Full IRIS integration over UART, live demo | Not started |

### Relationship to the other project pipeline
Runs in parallel with, not instead of:
- HDLBits practice
- ALU with testbench (due Oct 31, 2026)
- Single-cycle RISC-V CPU on Basys 3 (due Dec 31, 2026)
- Pipelined RISC-V stretch (due Feb 28, 2027)

### Open questions / decisions still needed
- Exact neural net architecture for keyword spotting (size, quantization scheme)
- ADC vs. PDM-to-PCM for the mic interface
- Fixed-point number format for the MAC units
- Timing for ordering the PCB (fab/shipping lead time)

---

## 5. Open questions across the whole stack
- Is IRIS the active going-forward architecture, with JARVIS V2 parked/legacy — or are both still being developed for different purposes?
- Wake word: openWakeWord (parked, buggy Colab notebook) vs. Picovoice/Porcupine `.ppn` (mentioned as the current path, key + trained file still pending) — which is actually the live approach?
- `.claude.json` API keys exposed in a past chat (GitHub PAT, Tavily, Firecrawl, Stripe test key) — confirm these have been rotated
- Microphone input level issue on IRIS — confirmed fixed?
- Claude Code CLI install/login — confirmed?
- Picovoice access key in `config.json` — added yet?

## 6. Notes
*(build logs, blockers, part numbers, things that broke, things you learned — add as you go)*
