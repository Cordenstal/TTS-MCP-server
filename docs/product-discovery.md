# AI-to-Tabletop Simulator discovery

## Initial goal

Connect an AI to Tabletop Simulator so it can play games with human players,
find and manipulate items, use the camera for visual understanding, and
communicate through in-game chat.

## Known system shape

- Python MCP server communicates with TTS over the External Editor API.
- Global Lua bridge dispatches commands and forwards chat.
- Screenshots are on-demand screen captures, configurable by rectangle.
- Chat can be read by MCP tools and can invoke the local AI gateway with
  `!ai`.
- Arbitrary Lua execution is intentionally out of scope for the current
  bridge.

## Current design focus

The first unresolved product boundary is whether the AI is a normal player,
a privileged assistant, or a hybrid with explicitly granted capabilities.
This must be settled before designing hidden-information access, approvals,
autonomy, and auditability.

## Interview log

### 2026-07-22

- User goal: AI should play games with users, find items, use the camera, and
  communicate through in-game chat.
- Existing implementation: structured MCP bridge plus localhost chat gateway.
- Decision: the AI behaves as a normal TTS player, with a stable identity and
  no privileged access to hidden or host-only game state.
- Decision: the AI is Player 2 and uses the Blue color.
- Decision: the AI should proactively participate in ordinary public chat,
  without requiring an explicit command prefix.
- Decision: the AI should act autonomously on its own turn.
- Decision: the first release should support arbitrary TTS games through
  generic observation/action tools. Chess and Go are likely early games, while
  game-specific adapters remain optional future improvements for complex or
  rule-sensitive games.
- Decision: a human player will identify the game and tell the AI where its
  rules are located. The server will expose a host-managed local `game_rules/`
  directory through read-only MCP access.
- Decision: Markdown and plain text are the initial supported formats. PDF
  extraction and RAG will be future sources for complex or extensive rules,
  behind the same read-only game-rules boundary.
- Decision: the AI should be able to cite the relevant rule source when a
  player requests it, but should omit citations from ordinary chat by default.
- Decision: whenever the AI is unclear about the active turn, game state, or
  legal move, it must ask for clarification rather than guessing.
- Decision: an unanswered clarification pauses the AI indefinitely until a
  player responds; it does not time out or silently forfeit.
- Decision: players need an explicit in-game chat command to pause or stop the
  AI during autonomous behavior.
- Decision: only the TTS host may issue pause, stop, or resume commands.
- Decision: pause suspends the current turn for later continuation; stop
  cancels the current turn and requires a new host command to restart.
- Decision: destructive actions such as destroying objects, spawning objects,
  or changing broad scene state require host approval for now.
- Decision: approval happens through in-game chat. The AI will present a
  human-readable proposal with a one-time action ID, and the host will approve
  or reject that specific proposal.
- Decision: the commands are `!ai approve ACTION_ID` and
  `!ai reject ACTION_ID`.
- Decision: pending approval pauses the autonomous turn indefinitely until the
  host responds.
- Decision: the AI may reposition its own camera and capture snapshots at any
  time, including outside its turn.
- Decision: the AI must never view or receive other players' hidden, private,
  or concealed information. Filtering must happen before observations reach
  the model; if permission is unclear, the observation is withheld.
- Decision: the AI may receive private messages addressed directly to Player
  2/Blue, but not private messages addressed to other players.
- Decision: the AI may send private messages to individual players as Blue.
- Decision: the active game and ruleset must be selected with an explicit
  host-only in-game command, preventing ordinary conversation from changing
  games accidentally.
- Decision: `!ai game <name>` resolves `<name>` to `game_rules/<name>/`. That
  folder contains the game's rules and supporting context.
- Decision: if the folder is missing or ambiguous, the AI must refuse to start
  autonomous play, explain that it could not find the rules, and ask the
  player to create the appropriate folder/ruleset.
- Decision: the AI determines its turn using the rules/context folder, visual
  table observations, and in-game chat. Conflicting signals require it to ask
  for clarification.
- Decision: the AI completes a bounded loop through the rules-defined turn
  state machine, then announces publicly as Blue that its turn is complete.
- Decision: the AI announces its intended plan publicly before execution so
  players can compare the plan with what it actually does.
- Decision: if the plan becomes invalid, the AI must stop, announce a revised
  plan, and then continue.
- Decision: the AI re-observes at state transitions defined by the selected
  rules/context, rather than after every individual action.
- Decision: successful TTS responses are treated as completed actions between
  transitions; explicit execution errors stop the turn before further action.
- Decision: after an error, the AI states the error publicly and asks whether
  to retry or pursue a different action. It never retries automatically.
