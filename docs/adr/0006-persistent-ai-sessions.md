# ADR-0006: Persistent resumable AI sessions

## Status

Accepted

## Context

The AI may pause for host control, clarification, or destructive-action
approval, and the MCP server may be restarted while a game is in progress.
Players want `!ai start` to resume the previous session rather than losing the
AI's plan and context.

## Decision

AI session state is persisted durably and is resumable across server restarts.
`!ai start` resumes the selected session when possible. `!ai start fresh`
creates a new session and clears prior AI turn/plan state for that game.

The initial persistence implementation uses a local SQLite database. Cleanup
is manual; the system does not automatically delete old sessions.

The TTS game save-file name is the session identifier used to save and resume
state. A session record must retain the selected game/ruleset and enough save
identity metadata to detect an accidental mismatch during resume. The save
name is treated as unique among active saves.

The game must have an initial save before the AI can start or resume a
session. If the save name changes, the current permitted AI state is persisted
under the new save name as a new session record; the previous save-name
session remains available as its own history. The new session starts with fresh
AI state after inspecting and reconciling the live table; it does not inherit
the previous plan or controller state.

Persisted state may include the selected game, ruleset identity, AI player
identity, controller state, current turn state, announced plan, pending
clarification, pending host approval, and relevant bounded conversation/event
context. It must not contain hidden or private information that the AI was not
permitted to access.

The AI/session checkpoint is written after each completed turn. In-progress
turn state may be persisted for crash recovery, but a completed-turn
checkpoint is the normal durable game-progress boundary.

Pending host-approval proposals are part of the persisted state and remain
valid until approved or rejected; they do not expire automatically.

SQLite also retains an audit trail of announced plans, requested actions,
execution results, errors, approvals/rejections, plan revisions, and completed
turn outcomes. This supports review of plan-versus-execution behavior.

Setup and mapping validation diagnostics, including complete lists of missing,
duplicate, or contradictory chess tags, are also persisted in the audit trail.

For chess, persisted session state tracks captured-piece history so promotion
can select an available off-board piece without confusing it with a captured
piece.

The audit trail records every conversation the AI participates in, including
public chat and direct messages addressed to Blue. It does not record private
conversations intended for other players because those messages must never
reach the AI.

Audit records remain in SQLite and are also exposed through read-only MCP
inspection tools for review.

Direct messages addressed to Blue are represented like other conversations in
audit output; they do not receive special display treatment.

On resume, the AI must reconcile persisted state with fresh permitted
observations from the live TTS table before taking action. If reconciliation is
uncertain, it must ask for clarification.

If persisted state refers to missing or changed objects, the AI must ask the
players whether to restore the prior saved table state and resume from there,
or accept the current table state and begin from the current position. It must
not silently choose either path. Restoring the prior table is a broad-scene
mutation and requires explicit host approval before execution.

Restore proposals use the existing one-time approval protocol: the host issues
`!ai approve ACTION_ID` or `!ai reject ACTION_ID` in in-game chat.

## Open questions
