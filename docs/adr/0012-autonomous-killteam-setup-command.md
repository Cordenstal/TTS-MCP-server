# ADR-0012: Add a single autonomous Kill Team setup command

## Status

Accepted

## Context

Kill Team setup already had bounded low-level actions for inspecting live
objects and committing an exact model placement. The AI must own tactical
selection and placement reasoning; the runtime must remain the validation and
execution boundary.

Requiring the AI to emit several separate setup commands in sequence is noisy
and brittle. It also leaks the implementation shape of the setup state machine
into chat prompting, even though the runtime already knows how to choose the
next AI card and the next tactical deployment slot.

## Decision

Treat the chat-level `KILLTEAM_AUTORUN_SETUP` message as an AI setup request,
not as an executable runtime macro. The AI observes the live placement bridge,
selects one AI model and one tactical position for that turn, emits one
`MOVE[guid,x,y,z]`, and stops until a new setup request is sent. The gateway
translates that `MOVE` into the setup runtime's verified placement path, which
uses the bridge's move alias for the actual TTS commit while keeping the
placement-only bridge narrow. The setup bridge keeps the same three Lua
actions and does not add a dedicated reload-check action; `setup_ping` proves
loaded-vs-disk parity by reading the active Global script and comparing its
hash to the checked-in bridge source.

- The runtime validates GUID ownership, coordinate shape, movement, and
  post-placement readback.
- The chat gateway forwards the setup request to the AI backend and consumes
  only the AI's bounded placement command.
- The host lifecycle command `!ai start fresh` clears the controller's setup
  history so a new setup pass starts from scratch.
- Lower-level setup commands remain available for manual control, debugging,
  and tests, including the compatibility `setup_place_model` form.

## Consequences

The AI owns the tactical decision at every placement while the runtime keeps
the mutation safe and testable. Human models remain human-placed.

The setup planner now persists which AI operatives were already placed during
the current session, and it derives aggressive-versus-conservative deployment
style from faction tags so teams like Legionary and Tau do not use the same
slot scoring.

The tradeoff is a resumable turn-by-turn AI interaction instead of a single
deterministic runtime macro. This preserves AI agency while keeping every
mutation bounded and verifiable.

## Alternatives rejected

- Keep the setup flow strictly stepwise in chat: this obscures the AI's actual
  tactical choices.
- Move tactical selection into the runtime: that removes the AI's reasoning
  from the placement decision.
- Hide setup behind a Lua macro: that would make the behavior harder to test and
  less visible to the Python runtime.
