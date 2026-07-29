# Tabletop Simulator MCP server

A local MCP server that lets Codex inspect and manipulate a running Tabletop
Simulator game through TTS's External Editor API.

The living project wiki is in [docs/wiki](docs/wiki/README.md). Start with the
[roadmap](docs/wiki/roadmap.md) for implementation order and ongoing goals.

## Architecture

```text
Codex CLI / Codex IDE
        |
        | MCP over stdio
        v
server.py
        |
        | JSON to 127.0.0.1:39999
        | callbacks on 127.0.0.1:39998
        v
Tabletop Simulator

TTS chat can also POST to the local AI gateway at `127.0.0.1:8765`. The
gateway can call an HTTP model server, run a local CLI, or queue messages for
an MCP client such as Codex to consume.
        |
        v
Global Lua bridge (tts_mcp_global.lua)
```

TTS must run on the same Windows computer as this MCP server because the
External Editor API is localhost-only.

## Current product boundary

The core product is a safe MCP control plane for explicit, bounded,
game-neutral scene inspection and manipulation. The MVP proves visibility-safe
structured reads and verified reversible actions on existing visible objects:
move, rotate, rename, and lock/unlock.

Blue is the default control-plane identity, but identity is explicitly
configurable. Mutations require a current exact GUID, just-in-time
preconditions, serialized fail-fast plans, and verified post-state. Hidden or
ambiguous observations are denied before they reach the MCP client.

Chat/HTTP integration, camera and screenshots, game rules, container/zone
operations, spawning/destruction, save-file administration, and arbitrary Lua
are separate adapters or later capabilities. See the [implementation plan](docs/implementation-plan.md)
and [roadmap](docs/wiki/roadmap.md) for their validation boundaries.

## Included MCP tools

Read tools:

- `tts_ping`
- `tts_list_objects`
- `tts_describe_capabilities`
- `tts_find_nearest_objects`
- `tts_find_objects_in_region`
- `tts_measure_distance`
- `tts_get_relative_transform`
- `tts_search_scene`
- `tts_resolve_object_reference`
- `tts_register_scene_alias`
- `tts_list_scene_aliases`
- `tts_remove_scene_alias`
- `tts_inspect_container`
- `tts_get_zone_objects`
- `tts_get_snap_points`
- `tts_take_from_container`
- `tts_put_object_into_container`
- `tts_validate_scene_requirements`
- `tts_validate_zone_occupancy`
- `tts_place_adjacent_to`
- `tts_place_in_zone`
- `tts_place_in_tagged_zone` (place a piece at an invisible tagged board square, such as chess `E4`)
- `tts_align_to_object`
- `tts_get_scene_summary`
- `tts_capture_view_info`
- `tts_calibrate_view`
- `tts_focus_object_and_capture`
- `tts_wait_for_object_settle`
- `tts_get_object`
- `tts_list_objects`
- `tts_capture_view`
- `tts_recent_chat`
- `tts_wait_for_chat`
- `tts_ai_chat`
- `tts_get_scripts`
- `tts_recent_events`
- `tts_list_game_rules`
- `tts_read_game_rule`
- `tts_validate_chess_mapping`
- `tts_get_session`
- `tts_checkpoint_session`
- `tts_audit_events`
- `tts_inspect_save_file`

Write tools:

- `tts_set_camera`
- `tts_set_camera_and_capture`
- `tts_move_object`
- `tts_move_checkers_piece` (validated black-piece movement; accepts tagged square zones such as `A1`)
- `tts_rotate_object`
- `tts_set_object_name`
- `tts_set_object_lock`
- `tts_spawn_builtin`
- `tts_destroy_object`
- `tts_broadcast`
- `tts_execute_action_plan`
- `tts_edit_save_file`
- `tts_load_save_file`

`tts_get_scene_summary` provides a bounded complete-scene snapshot with rich
object summaries including bounds, motion state, velocities, transform axes,
zone membership, and container item summaries, plus counts by type, lock state,
and tag presence. For coordinated
edits, `tts_execute_action_plan` accepts up to 50 structured actions using the
same action names and argument shapes as the individual mutation tools. It
returns each operation's result, which means move/rotate/name/lock operations
also provide the post-mutation object summary. The plan tool does not expose
arbitrary Lua. `destroy_object` requires `allow_irreversible=true` in addition
to the normal user-confirmation requirement.