- Decision: after a recovery choice, the AI announces an updated turn plan
  before continuing.
- Decision: the host must explicitly issue `!ai start` after selecting a valid
  game/ruleset to enable autonomous play.
- Decision: `!ai start` resumes the previous session when possible; `!ai start
  fresh` explicitly clears prior state and starts a new session.
- Decision: sessions are persistent and resumable across server restarts.
  Resuming requires fresh permitted observations and reconciliation with the
  live TTS table before the AI acts.
- Decision: persistent state will use a local SQLite database, with manual
  cleanup and no automatic retention policy.
- Decision: the TTS game save-file name is the identifier used to save and
  resume a session. Save names are treated as unique among active saves.
- Decision: the game requires an initial save before AI play. If the save name
  changes, current permitted AI state is saved under the new name as a new
  session while the old session remains separate.
- Decision: a renamed-save session begins with fresh AI state after inspecting
  and reconciling the live table; it does not inherit the prior plan or
  controller state.
- Decision: when resumed state references missing or changed objects, the AI
  asks whether to restore the prior saved table state or accept the current
  table state and begin from there.
- Decision: restoring the prior table state requires explicit host approval as
  a broad-scene/destructive action.
- Decision: restore proposals use the existing one-time `ACTION_ID` approval
  commands.
- Decision: SQLite AI/session state is checkpointed after each completed turn.
- Decision: action IDs are short, simple alphanumeric codes that players can
  type manually because TTS does not support copy/paste.
- Decision: generated action IDs are six-character uppercase alphanumeric
  codes using unambiguous manually typable characters.
- Decision: action IDs remain valid until explicitly approved or rejected and
  do not expire automatically, including across server restarts.
- Decision: host-only commands use TTS's built-in host identity and require no
  additional secret/token.
- Decision: a non-host attempting a host-only command receives a public
  explanation that the AI cannot follow it because only the host is
  authorized.
- Decision: successful host commands such as `!ai pause`, `!ai resume`,
  `!ai stop`, and `!ai start` produce public confirmation messages.
- Decision: the host has an explicit `!ai status` command showing the active
  game, session state, current turn, pending approval, and pause reason.
- Decision: the AI provides concise decision explanations on request, without
  exposing private internal reasoning.
- Decision: explanations use the request channel—public questions receive
  public replies, while direct messages receive private replies.
- Decision: requested rule citations follow the request channel as well; they
  are public for public requests and private for direct requests.
- Decision: when multiple requests arrive, the AI prioritizes the host.
- Decision: direct messages addressed to Blue take priority after host
  requests, ahead of ordinary public conversation.
- Decision: ordinary public messages are handled first-in/first-out.
- Decision: queued conversational requests wait until the AI reaches a turn
  boundary and do not interrupt autonomous execution. Host control commands
  remain immediate safety controls.
- Decision: direct messages to Blue also wait until a turn boundary and do not
  interrupt autonomous execution.
- Decision: queued messages are answered at the boundary before the AI begins
  its next autonomous turn.
- Decision: queued messages are processed by priority first, then first-in/
  first-out within each priority class.
- Decision: status responses and host-command confirmations bypass the normal
  conversational queue and appear immediately.
- Decision: SQLite retains a full audit trail of AI plans, actions, errors,
  approvals/rejections, revisions, and completed-turn outcomes.
- Decision: the audit log records all conversations the AI participates in,
  including public chat and direct messages addressed to Blue. Private
  conversations for other players are excluded.
- Decision: audit records are available both in the local SQLite database and
  through read-only MCP tools.
- Decision: direct messages addressed to Blue are treated like ordinary
  conversations in audit output.
- Decision: MCP audit review supports filters by session, turn, event type,
  and time range.
- Decision: audit records do not need a separate export format; review stays
  in SQLite and through read-only MCP tools.
- Decision: chess is the first validation game. Go and more complex games are
  deferred until the generic flow is proven.
- Decision: the system includes a starter ruleset for standard chess in
  `game_rules/chess/rules.md`. The loaded save must still provide its
  table-specific board/object mapping and side assignment.
- Decision: chess pieces and board locations are mapped using TTS object
  names/tags, with GUIDs resolved dynamically rather than hard-coded.
- Decision: pieces use names such as `White King`/`Black Pawn` and tags such as
  `chess-piece white king`; squares use tags such as `chess-square e4`.
- Decision: missing, duplicate, or contradictory chess tags pause the AI and
  require the players to repair the table before play continues.
- Decision: chess mapping validation is automatic when the game is selected or
  started; no separate validation command is required.
- Decision: invalid mapping feedback lists every missing, duplicate, or
  contradictory tag.
