# Kill Team Opponent Tickets

This backlog breaks the Kill Team semantic opponent into executable work items.
The order assumes the current setup and observation slice already exists and
extends it into a full match-playing AI.

## Phases

1. Foundation: state, identity, tokens, legality.
2. Game loop: activations, turning points, CP, scoring.
3. Combat and tactics: attacks, saves, wounds, priorities.
4. Hardening: replay, regression tests, documentation.

## Ticket Index

| ID | Ticket | Depends On | Outcome |
| --- | --- | --- | --- |
| KT-001 | Canonical match state model | - | A single typed source of truth for phase, turning point, initiative, active operative, CP, VP, markers, objectives, statuses, and revisions. |
| KT-002 | Entity registry and roles | KT-001 | Stable mapping between live GUIDs and semantic roles for operatives, objectives, tokens, markers, counters, and terrain. |
| KT-003 | Marker and token primitives | KT-001, KT-002 | First-class placement and lifecycle actions for objective markers, status markers, control tokens, and board annotations. |
| KT-004 | Activation lifecycle | KT-001, KT-002 | Start/end activation flow with APL spend, activation state, and post-action validation. |
| KT-005 | Turning point lifecycle | KT-001, KT-004 | Start/end turning-point transitions, initiative handling, readying, and end-of-turn bookkeeping. |
| KT-006 | Command point economy | KT-001, KT-002 | CP gain/spend actions with validation, audit history, and live counter synchronization. |
| KT-007 | Objective and scoring system | KT-001, KT-003, KT-006 | Mission and tac-op scoring flows that update VP, place markers, and preserve a reasoned scoring history. |
| KT-008 | Combat resolution pipeline | KT-001, KT-002, KT-004 | Attack, defense, save, damage, wound, and injury resolution with deterministic state updates. |
| KT-009 | Tactical decision engine | KT-001, KT-007, KT-008 | A policy layer that chooses the next legal, scoring-focused action from the current match state. |
| KT-010 | Goal and priority system | KT-001, KT-009 | A structured list of win-oriented priorities such as holding objectives, denying scoring, preserving pieces, and finishing activations. |
| KT-011 | Full-game loop orchestrator | KT-001, KT-004, KT-005, KT-007 | A controller that can advance a full match through setup, activations, turning points, scoring windows, and endgame detection. |
| KT-012 | Legality and hidden-information enforcement | KT-001, KT-002, KT-009 | Hard fail-closed checks for illegal moves, illegal targets, hidden information, and ambiguous observations. |
| KT-013 | Persistence and replay | KT-001, KT-011 | Save and restore match state plus event history so a game can resume or be replayed from logs. |
| KT-014 | Scenario fixtures and regression tests | KT-001 through KT-013 | Deterministic tests for deployment, markers, activations, combat, scoring, and turning-point transitions. |
| KT-015 | Documentation and operator guidance | All prior tickets | Updated wiki pages, API contracts, and operator notes that explain what the opponent can do and how to validate it. |

## Detailed Tickets

### KT-001 Canonical match state model

Build the authoritative typed runtime model for a Kill Team match.

Scope:

- Track phase, turning point, initiative side, active operative, command
  points, victory points, markers, objectives, statuses, and map revision.
- Separate public state, private AI state, and host-adjudicated state.
- Keep the runtime state serializable so later persistence work can reuse it.
- Make the state model the single source of truth for both observations and
  semantic actions.
- Keep the model explicit enough that later tickets can add activations,
  scoring, and combat without inventing new state fields ad hoc.

Work breakdown:

1. Define the canonical match-state schema.
   - Match-level fields: phase, turning point, initiative side, active
     operative, map revision, observation revision, and setup status.
   - Resource fields: CP, VP, and any future mission-specific score buckets.
   - Board fields: operatives, objectives, markers, counters, terrain, and
     visibility projections.
   - Provenance fields: revision history, last action ID, and last committed
     event.
2. Separate runtime state from live TTS projections.
   - Treat the runtime state as authoritative for logic.
   - Store TTS GUIDs, names, positions, and mirror objects as projections of
     that state rather than as the state itself.
   - Keep private AI facts and public-observation facts in different buckets so
     hidden-information rules can be enforced later.
3. Define state transition helpers.
   - Add one entry point for setup initialization.
   - Add one entry point for observation snapshots.
   - Add one entry point for revision bumps and event recording.
4. Add serialization and restoration support.
   - Serialize the complete match state to a stable JSON structure.
   - Restore the same structure without losing identifiers, counters, or turn
     context.
   - Preserve enough metadata for later persistence and replay work.
5. Define invariants that every future action must respect.
   - Turning point is always positive.
   - Phase is always one of the known game-loop phases.
   - Active operative, if set, must resolve to a real operative in state.
   - Counter values and score buckets must remain numeric and non-negative.
   - Marker and objective collections must not contain duplicate live GUIDs.