Action plans also support `dry_run`, per-step `preconditions` and
`postconditions`, optional settling time, and post-step verification. Use these
when a plan depends on a particular GUID, tag, lock state, or position.
Provide an `idempotency_key` when a client may retry the same request; completed
results are retained in a bounded in-memory cache and replayed without repeating
the TTS mutations.

The initial version intentionally does not expose arbitrary Lua execution.

### Numbered save editing and GUI loading

`tts_inspect_save_file` reads the default numbered save
`C:\Users\Gaming\Documents\My Games\Tabletop Simulator\Saves\TS_Save_128.json`
without changing it. `tts_edit_save_file` accepts bounded JSON Pointer
`add`/`replace`/`remove` operations. A real write requires
`allow_irreversible=true` and creates a timestamped sibling backup before the
file is atomically replaced; use `dry_run=true` to preview the hashes first.

`tts_load_save_file` then uses Windows GUI automation to open the TTS Games
menu, choose Save & Load, search for the numbered save, select it, and confirm
the load. Because TTS renders this menu in Unity rather than exposing stable
Windows controls, the tool requires four coordinate pairs relative to the
detected TTS window: `games_button`, `save_load_button`, `search_box`, and
`result_row`. The confirmation button is optional; when omitted, Enter is sent
to the confirmation dialog. Loading requires `allow_irreversible=true`, and
the result reports whether a post-load External Editor script-state callback
was observed. The callback does not identify the save filename, so the tool
also verifies that the edited file hash stayed unchanged during loading.

The documented TTS External Editor API does not provide a command to load an
arbitrary save from disk; this GUI layer is intentionally explicit and
coordinate-configured for that reason. Keep TTS focused and do not interact
with the mouse or keyboard while the load tool is running.

Persistent AI sessions and audit history are stored in a local SQLite database
at `tts_mcp_sessions.sqlite3` by default. Override the location with
`TTS_SESSION_DB`. The database stores resumable session state, completed-turn
checkpoints, bridge/chat events, and filtered audit records. Cleanup is manual.

## Game rules library

The host can maintain game-specific rules references in the local
`game_rules/` directory. The initial rules reader is intended for Markdown and
plain-text files. PDF extraction and retrieval-augmented generation (RAG) can
be added later for complex or extensive rule systems while preserving
read-only, host-managed access.

### Kill Team opponent

The first high-level game adapter targets the `Kill Team 3.0 Quick and
Easy` variant represented by the canonical `TS_Save_131.json` fixture. The AI
plays one side as an opponent using role-filtered observations, a versioned
canonical state, executable rules, semantic actions, physical dice/counters,
and map/line-of-sight validation. A versioned fixture setup profile maps the
save's native tags into canonical roles without modifying the save. It may
inspect the table like a player, but hidden opponent state is never exposed.
See the [Kill Team design](docs/wiki/killteam.md),
[ADR-0009](docs/adr/0009-killteam-semantic-opponent.md), and
[ADR-0010](docs/adr/0010-native-killteam-fixture-profiles.md).