- Decision: full validation diagnostics are included in `!ai status`.
- Decision: validation diagnostics are also persisted in the SQLite audit
  trail.
- Decision: Player 2/Blue plays White in the initial chess save. The side must
  remain explicit in save-specific context for future games.
- Decision: the initial save uses standard White-side orientation, with
  White's back rank nearest the Blue camera and conventional square
  coordinates.
- Decision: chess tag matching is case-insensitive; lowercase forms remain
  canonical for documentation and diagnostics.
- Decision: malformed and unknown chess tags are listed as validation errors
  alongside missing, duplicate, and contradictory tags.
- Decision: legal chess moves move the source piece object to the destination
  square; captures and special moves use additional object operations.
- Decision: chess captures are normal gameplay, require no host approval, and
  move the captured piece off-board instead of destroying it.
- Decision: the initial save does not require named capture areas; captured
  pieces only need to be moved off the main board.
- Decision: captured pieces are arranged neatly off-board and grouped by
  color, keeping captured White and Black pieces visually distinct.
- Decision: TTS physics drift or incorrect placement is an execution error;
  the AI reports it and asks whether to retry or choose a different action.
- Decision: the AI announces its promotion choice in the turn plan and
  proceeds automatically; no extra confirmation is required.
- Decision: promotion reuses an existing off-board piece of the selected type;
  it does not spawn a new object.
- Decision: promotion candidates do not use a dedicated tag; they retain the
  normal color/type tags.
- Decision: the SQLite session tracks captured-piece history so promotion can
  distinguish available off-board pieces from captured pieces.
- Decision: if no suitable piece is available, spawning a replacement requires
  host approval and the proposal identifies the color and piece type.
- Decision: an approved promotion spawn receives the standard chess name/tag
  and is verified at the next state transition.
- Decision: castling is one announced chess action containing coordinated king
  and rook movements, verified together.
- Decision: en passant is one announced action containing the capturing pawn's
  move and the captured pawn's off-board movement.
- Decision: resignation and draw agreements are recognized from clear
  ordinary conversation, not special commands; ambiguous statements require
  clarification.
- Decision: the host has final authority over a draw decision. A draw offer
  alone does not end the game; the AI waits for a clear host decision.
- Decision: host draw decisions use clear ordinary chat wording rather than a
  dedicated command.
- Decision: the first end-to-end chess validation is a smoke test, not a full
  game.
- Decision: the smoke test covers tag validation, `!ai game chess`,
  `!ai start`, one legal Blue move with a public plan, turn completion,
  SQLite checkpointing, audit events, and `!ai status`.
- Decision: implementation proceeds through SQLite sessions/audit, rules MCP
  tools, host chat controls/queues, chess mapping validation, autonomous turn
  loop, and smoke-test verification in that order.
### 2026-07-25

- Decision: the primary product is a safe MCP control plane for explicit,
  bounded inspection and manipulation of live TTS scenes, not a generic
  autonomous game-playing framework.
- Decision: bounded scene action plans are first-class, but plans are
  scene-only, exclusive, fail-fast, capped at 20 steps and 60 seconds, and
  never automatically rolled back or queued behind another plan.
- Decision: reversible MVP mutations are limited to moving, rotating,
  renaming, and locking/unlocking existing visible objects.
- Decision: natural-language references are read-only discovery hints;
  mutations require a current, unique exact GUID and just-in-time
  preconditions.
- Decision: numeric postconditions use 0.05 world-unit position tolerance and
  1-degree-per-axis rotation tolerance by default; callers may request only
  stricter tolerances.
- Decision: Blue is the default control-plane identity. Host-only identity
  changes occur only at plan/session boundaries and invalidate pending work.
- Decision: visibility filtering is defense-in-depth and deny-by-uncertainty
  before MCP or gateway exposure; host identity does not grant a generic
  privileged-observer mode.
- Decision: destructive exceptions are host-managed, versioned, and audited;
  the first allowed exception is plan-scoped cleanup of objects created by
  that plan, never pre-existing objects.
- Decision: save editing/loading, chat/HTTP gateway, camera/screenshots,
  spawning/destruction, game rules, and arbitrary Lua are outside the MVP and
  require separate capabilities.
- Decision: results and failures carry versioned schemas, freshness metadata,
  stable failure classes, and audit correlation. Audit records remain in
  local SQLite until explicit host-controlled cleanup.
- Decision: restart or uncertain bridge state enters read-only recovery;
  unknown commits are never retried automatically.
- Decision: validation uses deterministic fake-bridge tests by default and
  opt-in live-TTS smoke tests against a dedicated game-neutral fixture.
- Decision: implementation begins with the capability registry and schemas,
  then the fake bridge, executor, compatibility tests, and live fixture.
