# AGENTS.md

## Project goal

This project provides a local Model Context Protocol (MCP) server that allows
Codex and other MCP clients to inspect and control a running Tabletop
Simulator game safely and predictably.

## Purpose

The server bridges MCP requests to Tabletop Simulator's External Editor API.
The Python process communicates with TTS over localhost, while
`tts_mcp_global.lua` runs inside the loaded game's Global script and dispatches
commands to the TTS Lua API.

The project is intended to support tasks such as:

- Inspecting objects, GUIDs, transforms, names, tags, and lock state.
- Moving, rotating, naming, locking, spawning, and destroying objects.
- Broadcasting messages to players.
- Controlling a player's camera and capturing on-demand screenshots for visual
  analysis.
- Combining structured object data with visual snapshots for reliable game
  automation.
- Executing bounded multi-step action plans with post-action state returned for
  each step.

## Architecture

```text
MCP client / Codex
        |
        | stdio MCP
        v
server.py
        |
        | JSON over localhost:39999
        | callbacks on localhost:39998
        v
Tabletop Simulator
        |
        v
tts_mcp_global.lua
```

Screenshots are captured by Python using `mss` and returned as MCP image
content. They are on-demand snapshots, not a continuous video stream.

The Python process also exposes a localhost HTTP AI gateway on port 8765.
TTS can send chat messages to `/chat`, and the gateway can forward them to an
OpenAI-compatible, Hermes, Ollama, or generic HTTP backend.

Persistent AI session/controller state and audit records are stored in a local
SQLite database. The gateway interprets host-only `!ai` lifecycle and approval
commands, while ordinary chat is forwarded to the configured AI backend for
proactive participation.

## Development guidance

- Keep the Python and Lua bridge action names synchronized.
- Prefer read/inspect tools before mutating tools.
- Identify objects by GUID rather than display name alone.
- Preserve the existing External Editor callback protocol and request IDs.
- Do not add arbitrary Lua execution without explicit safeguards and approval.
- Treat object destruction and broad scene changes as irreversible operations.
- Keep action plans bounded and allowlisted; do not expose arbitrary Lua through
  batch execution. Require explicit opt-in for destructive plan steps.
- Keep screenshot capture configurable by screen rectangle; do not assume TTS
  is always on the primary monitor in new code.
- Update this file and `README.md` when adding major tools or changing the
  bridge architecture.
- Keep `docs/wiki/roadmap.md` current when roadmap priorities, implementation
  order, safety classes, or validation requirements change.

## Repository organization and cleanliness

Keep the repository easy to navigate and safe to hand off:

- Keep production Python modules at the repository root only when they are
  top-level application entry points or shared runtime modules. Put reusable
  helpers in clearly named modules rather than growing one monolithic file.
- Keep the Lua bridge at the repository root unless the bridge architecture is
  deliberately reorganized. Python action names and Lua handler names must
  remain easy to find and compare.
- Keep tests under `tests/`, documentation under `docs/`, game-specific rules
  under `game_rules/`, and wiki material under `docs/wiki/`.
- Do not place scratch scripts, experiments, downloaded references, screenshots,
  logs, exports, or temporary reports in the repository root. Use a clearly
  named ignored directory such as `.tmp/` or an external temporary directory.
- Do not commit generated caches or local runtime state, including
  `__pycache__/`, `.pyc` files, coverage output, local SQLite databases,
  captured screenshots, model outputs, logs, virtual environments, or build
  artifacts. Add appropriate patterns to `.gitignore` when a new generated
  artifact is introduced.
- Keep examples and fixtures small, intentional, and clearly labeled. Large
  binary assets belong outside the source tree unless they are required for a
  reproducible test or documented demonstration.
- Prefer one authoritative document for each topic. Update existing README,
  ADR, validation, glossary, or wiki pages instead of creating competing notes.
- Use stable, descriptive filenames with consistent lowercase naming for new
  documentation and tests.
- Remove obsolete files, duplicate documentation, failed experiment artifacts,
  and temporary migration code after a change is complete. Never delete user
  data or an existing artifact without confirming that it is disposable.
- Before handoff, inspect the repository for unexpected new files and verify
  that only intentional source, test, documentation, and configuration changes
  remain.

## Validation

Before handing off Python changes, run:

```powershell
python -m compileall -q server.py
```

When TTS is available, also verify that the Lua bridge responds to `tts_ping`
and that camera/screenshot tools work with the intended display rectangle.