The first implementation slice is now available through these semantic MCP
tools: `tts_killteam_setup`, `tts_killteam_observe`,
`tts_killteam_get_roster`, `tts_killteam_plan_objective_move`,
`tts_killteam_select_roster_card`,
`tts_killteam_lock_rosters`, `tts_killteam_start_setup_deployment`,
`tts_killteam_deploy_setup_operative`,
`tts_killteam_rollback_pending_deployment`,
`tts_killteam_reconcile_setup_step`,
`tts_killteam_probe_line_of_sight`, `tts_killteam_place_operative`,
`tts_killteam_deploy_test_model`,
`tts_killteam_search_deployment_names`,
`tts_killteam_activate_operative`, `tts_killteam_shoot`,
`tts_killteam_begin_setup_validation`, and
`tts_killteam_complete_setup_validation`. The dedicated snapshot uses bounded
native tag/GUID queries and scalar-safe JSON collection arguments instead of
generic whole-mod enumeration. When the Save 131 fixture profile is not used,
the runtime can enter the generic roster-card setup path: it discovers
side-tagged faction-deck containers, roster-list zones, deployed zones,
roster model containers, and deployment zones; begins in an initiative stage
that is normally resolved by `tts_killteam_roll_initiative`; allows the AI to
select one roster card at a time; locks both rosters only after faction
legality and physical model availability validate; then enforces official
alternating setup passes using one pending operative at a time. The Save 131 profile still
resolves its global snap point, staged Plague Marine, visible target, dice
stations, roster, and separate counters without modifying the save. The
resumable validation action places and verifies the operative, probes nine
physical LOS rays, resolves the four named/tagged Blue dice and invokes their
native TTS Roll operation (the roller remains an identity/recovery anchor;
mechanically inserting dice into it does not trigger its drop workflow), then
pauses. Red rolls through station `f1adc9`; only authenticated Red/host chat
acknowledgment resumes resolution. Damage is projected through the target
model's own `damage` function and its real `state.wounds` value is read back.
If collider evidence, a physical commit, or readback is ambiguous, the action
stops without an automatic retry.
The deterministic placement smoke test is exposed separately as
`tts_killteam_deploy_test_model`: it resolves the unique model whose name
contains `Plague Marine Warrior` and the unique destination tagged
`_deployment_zone_blue`. It derives both current GUIDs internally, copies the
zone's x/z coordinates while preserving the model's y coordinate, and
verifies the model's final x/z position within `0.25` TTS world units. This
zero-argument smoke test does not inspect setup, rosters, snap points, dice, or
game rules.

The bounded `tts_killteam_search_deployment_names` observation searches the
known Plague Marine, Novitiate Dialogus, and deployment names without a full
scene dump. It returns compact live summaries with GUIDs, names, tags, types,
lock state, and positions. Verify a candidate is a unique `Figurine` with the
expected `Operative` and faction tags before using its GUID for movement or
LOS. For an attack, resolve every selected die the same way, prove LOS first,
and use native die rolls rather than `putObject` into the roller. A roll with
missing face readback is an uncertain commit: recover read-only and never
automatically reroll or change wounds. Apply damage only after the defender
states whether each save is normal or critical.

The in-game AI gateway can also call the bounded `tts_killteam_setup`,
`tts_killteam_observe`, `tts_killteam_get_roster`,
`tts_killteam_plan_objective_move`, and `tts_killteam_probe_line_of_sight`
tools. The roster query reads the dedicated AI container, currently `e5adb7`,
only when the live observation lacks a needed profile or model identity. The
objective planner returns a suggested `MOVE[guid,x,y,z]` target for safe
contesting or staging around an objective. Setup is intended once per loaded
game; subsequent turns should use fresh observation and on-demand LOS probes.
For semantic roster setup, the gateway accepts `KILLTEAM_ROLL_INITIATIVE`,
`KILLTEAM_SELECT_ROSTER[contained_guid]`,
`KILLTEAM_LOCK_ROSTERS`, `KILLTEAM_START_DEPLOYMENT[operative_id]`,
`MOVE[guid,x,y,z]`, `KILLTEAM_ROLLBACK_PENDING`,
and `KILLTEAM_RECONCILE_SETUP[side_id]`. Use `KILLTEAM_ROLL_INITIATIVE` as
the first semantic setup step unless initiative has already been explicitly
overridden outside the runtime. For the initial placement test, the gateway accepts
`MOVE[guid,x,y,z]` after observing the AI roster; the runtime uses the live
figurine GUID at the move step and verifies the placement. The isolated
deployment smoke test uses
the standalone zero-argument command `KILLTEAM_DEPLOY_TEST`; it bypasses setup
and moves only the uniquely named test model to the uniquely tagged zone.
The agreed vertical-slice run uses
`KILLTEAM_VALIDATE_SETUP[action_id]`; the gateway consumes the command and
stops at the Red-defense handoff. Red or the host resumes it by saying
`Defense roll complete`.

## 1. Install the Python environment

From PowerShell:

```powershell
cd C:\path\to\tabletop-simulator-mcp
uv sync
```

