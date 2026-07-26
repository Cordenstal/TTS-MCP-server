# ADR-0004: Host approval for destructive actions

## Status

Accepted

## Context

The AI is a normal TTS player and may act autonomously on its own turn, but
generic TTS object operations can have irreversible or broad effects. Examples
include destroying objects, spawning objects, and changing broad scene state.

## Decision

Destructive or broad-scene actions require explicit host approval before the
MCP server sends them to TTS unless a separately defined safety condition
authorizes the specific action. The policy applies during autonomous play and
remains in force until intentionally revised.

The first condition-authorized exception is plan-scoped cleanup: a bounded
plan may destroy an object it created itself when the object is identified by
an exact GUID or creation token, still matches the plan's expected state, and
did not exist before the plan began. This exception does not authorize
destruction of pre-existing objects or broader cleanup.

Normal in-game actions that implement the selected rules are not treated as
destructive scene actions. For chess, a capture moves the captured piece off
the board without destroying it and does not require host approval.

If chess promotion cannot reuse an available off-board piece, spawning a
replacement piece is not exempt: the AI must request host approval and include
the color and promoted piece type in the proposal.

The approval request should identify the proposed action, target object or
scope, and expected effect. Rejection must leave the game unchanged. Approval
must be tied to the specific proposed action and must not grant unrestricted
future mutation access.

The approval exchange occurs through in-game chat. The AI announces a
human-readable proposal with a one-time action identifier; the host approves
or rejects that specific identifier in chat. The initial command syntax is
`!ai approve ACTION_ID` and `!ai reject ACTION_ID`.

Action IDs are six-character uppercase alphanumeric codes designed for manual
typing in TTS; punctuation and copy/paste are not assumed. The generator uses
only unambiguous letters and digits. Each code identifies one pending action.

An action ID remains valid until the host approves or rejects it. It does not
expire by time, and pending proposals must survive an MCP server restart.

Approval authorization uses TTS's built-in host identity. No additional
secret/token is required for the host.

While an approval is pending, the autonomous turn remains paused until the
host approves or rejects the proposal.

## Open questions

- How long should an approval remain valid?
- Which actions count as destructive or broad-scene actions?
