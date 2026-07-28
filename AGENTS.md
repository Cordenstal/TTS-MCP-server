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
- Running the first game-specific semantic adapter for Kill Team: tagged setup,
  role-filtered observation, validated operative placement, activation, and a
  physical-dice ranged attack.

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

`killteam_runtime.py` owns the typed Kill Team state and rules seam. It talks
to TTS only through the small `TTSKillTeamBridge` adapter, so deterministic
fake-bridge tests can validate legality and visibility without a live table.
The generic bridge remains the only Lua execution boundary; Kill Team exposes
allowlisted semantic actions rather than arbitrary scene mutations. Its LOS
adapter is an on-demand nine-ray physics query that returns first-hit evidence
and collider uncertainty; Python owns visibility policy and consumes that
evidence before shooting. Kill Team setup uses the dedicated
`killteam_list_objects` action with scalar-safe JSON tag/GUID/snap filters,
rather than the generic whole-scene listing action. A versioned Save 131
profile normalizes native fixture tags and stable support anchors without
modifying the save. The HTTP AI gateway may request only the bounded Kill Team
setup, observation, roster, and LOS-probe tools. The roster tool is fixed to
the configured dedicated AI roster container. The gateway may execute
semantic placement and the resumable Save 131 validation start; only
authenticated Red/host acknowledgment resumes the defense-roll handoff.
Activation, shooting, and other mutations remain on the semantic MCP
interface.

Screenshots are captured by Python using `mss` and returned as MCP image
content. They are on-demand snapshots, not a continuous video stream.

The Python process also exposes a localhost HTTP AI gateway on port 8765.
TTS can send chat messages to `/chat`, and the gateway can forward them to an
OpenAI-compatible, Hermes, Ollama, or generic HTTP backend.

Persistent AI session/controller state and audit records are stored in a local
SQLite database. The gateway interprets host-only `!ai` lifecycle and approval
commands, while ordinary chat is forwarded to the configured AI backend for
proactive participation.

Ordinary chat starts without automatic screenshots or object lists. The
gateway exposes only bounded, read-only observation tools to the AI backend;
the backend may request targeted scene data or the current view when needed.
Tool results are compact and ephemeral, and player-facing chat must contain
only the final natural-language response.

## Development guidance

- Keep the Python and Lua bridge action names synchronized.
- Prefer read/inspect tools before mutating tools.
- Identify objects by GUID rather than display name alone.
- For Kill Team model identification, use the bounded
  `tts_killteam_search_deployment_names` route before movement or LOS. Normalize
  TTS display-name markup for comparison, then require a unique live `Figurine`
  whose name matches the intended operative, includes the `Operative` tag, and
  has consistent faction tags. Similar-named bags, layouts, and containers are
  not models. Use the returned live GUID as authoritative; for the current
  pairing, the Plague Marine Warrior should also carry Chaos/LEGIONARY tags
  and the Novitiate Dialogus should carry NOVITIATE/Imperium tags.
- For the bundled checkers save, use the game-specific validated movement
  tool for black pieces; keep `tts_move_object` as an unrestricted primitive.
- Preserve the existing External Editor callback protocol and request IDs.
- Do not add arbitrary Lua execution without explicit safeguards and approval.
- Treat object destruction and broad scene changes as irreversible operations.
- Keep action plans bounded and allowlisted; do not expose arbitrary Lua through
  batch execution. Require explicit opt-in for destructive plan steps.
- Player-facing AI chat must contain only non-empty natural-language text. Never
  print JSON, command syntax, board/state dumps, diagnostic payloads, or blank
  and whitespace-only responses to the TTS chat.
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