Without `uv`:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install mcp mss Pillow
```

The screenshot tools prefer `mss` and fall back to Pillow screen capture if
`mss` is unavailable; by default they assume TTS occupies the primary
1920x1080 display. Pass `left`, `top`, `width`, and `height` when TTS is in
another window or monitor. The combined camera tool returns an on-demand JPEG
snapshot, not a video stream.

## HTTP AI gateway

When `server.py` starts, it also exposes a local HTTP gateway:

- `GET /health`
- `POST /chat`
- `POST /v1/chat`
- `POST /chat/tool` (bounded read-only observation calls for queue adapters)
- `POST /v1/ai/commands`
- `GET /chat/next?timeout=30` (for queue/MCP adapters)

The complete incoming-chat flow is:

```text
TTS player types !ai question
        -> Global.onChat
        -> POST http://127.0.0.1:8765/chat
        -> configured HTTP, CLI, or queue backend
        -> JSON response
        -> TTS broadcastToAll
```

All in-game chat is sent to the AI gateway so the AI can participate
proactively. Messages beginning with `!ai` are interpreted as controls or
explicit requests; ordinary public and Blue-directed chat is still available
to the configured AI backend. All chat is also forwarded to the MCP event
buffer, so Codex can inspect it with `tts_recent_chat` or wait for it with
`tts_wait_for_chat`.

The chat body is compatible with the previous Lua bridge, for example:

```json
{"message":"!ai What is on the table?","player":{"color":"White"}}
```

The gateway persists conversation history in the SQLite database configured by
`TTS_SESSION_DB` (or `tts_mcp_sessions.sqlite3` by default). In-game chat is
automatically namespaced by the selected game (`tts-game:chess`, for example),
so the AI retains both conversation context and the persisted `!ai start`
lifecycle state across messages and gateway restarts. `!ai start fresh` clears
only that game’s conversation. Use `AI_BACKEND_SYSTEM_PROMPT` for stable
instructions such as chess rules. A manual reset remains available:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/chat/reset -Method Post `
  -ContentType "application/json" `
  -Body '{"conversation_id":"tts-default"}'
```

Configure an OpenAI-compatible backend before starting Codex:

```powershell
$env:AI_BACKEND_URL = "http://127.0.0.1:11434/v1/chat/completions"
$env:AI_BACKEND_MODEL = "your-model-name"
```

The gateway also handles host-only controls in in-game chat: `!ai game <name>`,
`!ai start`, `!ai start fresh`, `!ai pause`, `!ai resume`, `!ai stop`,
`!ai status`, `!ai approve ACTION_ID`, and `!ai reject ACTION_ID`. Controls
use TTS's built-in host identity and persist controller state in SQLite.
Approval IDs are six-character uppercase alphanumeric codes using only
manually typable characters; punctuation and copy/paste are not required.
Other messages beginning with `!ai` are explicit questions for the configured
AI backend, such as `!ai check the state of the board`; they are not treated as
unknown lifecycle commands.

Chat requests begin without an object list or screenshot. The configured AI
backend receives an allowlisted read-only tool registry and may request
targeted object lookup/search, zone contents, a bounded scene summary, or the
current view when that evidence is needed. Image review is deliberate and is
limited to one screenshot per turn; failed object lookup does not automatically
capture an image. Tool calls are sequential but bounded by 4 calls and 300
seconds by default; configure these limits with
`AI_OBSERVATION_MAX_CALLS` and `AI_OBSERVATION_TIMEOUT`. AI-requested TTS
observations use a separate 300-second transport limit via
`AI_OBSERVATION_TTS_TIMEOUT`. Results are compacted
and ephemeral, and only the final natural-language response reaches TTS chat.
Screenshots capture the current view without moving a player's camera;
structured object data remains authoritative for exact identity and
coordinates. Backends with native tool calling use it directly. Generic and
CLI backends use the strict JSON fallback described in the gateway prompt.

For direct local Ollama use the native chat HTTP endpoint. The gateway sends
`keep_alive: "30m"` by default so the model remains loaded between requests;
override it with `OLLAMA_KEEP_ALIVE` or the admin panel's Ollama keep-alive
field. Native Ollama vision requests carry screenshots in the `images` base64
array, which avoids relying on OpenAI-compatibility translation:

```powershell
$env:AI_BACKEND_KIND = "http"
$env:AI_BACKEND_URL = "http://127.0.0.1:11434/api/chat"
$env:AI_BACKEND_MODEL = "gemma4:12b"
$env:AI_BACKEND_FORMAT = "ollama"
$env:AI_BACKEND_TIMEOUT = "300"
```

