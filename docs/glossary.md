# Glossary

## AI agent

The model-driven participant or assistant that reasons about the current TTS
game and requests observations or actions through MCP.

## External Editor API

Tabletop Simulator's localhost JSON request/callback interface used by the
Python process to communicate with the running game.

## Global Lua bridge

The `tts_mcp_global.lua` script installed in the TTS Global script. It
dispatches external commands to the TTS Lua API and forwards chat events.

## MCP server

The Python `server.py` process exposing structured TTS tools to Codex or
another MCP client over stdio.

## AI gateway

The localhost HTTP service on port 8765 that receives `!ai` messages from TTS
and forwards them to a configured AI backend, then broadcasts the response in
game chat.

## Observation

A read-only view of game state, such as object metadata, recent chat, events,
or an on-demand screenshot.

## Action

A state-changing operation, such as moving, rotating, spawning, locking,
destroying, naming an object, changing the camera, or broadcasting chat.

## Hidden information

Game state that should not automatically be visible to every participant,
including private hands, concealed zones, deck contents, or game-specific
secrets.

## AI player identity

The in-game identity reserved for the AI: Player 2, represented by the Blue
color.

## Proactive participation

The AI may respond to ordinary public chat based on conversational relevance,
without requiring a command prefix such as `!ai`.

## Autonomous turn

A bounded period in which the AI detects that Player 2/Blue may act, observes
permitted state, takes game actions, and concludes without a human prompt.

## Game-specific adapter

An optional integration that adds structured state, rule validation, turn
detection, or specialized actions for one game without changing the generic
TTS bridge.

## Game rules library

The host-managed local `game_rules/` directory containing read-only references
that the AI uses to understand the active game's rules and conventions.

## Active ruleset

The host-selected game and rules reference governing the current AI session.
It can only be changed through an explicit host control command.

## Autonomous session

The host-controlled period in which the AI is enabled to observe, chat, and
act as Player 2/Blue. It begins only after `!ai start`.

## Fresh session

A new AI session started by the host with `!ai start fresh`, clearing prior
AI turn and plan state for the selected game.

## Resumable session

An AI session whose controller state, plan, and permitted context are stored
durably and can be restored after a server restart, subject to reconciliation
with the live TTS table.

## Resume reconciliation

The comparison between persisted AI/session state and the current TTS table.
If objects differ, the AI asks whether to restore the prior state or continue
from the current table. Restoration requires host approval.

## Session database

The local SQLite database storing durable AI session state. Old sessions are
removed manually.

## Save session ID

The TTS game save-file name used as the persistent session identifier for
saving and resuming AI state.

## Object mapping

The runtime association between TTS object names/tags and game entities such
as chess pieces or board squares. GUIDs may be discovered dynamically.

## Rule provenance

The file, section, page, or retrieved source supporting a rule-based answer or
move decision. Provenance is available on request.

## Uncertainty stop

The safety behavior that pauses autonomous action and asks the players for
clarification whenever the AI cannot confidently identify a legal action,
state, or turn owner. The pause persists until a player responds.

## Turn evidence

The combined rules/context, permitted visual state, and chat signals used to
determine whether Player 2/Blue may act.

## Turn state machine

The rules-defined sequence of states and actions used to carry out one
autonomous turn and determine when that turn is complete.

## Turn plan

The AI's publicly announced intended sequence of actions for its current turn,
used to make plan-versus-execution behavior observable. If invalidated, the AI
must announce a revised plan before continuing.

## Execution error

An explicit failure returned by Tabletop Simulator or the bridge for a
requested action. It stops the autonomous turn until the AI can clarify or
recover safely. The AI reports it publicly and asks before retrying or choosing
a different action.

## AI control command

An explicit in-game chat command used to pause, stop, or resume autonomous AI
behavior. These commands are host-only.

Successful control commands produce a public confirmation; unauthorized
attempts receive an explanation.

## AI status

The host-requested public summary of active game, session/controller state,
current turn, pending approval, and pause reason.

It also includes complete chess mapping validation diagnostics when relevant.

## Decision explanation

A concise player-facing rationale for an AI action, provided when requested;
it is not a dump of private internal reasoning. It follows the channel where
the request was made.

## Request priority

The ordering used when multiple players request AI attention at once. Host
requests have highest priority.

## Turn-boundary queue

The rule that conversational requests wait until the current autonomous turn
reaches a boundary instead of interrupting execution. Host safety controls are
an exception.

## Immediate control response

A status response or host-command confirmation delivered immediately rather
than waiting in the conversational queue.

## Audit trail

Persistent records of AI plans, actions, outcomes, errors, approvals, and
revisions used to review behavior over time. It is available in SQLite and
through read-only MCP inspection tools.

## Pause

A host control state that suspends the current AI turn and allows it to resume
later.

## Stop

A host control that cancels the current AI turn and leaves the AI inactive
until explicitly restarted.

## Host approval

Explicit confirmation for a specific destructive or broad-scene action before
the server sends that action to Tabletop Simulator. In this system it is
issued by the host through in-game chat and applies to one action ID.

Host identity is determined by TTS's built-in player identity.

## Action ID

A one-time identifier attached to a single pending host-approval proposal.
It is a short, manually typed alphanumeric code.

## AI camera

The Player 2/Blue player's camera, which the AI may reposition and capture for
its own visual observations at any time, without changing other players' views
or bypassing normal visibility/privacy rules.

## Anti-cheating boundary

The hard rule that the AI must not receive hidden, private, or concealed game
information belonging to other players. Uncertain observations are withheld.

## Direct message

A private in-game chat message addressed to one player. The AI may receive
messages addressed to Player 2/Blue but not messages addressed to others.

The AI may also send direct messages as Player 2/Blue to individual players.
