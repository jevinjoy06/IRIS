# Cross-Device Command Execution — Design

## Intent and why

Right now every tool the hub's brain calls (`open_app`, `focus_window`,
`list_windows`, `system_info`, etc.) executes inside the hub process itself,
on the GPU desktop. This means a request issued from the laptop client still
causes side effects on the desktop — e.g. asking IRIS to "open Google" from
the laptop opens a browser window on the desktop, not the laptop, because
the hub has no concept of "which device actually asked."

The user wants IRIS to act as a true multi-device assistant: able to execute
on whichever device makes sense for the request — the device you're talking
from by default, or an explicitly named device ("open Google on my
desktop") — and to do so with real, unrestricted command execution rather
than being limited to today's fixed tool set, so it can "do whatever it
needs to do" to satisfy a request.

## Goals

- The brain can execute arbitrary shell commands/scripts on any device
  currently connected to the hub, not just tools in the existing fixed set.
- Device targeting is a judgment call the model makes per-request from
  conversational context, the same way it already decides which tool to
  call:
  - Unqualified request → target the device the request came from.
  - Explicitly named device ("my desktop", "the laptop") → target that
    device.
  - Genuinely ambiguous → ask the user instead of guessing.
- Destructive or irreversible actions (delete, overwrite, kill process,
  format, etc.) pause and ask the user to confirm, in the conversation the
  request came from, before running — on any device.
- Everything non-destructive executes immediately with no confirmation
  step.
- Devices stay controllable even when their chat GUI isn't open: a
  lightweight background agent runs per device, independent of the
  Electron chat window's lifecycle, and stays connected to the hub.
- Trust boundary is Tailscale network membership — being a device on the
  user's tailnet is sufficient to issue and receive commands. No additional
  pairing/token layer in this iteration.

## Non-goals (explicitly out of scope this round)

- Any authentication/pairing/token layer beyond Tailscale membership.
- Mobile/phone client support. The design shouldn't preclude it later, but
  no phone agent is being built now.
- An audit UI for reviewing past executed commands.
- Sandboxing or containerizing command execution — commands run with
  whatever privileges the background agent process has (the logged-in
  user's privileges on that device).
- Cross-platform proof — both current devices (`iris-desktop` hub,
  `jevin-legion-5` laptop) are Windows. Structure the code so it isn't
  Windows-only forever, but don't build/test macOS or Linux execution now.

## Anti-goals (would make this a failure even if "technically working")

- A destructive action running without the user having a real chance to
  stop it first.
- Any party not on the Tailscale network being able to trigger execution.
- The model guessing the wrong target device silently — the user should
  always be able to tell which device something ran on.

## Constraints

- Reuse the existing hub WS-based architecture (FastAPI + WebSocket) as the
  transport — no new transport/protocol.
- This directly supersedes two items already logged in
  `docs/known-issues.md`: the bypassable shell-command blocklist, and the
  destructive-request suggestion nudge. Both need to be resolved by (or
  folded into) the new confirmation gate here, not left running in
  parallel as a second, inconsistent safety mechanism.
- **In scope**: the hub currently binds to `0.0.0.0` with no check on the
  connecting party, which means the Tailscale-only trust boundary this
  design relies on isn't actually enforced today — anyone on the same
  LAN/Wi-Fi as the hub machine can already reach it. Since this project is
  about to wire arbitrary command execution onto that same socket, closing
  this gap is in scope: bind the hub's listener to the Tailscale interface
  address only (not `0.0.0.0`), so the anti-goal ("no party outside
  Tailscale can trigger execution") is actually true rather than aspirational.

## Decisions the user made

- **Device targeting is the model's judgment call**, informed by which
  devices are currently connected — not a fixed routing rule.
- **Destructive actions require a confirmation round-trip**; non-destructive
  actions do not.
- **Trust boundary is Tailscale membership only**, for now — more may be
  added later as a separate project.
- **A persistent background agent per device**, separate from the chat
  GUI's process lifecycle, so a device stays controllable without its
  Electron window open.
- **Execution is arbitrary**, not confined to today's structured tool set —
  the model can write and run whatever command/script it decides solves the
  request.

## What's left to the builder (defaults chosen, open to challenge)

- **Protocol**: new WS message types for (a) a device agent's registration
  handshake when it connects (self-reports a device id — its hostname —
  and role), (b) a command-dispatch message from hub → target device's
  connection (command string, a `destructive` flag, a request id), (c) a
  command-result message back (stdout, stderr, exit code, request id), and
  (d) a confirmation round-trip for destructive requests that goes back to
  the *originating chat session* (which may be a different connection than
  the target device), not the target device itself.
- **Destructive classification**: the model self-declares `destructive:
  true/false` as a parameter when it generates the execute-command tool
  call — consistent with the "ambiguous judgment call" philosophy used for
  device targeting, rather than a regex/keyword matcher (the thing already
  flagged as bypassable). As a safety net in case the model mis-declares, a
  small secondary heuristic check on the literal command text (obviously
  destructive verbs/flags: `del`, `rm`, `format`, `taskkill /F`,
  `Remove-Item`, `DROP`, redirects that truncate a file, etc.) can *upgrade*
  a false → true, but never downgrade true → false.
- **Device identity**: self-reported hostname at connection time. No manual
  device registry file to maintain.
- **Background agent implementation**: a small persistent Python process
  (reusing `clients/laptop`'s existing Python dependencies/backend rather
  than standing up a second Electron instance, since it must run with no
  GUI), started at login (Windows: Startup-folder shortcut or Task
  Scheduler entry) rather than a full Windows Service, to keep setup
  simple.
- **Execution model**: each dispatched command runs in its own subprocess
  (not a persistent shell session), with stdout/stderr/exit code captured
  and a timeout so a hung command can't hang the conversation.
- **UI**: command results surface in the chat the same way existing tool
  results do today — no new result-display surface.
- **Code location**: a new `hub/tools/remote_exec.py`-style module for the
  hub-side dispatch logic, a device-connection registry addition in
  `hub/server.py`/`hub/brain.py`, and a new small agent script under
  `clients/laptop/` (or a shared location if more devices join later).

## Resolved after builder-check review

A fresh-eyes review of this document surfaced four protocol gaps that the
original draft assumed were covered but weren't. Settled here as builder
defaults:

- **Chat connections report device identity too.** Not just the background
  agent — the chat client (Electron GUI and the CLI in
  `clients/laptop/main.py`) also self-reports its hostname at connect
  time, using the same mechanism as the agent handshake. This is what
  lets the hub resolve "unqualified request → the device it came from";
  without it, that targeting default has no data to work from.
- **Friendly device names are config, not a server registry.** Each
  client's `config.json` gains an optional `device_name` field (e.g.
  `"laptop"`) set once by the user, reported alongside the hostname at
  connect time, falling back to the hostname if unset. This is what lets
  "my laptop" / "the desktop" resolve to an actual connection — a real
  hostname like `jevin-legion-5` has no lexical relationship to "laptop"
  on its own.
- **The hub is an implicit device, not a loopback connection.** The hub
  registers itself in the device registry at startup under its own
  hostname, with no WebSocket round-trip. When the resolved target is the
  hub's own id, dispatch skips the network hop and executes in-process via
  the existing tool-call path — "open Google on my desktop" from the
  laptop behaves like today's local tool execution, not a self-connect.
- **An offline named target is a normal tool error.** If the resolved
  target device isn't currently connected, the execute-command tool call
  returns an error result ("device X isn't connected right now") to the
  model, which relays it to the user in its normal response — the same
  pattern as any other tool failure today (e.g. the existing `open_app`
  failure handling).

## What's deliberately not decided yet

Nothing — the above, plus the constraint on the hub's bind address, covers
every open question raised in discussion and in review. Any further detail
(exact message field names, timeout durations, confirmation prompt
wording) is an implementation-time call, not a design-level one.
