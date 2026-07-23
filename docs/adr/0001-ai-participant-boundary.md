# ADR-0001: AI participant boundary

## Status

Accepted

## Context

The system connects an AI agent to Tabletop Simulator through a local MCP
server and a Global Lua bridge. The AI should be able to inspect the table,
find objects, use the camera, play games with human players, and communicate
through in-game chat.

The existing bridge supports read-only inspection, controlled object and
camera mutations, screenshots, chat history/waiting, and a localhost HTTP
gateway for `!ai` chat messages. It intentionally does not expose arbitrary
Lua execution.

## Decision

The AI acts as a normal Tabletop Simulator player. It has a stable player
identity and may access only information and actions available to that player
through the game's normal rules and visibility model.

The AI is represented as Player 2 using the Blue player color.

## Consequences

This requires the bridge to model player identity and enforce the normal
player boundary for hidden zones, private hands, chat attribution, camera
ownership, and game-specific actions. Host/setup operations must be separated
from the AI player's normal gameplay operations.

The AI listens to ordinary public in-game conversation and may proactively
participate. It is not limited to messages prefixed with `!ai`.

The AI may act autonomously when it is Player 2/Blue's turn. A turn controller
must determine when the AI can act, gather permitted observations, execute a
bounded sequence of actions, and announce or end the turn through normal game
interactions.

Players must be able to interrupt or pause autonomous behavior through an
explicit in-game chat control, such as `!ai stop` or `!ai pause`.

Only the TTS host may issue pause, stop, or resume controls. Other players'
messages may be conversational input but cannot alter the AI controller state.

Host-only commands are authorized using Tabletop Simulator's built-in host
identity; the system does not add a separate secret or token.

If a non-host attempts a host-only command, the AI publicly explains that it
cannot follow the instruction because only the TTS host is authorized.

`pause` suspends the current autonomous turn for later continuation. `stop`
cancels the current turn; the AI remains inactive until the host explicitly
restarts it.

Camera movement is part of the AI player's normal observation behavior. The AI
may reposition its own camera and request on-demand snapshots at any time,
including outside its turn, subject to the same pause/stop controls. Camera
movement does not change other players' cameras and must not bypass the normal
Blue player's visibility/privacy boundary.

## Open questions

- How should the system handle games where Player 2/Blue is unavailable?
- Can it read only information visible to that seat, including its private
  hand?
- What relevance, turn-taking, and rate limits prevent disruptive chatter?
- Should the AI be silent during active human turns unless directly relevant?
- How is the active turn detected for games with no standard turn tracker?
- What stops an autonomous turn from looping or making unbounded actions?
- Which players may pause, stop, or resume the AI?
- Which actions require human approval before execution?
- Should the AI be allowed to act autonomously between chat messages?