6. Make the observation layer derive from the canonical state.
   - Observations should be a filtered projection of the match state, not a
     parallel structure that can drift.
   - The same state snapshot should produce the same observation payload unless
     the board actually changes.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001a State container and defaults | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the canonical match-state shape, defaults, and reset behavior in one place. |
| KT-001b Setup bootstrap state | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Populate phase, turning point, initiative, active operative, counters, markers, and revision data during setup. |
| KT-001c Observation projection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Derive the public observation payload from state instead of rebuilding it ad hoc from bridge queries. |
| KT-001d Revision and event helpers | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Centralize revision bumps, event recording, and state-copy helpers so later actions can reuse them safely. |
| KT-001e Serialization contract | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Serialize and restore the complete match state without losing identifiers, counters, or turn context. |
| KT-001f State invariants and validation tests | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Guard the state model with explicit invariants for phase, turning point, counters, markers, and active operative identity. |
| KT-001g Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md` | `docs/wiki/roadmap.md` | Keep the terminology and state-surface description aligned with the runtime model. |

### KT-001a Implementation checklist

Implement KT-001a before any tactical, scoring, or persistence work.

Order of work:

1. Add the canonical state container and related objects in
   `tts_mcp/runtime/killteam_runtime.py`.
   - Introduce `KillTeamState` plus the minimal nested objects needed for
     setup, board entities, resources, visibility, pending actions, and event
     history.
   - Keep the shape JSON-friendly so later persistence does not need a second
     translation layer.
   - Keep the state model separate from the bridge adapter and from the
     runtime methods that mutate it.
2. Add state construction helpers in `tts_mcp/runtime/killteam_runtime.py`.
   - Build one helper that returns the default state for a fresh scene epoch.
   - Build one helper that rehydrates state from a serialized dict.
   - Build one helper that converts the active state back into a plain dict for
     observation and persistence.
3. Thread the canonical state through setup in `tts_mcp/runtime/killteam_runtime.py`.
   - Populate phase, turning point, initiative side, active operative, CP,
     VP, markers, counters, and revisions during setup.
   - Make setup the only place that initializes a fresh match state.
   - Ensure setup resets any stale state when a new scene epoch begins.
4. Make observation derive from the canonical state in
   `tts_mcp/runtime/killteam_runtime.py`.
   - Stop assembling state from scattered local variables or bridge lookups.
   - Use the canonical state as the source for phase, turning point, active
     operative, counters, markers, and revision data.
   - Keep observation-only fields separate from mutable game state.
5. Add serialization round-trip coverage in `tests/test_killteam_runtime.py`.
   - Assert that a populated state can be serialized and restored without
     losing identifiers, counters, or turn context.
   - Assert that observation data remains stable after a serialize/restore
     cycle.
6. Add invariant coverage in `tests/test_killteam_runtime.py`.
   - Assert that invalid phase names, negative counters, duplicate live GUIDs,
     and missing active-operative references fail closed.
   - Assert that revision values only move forward when the state changes.
7. Add seam coverage in `tests/test_server.py` only if the server surface needs
   to expose the new state shape.
   - Keep this test limited to the public observation contract.
   - Do not test private helpers through the server seam.

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: canonical state, defaults,
  serialization helpers, setup bootstrap, observation projection, invariants.
- `tests/test_killteam_runtime.py`: state-shape tests, setup-state tests,
  round-trip tests, invariant tests.
- `tests/test_server.py`: only public observation-shape assertions that must
  remain visible through the server interface.

Out of scope:

- Tactical decision making.
- Combat resolution.
- Objective scoring rules beyond storing the state needed to represent them.
- Persistence to disk.

Acceptance criteria:

- The runtime can serialize and restore a complete match state without losing
  turn, scoring, or activation context.
- Observations are derived from this model rather than from ad hoc bridge
  queries.
- A later ticket can add activations, scoring, or persistence without
  redefining the match-state core.

### KT-002 Entity registry and roles

Create the stable identity layer that maps live GUIDs to semantic roles.

Scope:

- Register operatives, terrain, objectives, markers, counters, rollers, and
  tokens by GUID.
- Keep semantic roles separate from display names and faction labels.
- Record visibility and ownership boundaries for public, private, and hidden
  entities.

Acceptance criteria:

- The runtime can answer what an object is, why it matters, and whether the AI
  is allowed to reason about it.
- GUIDs remain stable across observations and action plans.

### KT-003 Marker and token primitives

Add first-class support for placing and managing game markers.

Scope:

- Place, move, update, and remove tokens and markers for objectives, status
  effects, control areas, and tactical annotations.
- Mirror markers back into the runtime state and observations.
- Keep marker creation bounded and explicit rather than using general-purpose
  object spawning.

Acceptance criteria:

- The AI can place a marker for an objective or status and see it in the next
  observation.
- Removing or updating a marker updates both the live scene and the runtime
  state.

### KT-004 Activation lifecycle

Implement a complete operative activation sequence.

Scope:

- Start activation, spend APL, end activation, and track the currently active
  operative.
- Validate that activation actions only occur during the correct phase.
- Record activation history for later replay and debugging.

Acceptance criteria:

- A single operative can complete an activation from start to end with state
  updates after each action.
- Illegal activation attempts fail closed with a clear reason.

### KT-005 Turning point lifecycle

Add turn progression and end-of-turn bookkeeping.

Scope:

- Start and end turning points.
- Handle initiative, readying, phase transitions, and score checkpoints.
- Reconcile per-turn state that should reset or roll forward.

Acceptance criteria:

- The runtime can advance one turning point and preserve the correct score and
  initiative state.
- End-of-turn state changes are reflected in both runtime state and live
  counters or markers.

### KT-006 Command point economy

Implement a clear CP resource model.

Scope:

- Gain CP from mission rules or turn progression.
- Spend CP on tactical ploys or other allowed uses.
- Validate that CP cannot go negative and every change is auditable.

Acceptance criteria:

- CP gain and spend actions update the live counter and the runtime model.
- Overspend attempts are rejected without mutating the match state.

### KT-007 Objective and scoring system

Make scoring a first-class gameplay subsystem.

Scope:

- Score objectives, mission points, tac op points, and other point sources.
- Place the right markers when objectives are claimed, contested, or scored.
- Track the reason for every VP change.

Acceptance criteria:

- The AI can pursue a scoring task and see the VP result in state and on the
  table.
- Scoring history explains why points were awarded.

### KT-008 Combat resolution pipeline

Expand the combat slice into the full attack and defense flow.

Scope:

- Build attack dice, defense dice, save resolution, damage assignment, wound
  application, and injury outcomes.
- Support the physical-dice contract already established for the first ranged
  slice.
- Preserve uncertainty handling when a physical commit is not clean.

Acceptance criteria:

- The AI can resolve a complete attack sequence without collapsing steps into a
  single opaque action.
- Damage and wound state are reflected in the runtime after resolution.

### KT-009 Tactical decision engine

Add the policy layer that chooses the next action.

Scope:

- Rank legal candidate actions by board state, score pressure, threats, and
  mission goals.
- Prefer score-positive and board-stable actions when the match state is close.
- Use the current runtime state rather than hidden or speculative data.

Acceptance criteria:

- Given the same state, the engine produces a deterministic ranked action set.
- The top choice is always legal under the current observation and hidden-info
  boundary.

### KT-010 Goal and priority system

Represent win conditions as explicit strategic priorities.

Scope:

- Model tasks like hold objective, deny opponent scoring, preserve operatives,
  kill a key target, and finish a turning point safely.
- Allow priorities to change as the score or board position changes.
- Feed priorities into tactical planning instead of hard-coding one move.

Acceptance criteria:

- The AI can explain its current strategic goal in terms of mission value.
- Goals can be reprioritized when the board state changes.

### KT-011 Full-game loop orchestrator

Build a controller that can drive an entire match.

Scope:

- Chain setup, deployment, activations, turning points, scoring windows, and
  endgame detection.
- Stop when the game is over or when a host ruling is required.
- Keep each step bounded and resumable.

Acceptance criteria:

- A full match can advance from setup through endgame without manual stepping
  through every low-level action.
- The controller can resume from an interrupted but valid state.

### KT-012 Legality and hidden-information enforcement

Make the opponent fail closed on anything it should not know or do.

Scope:

- Reject illegal moves, illegal attacks, illegal scoring, and invalid marker
  placement.
- Enforce the public/private/hidden information boundary.
- Escalate ambiguous or contradictory states to host adjudication.

Acceptance criteria:

- The AI cannot use hidden opponent state to choose an action.
- Illegal requests fail safely with a stable error and no scene mutation.

### KT-013 Persistence and replay

Add durable recovery for long matches.

Scope:

- Persist match state, action history, and scoring history.
- Restore a match from saved state after a disconnect or restart.
- Enable replay from logs for debugging and testing.

Acceptance criteria:

- A saved game can be restored with the same strategic state and score.
- Replay reproduces the same sequence of committed actions.

### KT-014 Scenario fixtures and regression tests

Cover the opponent with deterministic tests.

Scope:

- Add fixture-based tests for deployment, markers, activations, combat,
  scoring, CP changes, and turn progression.
- Add bridge tests for uncertain commits, stale state, and hidden-info
  rejection.
- Keep live-TTS validation separate from deterministic tests.

Acceptance criteria:

- The core game loop has repeatable tests that fail on rule regressions.
- New opponent actions are paired with tests before they are considered done.

### KT-015 Documentation and operator guidance

Document the full opponent surface and operating rules.

Scope:

- Keep the wiki, ADRs, API reference, and roadmap aligned with the runtime.
- Document the new ticket backlog and link the major phases from the roadmap.
- Explain how host rulings, hidden information, and scoring interact.

Acceptance criteria:

- A new contributor can find the opponent surface and understand the expected
  order of implementation.
- The docs explain the current limits as clearly as the implemented features.