The selected model must already be available in Ollama. The gateway also
supports other local command adapters through `AI_BACKEND_KIND=command`, but
Hermes is not part of the normal startup path.
Replace it with the non-interactive/stdin mode of another CLI as needed.
Interactive terminal UIs generally cannot be driven reliably as a backend.

Codex is normally the MCP client rather than an HTTP completion server. To
have Codex receive player messages, use queue mode and ask Codex to call
`tts_wait_for_chat` (or `tts_recent_chat`):

```powershell
$env:AI_BACKEND_KIND = "queue"
```

External adapters can long-poll `GET /chat/next?timeout=30`; the response
contains `pending`, an `id`, the original `payload`, the tool registry, and the
observation budget. They can execute an allowlisted observation through
`POST /chat/tool` with `{"name":"tts_search_scene","arguments":{...}}`.
The MCP chat tools remain the preferred Codex integration because they preserve
the MCP session.

### General game-opponent layer

When a game is selected with `!ai game <name>`, the gateway loads
`game_rules/<name>/rules.md` and builds an intent-aware opponent prompt. The AI
acts as a normal participant playing the selected game, not as a D&D Dungeon
Master or narrator. The selected rules file is authoritative; if the AI cannot
identify its side, the active turn, or a legal action, it asks for clarification
instead of guessing. It requests live scene/search context through the
allowlisted observation tools. AI
responses may contain only these bounded commands:
`SPAWN`, `PLACE`, `MOVE`, `ROTATE`, `LOCK`, `UNLOCK`, `SPAWN_BUILTIN`,
`BROADCAST`, and `DESTROY`. When the AI needs to move an existing object, it
should emit a direct `MOVE[guid,x,y,z]` command rather than describing the move
in prose; this is the simplest and preferred movement path. Catalog-based
`SPAWN` and `PLACE` resolution is disabled; use live object GUIDs or built-in object spawning. Safe commands execute only while `!ai` is running; destructive
commands become persisted host approvals. Executed move/rotate/lock commands
are read back from TTS. A failed action is an uncertainty stop: the gateway
does not automatically retry it or execute later actions from the same
response. If a move is more than 0.5 TTS world units from its expected
position on any axis, the gateway captures a visual review for the AI; the
resulting failure is reported in player chat and the gateway waits for further
player instructions.

For a backend that expects the original request body instead of chat-completion
messages, set `AI_BACKEND_FORMAT=generic`. Use `AI_BACKEND_ECHO=1` to test the
TTS-to-HTTP path without an AI backend. The gateway listens only on localhost
by default and can be changed with `TTS_HTTP_HOST` and `TTS_HTTP_PORT`.

### Runtime trace

The server emits a readable multiline runtime trace to stderr and, by default,
to `.tmp/tts_mcp_trace.log`. Each event starts with a timestamp, event name,
trace ID, process, and thread, followed by indented fields and payloads. The
machine-readable JSON-lines sidecar is written to `.tmp/tts_mcp_trace.jsonl` by
default and can be changed with `TTS_TRACE_JSON_LOG`. Inspect recent records
through the `tts_recent_trace` tool. Set `TTS_TRACE=0` to disable tracing or
set `TTS_TRACE_LOG` to choose another human-readable log path.
Trace writes are asynchronous and best-effort: a locked or slow log file never
blocks TTS chat, bridge callbacks, or the HTTP gateway.

The Windows `quick_start.bat` console keeps tracing enabled by default and
shows live TTS, AI-message, backend-request, and AI-response events. When
running `bridge_supervisor.py`, the child server's trace stderr is mirrored to
the supervisor console while MCP protocol output remains in
`tts_mcp_server.log`.
The live console uses compact one-line summaries; full structured payloads
remain in `.tmp/tts_mcp_trace.jsonl` for detailed debugging.
Player chat contains only the AI response text. Bridge diagnostics and HTTP
errors stay in the server trace; set `MCP_DEBUG_PRINT = true` in the Lua
bridge only when Lua-side troubleshooting is specifically needed.
MCP responses use both `sendExternalMessage` and a private localhost HTTP
callback for compatibility with TTS builds that drop custom-message callbacks.
Neither transport is forwarded to player chat; scene/object data remains in
the Python trace and the AI tool result only.

With echo mode enabled, verify the gateway before opening TTS:

```powershell
$env:AI_BACKEND_ECHO = "1"
python server.py

Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:8765/chat -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"!ai bridge test"}'
```

