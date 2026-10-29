# Known Issues / Backlog

Tracked during the Oct 2026 conversational testing pass. Not yet fixed — come back to these.

## Behavioral issues (found, not fixed)

1. **Destructive-request suggestion nudge** — asked to delete everything in Documents,
   IRIS correctly declines (no delete tool exists) but then adds "you'll need to do
   that manually or use a shell command to remove the contents." It shouldn't nudge
   toward a destructive workaround after declining.
2. **Empty-string input → total silence** — client sends `{"type":"message","text":""}`
   and gets back nothing: no token, no error, no done. `server.py` skips the whole
   processing block when `text` strips to empty. Probably intentional (VAD false
   trigger with no speech), but not confirmed as deliberate vs. an oversight.
3. **Cold-start latency spike** — first message on a fresh connection took 7.7s to
   first token vs. ~0.5s on the second message in the same session. Suspected Ollama
   reloading the model into VRAM after idling out. Not confirmed or addressed.

## Known limitations (documented, deliberately deprioritized)

4. Ollama does not reliably honor `tool_choice` (generic or per-function) for
   `qwen2.5:14b`. Only `clipboard_read` needed a hard bypass (`_DETERMINISTIC_TOOLS`
   in `hub/brain.py`) so far. Watch for the same symptom — skipped or fabricated tool
   calls — if more tools are added.
5. Extreme-length input (50k+ chars) can still trigger language-switching even with
   `num_ctx=8192`. Judged unrealistic for real voice input (would need ~1hr+ of
   continuous speech), so not chased further.
6. `hub/tools/shell.py`'s dangerous-command blocklist is regex/pattern-based and
   bypassable (e.g. PowerShell `Remove-Item -Recurse -Force` isn't caught). Flagged
   as a security observation, not exploited, not fixed.
7. `/ws` has zero authentication and no Origin check (confirmed via grep — no
   auth/token/secret handling anywhere in `server.py`), and the hub binds `0.0.0.0`
   by default. Now that Tailscale is set up, the hub is also reachable from any
   other network this desktop joins (public wifi, etc.), not just the tailnet —
   anyone on the same LAN segment could connect and use `shell_run`/file tools with
   no credential at all. Flagged by automated security review on this session's
   commit. Worth at minimum a shared-secret handshake on connect, or restricting
   `HUB_HOST` to the Tailscale interface specifically, before this leaves a fully
   trusted network. Not fixed yet — personal-devices-only usage for now limits
   exposure, but it's still a real gap.

## Untested surface

7. The real voice pipeline (`voice/pipeline.py`): wake word → VAD → Moonshine
   transcription → TTS. Needs a live mic/speaker and a human talking to it — hasn't
   been run this session.
8. TTS (`voice/tts.py`) and transcription (`voice/transcribe.py`) in isolation, no
   mic needed — not yet tested.
9. Electron GUI client (`clients/desktop/electron`, `clients/laptop/electron`) — not
   yet launched or tested.
10. REST API beyond `/api/facts` GET/DELETE — no explicit POST/PATCH testing on
    `/api/facts` or `/api/conversations`.
11. Multi-client connectivity — hub handling more than one connected client at once
    (e.g. desktop + laptop simultaneously). Desktop-to-laptop reachability over
    Tailscale is now wired up (see below); concurrent-session behavior on the hub
    itself still untested.

## Resolved since this file was written

- **Unbounded tool-trigger keyword list** — `_needs_tools()` used to be an
  allow-list of topic keywords, which meant any topic not anticipated (e.g.
  restaurant recommendations) never got the tool list offered at all, and
  IRIS fabricated specific business names with fake review claims instead
  (confirmed live over the laptop-to-hub Tailscale connection). Fixed by
  inverting to a denylist: tools are now offered by default, suppressed only
  for a small closed set of pure-chitchat patterns (greetings, thanks,
  identity questions). `tool_choice` stays "auto" so visibility alone
  doesn't force a call. Re-verified the original regression this guarded
  against (spurious tool calls on greetings/venting) does not reappear.
  Known pre-existing quirk, not touched by this fix: `_KEYWORD_TO_TOOL`'s
  specific-tool forcing has no negation detection, so "don't search the web
  for X" still sends a forced `web_search` tool_choice — it only "works" by
  accident because Ollama doesn't reliably honor forced tool_choice.
- **`_DETERMINISTIC_TOOLS` silently dropped the rest of a compound message** —
  e.g. "what's on my clipboard, and what time did we last talk?" only ever
  answered the clipboard half; the bypass hard-returned immediately after
  dispatching the deterministic tool, both pre-model and inside the normal
  tool loop. Same root cause as the keyword-list issue above: a hardcoded
  per-tool special case that doesn't scale once requests combine intents.
  Fixed by guaranteeing dispatch (still necessary — clipboard is proven to
  fabricate even with the real result sitting in context as a plain tool
  message) but seeding the real result as an already-spoken assistant
  message instead of returning, so the loop continues and anything else in
  the message still gets a chance to be addressed. Verified: 5/5 single-intent
  clipboard trials still correct (no regression), 3/3 compound trials now
  address both parts — clipboard always correct, the second part never
  fabricated even on the 2/3 trials where it didn't call `memory_recall`.


- Tailscale is now installed and running on the desktop (node `iris-desktop`,
  `100.98.135.70`). The laptop (`jevin-legion-5`, `100.74.253.30`) was already on the
  same tailnet — the earlier note in this file blaming the laptop's IP as "this
  desktop's stale Tailscale IP" baked into `clients/laptop/config.json.template` was
  wrong; that IP was always the laptop's own node, just pointed at itself instead of
  the desktop. Fixed the template to point at `100.98.135.70`. Still need to actually
  run the laptop client against the hub over Tailscale to confirm end-to-end.

## Already fixed and verified this pass

See session history / git diff on `hub/brain.py`, `hub/memory.py`, `hub/server.py`,
`hub/tools/file_system.py`, `hub/tools/system_info.py` for the 9 bugs fixed and
verified earlier in this testing pass (system_info crash, FILE_SYSTEM_ROOT empty-string
bug, tool-trigger false positives, unbounded core-fact injection, fact-store pollution,
"close Spotify" hallucination, language garbling on tool turns, clipboard_read
deterministic hallucination, malformed-WebSocket-frame connection death).
