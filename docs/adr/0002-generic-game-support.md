# ADR-0002: Generic game support with optional adapters

## Status

Accepted

## Context

The initial games are likely to be simple games such as chess or Go, but the
system should leave room for more complex Tabletop Simulator games. TTS games
vary widely in how they represent turns, rules, zones, pieces, and state.

## Decision

The core AI integration will target arbitrary TTS games through generic
observations and actions: public chat, permitted object metadata, camera
snapshots, transforms, zones where available, and normal object interaction.

Game-specific adapters may be added later for games where reliable play needs
structured board state, rule validation, turn detection, or specialized
actions. Chess and Go are candidate validation games, not the architectural
boundary.

## Consequences

Generic play will be less reliable than an adapter and may require players to
explain or confirm game state. The AI needs explicit uncertainty handling and
must avoid claiming a move is legal when it cannot verify the rules. Adapter
capabilities should improve reliability without changing the player identity
or permission model.

If the AI cannot confidently determine the active turn, game state, or legal
action, it must pause and ask the players for clarification. It must not make a
best-effort move under uncertainty. The pause persists until a player provides
an answer; there is no automatic timeout or silent forfeiture.

Turn detection uses all available evidence: the selected rules/context,
permitted visual observations of the table, and public or Blue-directed chat.
Conflicting signals are treated as uncertainty and require clarification.

An autonomous turn is a bounded loop through the turn state machine described
by the selected rules/context. When the end condition is reached, the AI
announces publicly as Blue that it has completed its turn. It must not rely on
an arbitrary action-count limit as the definition of completion.

Before executing a turn, the AI announces its intended plan publicly as Blue.
The plan is an observable expectation for players to compare against the
actions taken. Destructive actions still pause for the separate host-approval
flow before execution.

If new observations or player actions invalidate the plan, the AI must stop,
announce a revised plan publicly as Blue, and only then continue. It must not
silently change strategy.

The AI re-observes the table at state transitions defined by the selected
rules/context rather than after every individual action. A transition should
identify what state to verify, what observations are permitted, and what
conditions require replanning or clarification.

Between defined transitions, a successful TTS response is treated as evidence
that the requested action executed. The AI does not need to verify every
individual action visually. An explicit execution error stops the turn and
requires clarification or recovery before more actions are attempted. The AI
must state the error publicly as Blue and ask the players whether it should
retry the action or pursue a different action. It must not retry automatically.

Whichever recovery option the players choose, the AI must announce an updated
turn plan publicly before continuing.

## Open questions

- Does the host describe the game and rules at session start, or should the AI
  infer them from the table?
- How is turn ownership detected in arbitrary games?
- What is the minimum safe fallback when the AI cannot identify legal actions?
- How can a human interrupt or cancel an autonomous turn already in progress?