The second request should return `text: "!ai bridge test"`. In TTS, type
`!ai bridge test`; the same text should be broadcast back into the game.

For a gateway-only diagnostic session, use `TTS_GATEWAY_ONLY=1`. This keeps
the HTTP gateway running without starting the MCP stdio transport, so it can
be tested directly from PowerShell. Normal `python server.py` startup should
be performed by the MCP client, not by typing into an interactive terminal.

On Windows, double-click `quick_start.bat` for the TTS-only launch in a new
console window. Startup first stops existing listeners on ports 8765/8770 and
older TTS MCP Python processes from this workspace, then starts one fresh
instance. Use `quick_restart.bat` for the same clean restart. Both scripts
prefer `.venv\Scripts\python.exe`.
If Hermes is installed and no `tts_mcp_backend.json` exists, quick start uses
`hermes_tts_backend.py` automatically; otherwise configure an HTTP, command,
or queue backend explicitly through `/admin`.

To verify queue mode without an AI runtime:

```powershell
$env:AI_BACKEND_KIND = "queue"
python server.py
Invoke-RestMethod http://127.0.0.1:8765/chat/next?timeout=1
```

Post a chat message from TTS, then call the endpoint again; it should return
`pending: true` and the player's message.

### Local backend control panel

Open `http://127.0.0.1:8765/admin` while the bridge is running. The local
panel can start, stop, or restart AI servicing without disconnecting the
MCP/TTS bridge. It edits and persists backend kind, URL, CLI command, model,
request format, timeout, vision capture, and system prompt in
the ignored `tts_mcp_backend.local.json` file (override with
`TTS_BACKEND_CONFIG`); `tts_mcp_backend.json` is only a starter template.

The panel discovers all installed Ollama models from Ollama's native
`/api/tags` endpoint, defaulting to `http://127.0.0.1:11434`, and also checks
OpenAI-compatible `/v1/models` endpoints when configured. Set `OLLAMA_HOST` if
Ollama runs elsewhere. Models appear as selectable entries while still
allowing a custom model name. The panel also provides a persistent conversation
log with per-conversation reset. Keep the gateway bound to `127.0.0.1` unless
access control is added; the panel is intentionally local-only.

The panel API requires `TTS_ADMIN_TOKEN` as a bearer token. Remote binding is
refused by default. If remote access is deliberately needed, set both
`TTS_HTTP_ALLOW_REMOTE=1` and a strong `TTS_HTTP_AUTH_TOKEN`; clients must send
`Authorization: Bearer <token>`. The arbitrary CLI backend is disabled by
default and requires both `TTS_ALLOW_COMMAND_BACKEND=1` and an explicit
comma-separated `TTS_ALLOWED_BACKEND_EXECUTABLES` list (for example,
`python.exe`). Do not expose the gateway directly to the Internet.

### Full process supervisor

For controls that terminate and relaunch the entire MCP server process tree,
run the supervisor instead of launching `server.py` directly:

```powershell
cd "C:\path\to\tabletop-simulator-mcp"
python bridge_supervisor.py
```

Open `http://127.0.0.1:8770/admin`. **Stop all bridge processes** terminates
the managed `server.py` process and its children; the supervisor remains alive
so Start and Restart continue to work. The supervisor launches the MCP server
on its normal ports, mirrors the live trace to the supervisor console, and
writes child output to `tts_mcp_server.log`.

## 2. Install the bridge in Tabletop Simulator

1. Start Tabletop Simulator and load a game/save.
2. Open **Modding > Scripting** or the top-bar **Scripting** editor.
3. Select the **Global** script.
4. Paste the contents of `tts_mcp_global.lua`.
5. Choose **Save & Play**.

If the mod already defines `onExternalMessage(data)`, retain its handler and
call `mcp_handleExternalMessage(data)` from it. Do not define two competing
handlers.

Do not run Atom's TTS plugin at the same time. The plugin and this MCP server
both try to listen on TCP port 39998.

## 3. Register the server with Codex

The most reliable Windows configuration uses the virtual environment's Python
executable and absolute paths:

```powershell
codex mcp add tabletop-simulator -- `
  "C:\path\to\tabletop-simulator-mcp\.venv\Scripts\python.exe" `
  "C:\path\to\tabletop-simulator-mcp\server.py"
```

