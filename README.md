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
- `tts_align_to_object`
- `tts_get_scene_summary`
- `tts_capture_view_info`
- `tts_calibrate_view`
- `tts_focus_object_and_capture`
- `tts_wait_for_object_settle`
- `tts_get_object`
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

Write tools:

- `tts_set_camera`
- `tts_set_camera_and_capture`
- `tts_move_object`
- `tts_rotate_object`
- `tts_set_object_name`
- `tts_set_object_lock`
- `tts_spawn_builtin`
- `tts_destroy_object`
- `tts_broadcast`
- `tts_execute_action_plan`

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

The screenshot tools capture a screen rectangle using `mss`; by default they
assume TTS occupies the primary 1920x1080 display. Pass `left`, `top`,
`width`, and `height` when TTS is in another window or monitor. The combined
camera tool returns an on-demand JPEG snapshot, not a video stream.

## HTTP AI gateway

When `server.py` starts, it also exposes a local HTTP gateway:

- `GET /health`
- `POST /chat`
- `POST /v1/chat`
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

When a selected game is running, each AI request receives a best-effort live
board context. The context includes tagged object GUIDs, names, tags,
positions, rotations, and lock state. With `AI_GAME_VISION=1` (the default),
the gateway also moves the configured TTS camera and attaches a JPEG snapshot
for vision-capable backends. Configure the screen rectangle and camera with
`AI_VISION_LEFT`, `AI_VISION_TOP`, `AI_VISION_WIDTH`, `AI_VISION_HEIGHT`,
`AI_VISION_PLAYER_COLOR`, `AI_VISION_X`, `AI_VISION_Y`, `AI_VISION_Z`,
`AI_VISION_PITCH`, `AI_VISION_YAW`, and `AI_VISION_DISTANCE`. Structured tags
remain the authoritative source for exact piece identity; the image helps a
vision model resolve the visible board and verify the mapping.

For direct local Ollama use the native chat HTTP endpoint. Native Ollama vision
requests carry screenshots in the `images` base64 array, which avoids relying
on OpenAI-compatibility translation:

```powershell
$env:AI_BACKEND_KIND = "http"
$env:AI_BACKEND_URL = "http://127.0.0.1:11434/api/chat"
$env:AI_BACKEND_MODEL = "gemma4:12b"
$env:AI_BACKEND_FORMAT = "ollama"
$env:AI_BACKEND_TIMEOUT = "120"
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
contains `pending`, an `id`, and the original `payload`. The MCP chat tools are
the preferred Codex integration because they preserve the MCP session.

### D&D gameplay layer

When a game is selected with `!ai game <name>`, the gateway loads
`game_rules/<name>/rules.md` and builds an intent-aware gameplay prompt. It
uses only live top-level TTS object summaries for scene/search context. AI
responses may contain only these bounded commands:
`SPAWN`, `PLACE`, `MOVE`, `ROTATE`, `LOCK`, `UNLOCK`, `SPAWN_BUILTIN`,
`BROADCAST`, and `DESTROY`. Catalog-based `SPAWN` and `PLACE` resolution is
disabled; use live object GUIDs or built-in object spawning. Safe commands execute only while `!ai` is running; destructive
commands become persisted host approvals. Executed move/rotate/lock commands
are read back from TTS and retried up to `AI_COMMAND_RETRIES` times when
verification fails.

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
console window. Use `quick_restart.bat` to stop the existing gateway on port
8765 and start it again. Both scripts prefer `.venv\Scripts\python.exe`.
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
on its normal ports and writes child output to `tts_mcp_server.log`.

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
startup_timeout_sec = 20
tool_timeout_sec = 30
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
- Game-specific tools for D&D initiative, movement, fog, and encounter state

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
