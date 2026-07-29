# ADR-0002: Generic game support with optional adapters

## Status

Accepted

## Context

The initial games are likely to be simple games such as chess or Go, but the
system should leave room for more complex Tabletop Simulator games. TTS games
vary widely in how they represent turns, rules, zones, pieces, and state.

## Decision

The core product will be a safe TTS control plane for arbitrary tables,
exposing generic observations and bounded actions: permitted object metadata,
camera snapshots, transforms, zones where available, and normal object
interaction. Requests are explicit and are subject to visibility filtering,
exact GUID mutation targets, bounded plans, destructive-action policy, and
post-action verification.

For ordinary object motion, the AI-facing command language should use explicit
`MOVE[guid,x,y,z]` instructions instead of prose descriptions. The bridge may
still translate that command into the underlying TTS Lua movement call, but
the structured move token is the preferred AI-side contract because it is short,
auditable, and maps directly to an exact GUID and target position.

Autonomous game play is not part of the generic core. It may be added through
an optional game-specific adapter that supplies rules, turn ownership, and
plan authority. External integrations such as the HTTP AI gateway are
adapters to the MCP control plane, not alternate mutation authorities.

Arbitrary Lua execution is out of scope for the generic surface.

Game-specific adapters may be added later for games where reliable play needs
structured board state, rule validation, turn detection, or specialized
actions. Chess and Go are candidate validation games, not the architectural
boundary.

## Consequences

Generic scene manipulation can be reliable without understanding game rules,
provided that object identity, visibility, preconditions, and postconditions
are explicit. The control plane must not claim that a generic action is a
legal game move. Adapter capabilities may add game semantics without changing
the generic control-plane permission model.

If the AI cannot confidently determine the active turn, game state, or legal
action, it must pause and ask the players for clarification. It must not make a
best-effort move under uncertainty. The pause persists until a player provides
an answer; there is no automatic timeout or silent forfeiture.

Turn detection uses all available evidence: the selected rules/context,
permitted visual observations of the table, and public or Blue-directed chat.
Conflicting signals are treated as uncertainty and require clarification.

When an optional adapter provides autonomous play, an autonomous turn is a
bounded loop through the turn state machine described by the selected
rules/context. The generic control plane itself has no turn state machine or
game-legality authority.

Before executing a turn, the AI announces its intended plan publicly as Blue.
The plan is an observable expectation for players to compare against the
actions taken. Destructive actions still pause for the separate host-approval
flow before execution.

If new observations or player actions invalidate the plan, the AI must stop,
announce a revised plan publicly as Blue, and only then continue. It must not
silently change strategy.

An adapter may define re-observation at state transitions, but every generic
mutation still requires structured post-state verification before it is
reported successful. A transition should identify what state to verify, what
observations are permitted, and what conditions require replanning or
clarification.

An explicit execution error or failed post-state verification stops the
current plan and requires clarification or a separately validated recovery
plan before more actions are attempted. The generic control plane reports
partial completion and does not automatically roll back completed actions.

Whichever recovery option the players choose, the AI must announce an updated
turn plan publicly before continuing.

## Open questions

- Does the host describe the game and rules at session start, or should the AI
  infer them from the table?
- How is turn ownership detected in arbitrary games?
- What is the minimum safe fallback when the AI cannot identify legal actions?
- How can a human interrupt or cancel an autonomous turn already in progress?