Or edit `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.tabletop_simulator]
command = "C:\\path\\to\\tabletop-simulator-mcp\\.venv\\Scripts\\python.exe"
args = ["C:\\path\\to\\tabletop-simulator-mcp\\server.py"]
startup_timeout_sec = 300
tool_timeout_sec = 300
default_tools_approval_mode = "writes"
enabled = true
```

Then restart Codex. Verify with:

```powershell
codex mcp list
```

Inside the Codex terminal UI, use `/mcp`.

## 4. First test

With TTS open and the bridge installed, ask Codex:

```text
Use Tabletop Simulator tools to ping the game, then list the first 20 objects.
Do not move or modify anything.
```

Then try:

```text
Find the object named "Red Pawn", report its GUID and position, and move it
two world units along the positive X axis.
```

For visual inspection, use a request such as:

```text
Move the White camera to an overhead view centered at (0, 0, 0), capture the
TTS view, and identify the major game areas.
```

## Troubleshooting

### Runtime trace details

The human-facing `.tmp/tts_mcp_trace.log` is formatted as a readable
multiline timeline: each event starts with a timestamp, event name, trace ID,
process, and thread, followed by indented fields and payloads. The structured
JSON-lines sidecar is written to `.tmp/tts_mcp_trace.jsonl` by default and can
be changed with `TTS_TRACE_JSON_LOG`.

The shared runtime trace records server,
gateway, and supervisor startup/shutdown, AI backend requests and responses,
HTTP gateway traffic, and both directions of the TTS External Editor protocol.
Chat text is retained for debugging; credentials are redacted and
scripts/images are represented by bounded metadata rather than raw blobs.

Chat messages are forwarded from TTS through `onChat` and can be read with
`tts_recent_chat`. Use `tts_wait_for_chat` when Codex should wait for the next
message. MCP tools are request/response based, so Codex retrieves chat when it
calls one of these tools rather than receiving unsolicited messages during an
active turn.

Codex can also call `tts_ai_chat` to use the same local `/chat` gateway and
configured Hermes or OpenAI-compatible backend used by TTS.

### Port 39998 is already in use

Close Atom or another Tabletop Simulator editor plugin. Check the port with:

```powershell
Get-NetTCPConnection -LocalPort 39998 -ErrorAction SilentlyContinue
```

### Connection refused on port 39999

Start Tabletop Simulator, load a game, and open/enable scripting. Confirm with:

```powershell
Test-NetConnection 127.0.0.1 -Port 39999
```

### `tts_ping` times out

The Python side reached TTS, but the loaded game did not answer. Reinstall
`tts_mcp_global.lua` in the game's Global script and select **Save & Play**.

### Existing mod stops handling external messages

The bridge wrapper replaced the mod's existing `onExternalMessage`. Merge the
handlers as described in `tts_mcp_global.lua`.

## Recommended next extensions

- Structured card/deck operations
- Player hand inspection with privacy controls
- Snap-point and zone tools
- Dice rolling and result collection
- Save-state snapshots and restore
- Script update tools with diff/approval safeguards
- Game-specific tools for supported games, including turn state, movement, and rule validation

## Primary documentation

- Tabletop Simulator External Editor API:
  https://api.tabletopsimulator.com/externaleditorapi/
- Tabletop Simulator Object API:
  https://api.tabletopsimulator.com/object/
- Tabletop Simulator base/global API:
  https://api.tabletopsimulator.com/base/
- OpenAI Codex MCP configuration:
  https://developers.openai.com/codex/mcp
- Official MCP Python SDK:
  https://py.sdk.modelcontextprotocol.io/

### Save 128 autonomous checkers

The natural-language `Your move` prompt uses a deterministic American/English
checkers rules and alpha-beta search engine. TTS remains authoritative for
physical board facts, while the engine owns legal transitions, mandatory
captures, complete multi-jumps, promotion rules, and tactical move selection.
The gateway reconciles the user's preceding Red move before each Black turn,
verifies every landing, persists the canonical position, and stops on any
mismatch or uncertain commit. Red and Black players crown their own pieces.
Draws require an explicit offer and clear acceptance by the other player. Set
`CHECKERS_SEARCH_DEPTH` to bound search depth; the default is 8 plies.
