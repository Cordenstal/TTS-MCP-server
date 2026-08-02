# Kill Team Opponent Tickets

This backlog breaks the Kill Team semantic opponent into executable work items.
The order assumes the current setup and observation slice already exists and
extends it into a full match-playing AI.

The setup-specific KT-016 through KT-021 tickets are implemented and frozen
for the current setup slice: board-context geometry, placement policy,
turn-order behavior, recovery semantics, gateway execution, and the regression
matrix that locks the public docs to the runtime. The geometry snapshot,
slot-ranking, turn ordering, recovery, gateway routing, and regression
subtasks are all implemented. KT-021 is now implemented as direct gateway
execution of the runtime `KILLTEAM_AUTORUN_SETUP` macro, which keeps the
semantic setup path authoritative and avoids the repeated-MOVE fallback.
KT-022 tracks the next setup slice for operative tokens, equipment, and other
non-model fixtures.

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
| KT-016 | Setup deployment geometry model | KT-001, KT-002, KT-011, KT-012 | A revision-stamped deployment context that captures live geometry, occupancy, objectives, and stale-context boundaries for setup planning. Implemented in the runtime; KT-016c and KT-016d remain to freeze stale-context and regression behavior. |
| KT-017 | Context-aware setup placement policy | KT-001, KT-007, KT-009, KT-010, KT-016 | A tactical slot-ranking contract that weighs cover, exposure, objective pressure, friendly spacing, hostile threat, and faction style. Implemented in the runtime; KT-017d remains to pin policy regressions. |
| KT-018 | Setup turn-order and pass advancement | KT-001, KT-011, KT-012, KT-016, KT-017 | A deterministic setup flow that chooses the next side, advances alternating passes, and carries the current deployment batch forward without collapsing to zone-center placement. Implemented in the runtime and pinned by setup regression tests. |
| KT-019 | Setup recovery and reset semantics | KT-001, KT-011, KT-012, KT-016, KT-017, KT-018 | A recovery contract for `!ai start fresh`, human reconciliation, pending placements, and uncertain setup commits. Implemented in the controller and runtime recovery paths. |
| KT-020 | Setup regression matrix and docs alignment | KT-014, KT-015, KT-016, KT-017, KT-018, KT-019 | A locked validation plan and doc update set that proves the geometry-aware setup path on dense boards and stale revisions. Implemented in the regression docs and tests. |
| KT-021 | Autorun setup gateway execution | KT-016, KT-017, KT-018, KT-020 | Implemented in the runtime and gateway; `KILLTEAM_AUTORUN_SETUP` executes through the semantic setup macro so legal-slot selection, terrain-aware placement, and fail-closed setup progression stay inside the rules engine. |
| KT-022 | Setup placement for operative tokens and equipment | KT-003, KT-016, KT-017, KT-021 | A bounded setup-placement contract for operative tokens, equipment, and other non-model fixtures, with legality checks, readback, and separate regression coverage from model placement. |

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

### KT-001b Setup bootstrap state

Initialize the canonical state from a fresh live scene.

Order of work:

1. Define the setup-only state fields in `tts_mcp/runtime/killteam_runtime.py`.
   - Mark the match as `setup` or `ready` according to the current setup stage.
   - Initialize turning point, initiative side, active side, and active
     operative values.
   - Seed the setup, board, and resource sub-structures so later actions do not
     need to create them lazily.
2. Wire `setup()` to populate the canonical state.
   - Read live bridge data once and translate it into the state model.
   - Populate counters, markers, operatives, terrain, and objective metadata.
   - Reset stale state when a fresh scene epoch starts.
3. Make setup output reflect the state bootstrap.
   - Return the state-derived revision, phase, turn, and setup status.
   - Keep the initial observation aligned with the same bootstrapped state.
4. Add setup tests in `tests/test_killteam_runtime.py`.
   - Verify a fresh setup populates the expected phase, turning point, and
     resource values.
   - Verify stale state does not survive a new setup call.
   - Verify the bootstrapped state remains consistent across observation
     calls.

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: setup defaults, fresh-state
  initialization, scene-epoch reset, state bootstrapping.
- `tests/test_killteam_runtime.py`: setup bootstrap assertions and stale-state
  regression tests.

### KT-001c Observation projection

Make `observe()` read from canonical state instead of reconstructing state from
bridge lookups.

Order of work:

1. Define the observation shape in `tts_mcp/runtime/killteam_runtime.py`.
   - Include phase, turning point, active operative, revision metadata,
     counters, markers, objectives, operatives, and visibility status.
   - Distinguish public facts from private AI facts.
   - Keep observation-only convenience fields separate from mutable state.
2. Route observation assembly through the canonical state.
   - Use the state model as the source for phase, turn, resources, and entity
     snapshots.
   - Avoid rebuilding the same data from scattered local variables.
   - Preserve stable ordering where the observation is used for tests.
3. Make observation updates monotonic.
   - Increment observation revision when a new snapshot is emitted.
   - Keep map revision separate so state changes and board changes are not
     conflated.
4. Add observation tests in `tests/test_killteam_runtime.py` and
   `tests/test_server.py`.
   - Verify the observation includes the same values the state contains.
   - Verify public server output exposes the expected projection and nothing
     extra.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001c-1 Observation schema shape | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the exact observation payload fields, including phase, turn, resources, entities, revisions, and visibility metadata. |
| KT-001c-2 Public/private split | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Ensure the observation exposes only public facts on the public seam and keeps private AI facts separated. |
| KT-001c-3 Stable projection order | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Keep map/object/marker/entity ordering deterministic so tests and clients see the same structure each time. |
| KT-001c-4 Observation revision handling | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Increment observation revision on each emitted snapshot without conflating it with game-state revision. |
| KT-001c-5 Derived counters and summaries | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Derive observation-friendly summaries for counters, objectives, markers, and operative readiness from canonical state. |
| KT-001c-6 Server-facing observation contract | `tests/test_server.py` | `tts_mcp/app/server.py` | Verify the public server seam returns the same observation projection and does not leak extra internal state. |
| KT-001c-7 Regression coverage for state-derived output | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove the same canonical state yields the same observation output after setup, mutation, and serialization round trips. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: observation payload shape,
  projection logic, ordering, revision handling, and derived summaries.
- `tests/test_killteam_runtime.py`: runtime observation assertions and
  regression coverage.
- `tests/test_server.py`: public observation surface assertions.
- `tts_mcp/app/server.py`: only if the public tool contract needs to expose a
  new observation field or remove a leaked internal field.

### KT-001d Revision and event helpers

Centralize revision management and event recording.

Order of work:

1. Add helper methods in `tts_mcp/runtime/killteam_runtime.py`.
   - Add one helper for revision bumps.
   - Add one helper for append-only event recording.
   - Add one helper for deep-copying state fragments before they are published.
2. Make state mutations use the helpers.
   - Replace local ad hoc revision increments with the shared helper.
   - Record one event per committed semantic change.
   - Store the action ID and result metadata alongside the event when present.
3. Add helper-focused tests in `tests/test_killteam_runtime.py`.
   - Verify revision changes are monotonic.
   - Verify events are appended in order.
   - Verify emitted events are copies rather than live mutable references.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001d-1 Revision bump helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Create one shared helper for incrementing state revision and returning the updated value. |
| KT-001d-2 Append-only event helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Create one helper that appends a normalized event record to match history without mutating existing records. |
| KT-001d-3 Safe copy helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Ensure event payloads, state fragments, and returned results are deep-copied before they leave the runtime. |
| KT-001d-4 Recorded-result helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Normalize the pattern of returning action results while preserving action IDs, replay state, and event metadata. |
| KT-001d-5 Mutation-site conversion | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Replace local ad hoc revision increments and event appends in existing methods with the shared helpers. |
| KT-001d-6 Revision regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove revisions only move forward when state changes are committed. |
| KT-001d-7 Event ordering and immutability tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove history is append-only, ordered, and detached from later caller mutations. |
| KT-001d-8 Action-id and replay coverage | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove the helper path preserves action IDs and enables idempotent replay of already-committed actions. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: revision helper, event helper, safe
  copy helper, result-recording helper, and mutation-site conversion.
- `tests/test_killteam_runtime.py`: revision monotonicity, event ordering,
  immutability, and replay regression tests.

### KT-001e Serialization contract

Define the round-trip contract for the canonical state.

Order of work:

1. Add a JSON-friendly export path in `tts_mcp/runtime/killteam_runtime.py`.
   - Convert nested dataclasses and state objects into plain dict/list/scalar
     values.
   - Preserve schema version, revisions, event history, and setup metadata.
2. Add an import path in `tts_mcp/runtime/killteam_runtime.py`.
   - Rehydrate the same schema from a plain dict.
   - Fail closed when required fields are missing or invalid.
   - Keep unknown-version handling explicit instead of silent.
3. Add round-trip tests in `tests/test_killteam_runtime.py`.
   - Serialize a populated state and restore it.
   - Assert that counters, markers, operatives, and turn context survive the
     round trip.
   - Assert that the restored state still drives the same observation output.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001e-1 Export schema shape | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the JSON-compatible structure used to export the canonical state, including nested objects and version fields. |
| KT-001e-2 Import schema shape | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the input schema used to restore state, with explicit handling for missing fields and unknown versions. |
| KT-001e-3 Dataclass-to-dict conversion | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add helpers that turn nested runtime objects into plain dict/list/scalar data without losing identifiers or metadata. |
| KT-001e-4 Dict-to-dataclass hydration | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add helpers that rebuild the canonical state objects from serialized data while preserving defaults and validation. |
| KT-001e-5 Version gate and migration hook | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Make version mismatches explicit and leave a controlled place for future migrations. |
| KT-001e-6 Round-trip state tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove a populated state survives export/import without changing counters, turn state, or entity identity. |
| KT-001e-7 Observation parity after round trip | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py`, `tests/test_server.py` | Prove a restored state produces the same observation projection as the original state. |
| KT-001e-8 Serialization failure tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Prove malformed or incompatible serialized input fails closed rather than producing partial state. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: export/import helpers, version gate,
  and any future migration hook.
- `tests/test_killteam_runtime.py`: round-trip, parity, and failure coverage.
- `tests/test_server.py`: only if the server seam needs to validate restored
  public observations.

### KT-001f State invariants and validation tests

Guard the canonical model with explicit invariants.

Order of work:

1. Add validation helpers in `tts_mcp/runtime/killteam_runtime.py`.
   - Validate phase names against the known loop states.
   - Validate that turning point and resource counters stay non-negative.
   - Validate that active operative references resolve to a real operative.
   - Validate that board collections do not duplicate live GUIDs.
2. Call validation from the right seams.
   - Validate after setup.
   - Validate after every committed state mutation.
   - Validate before emitting an observation snapshot if a prior action may
     have corrupted state.
3. Add invariant tests in `tests/test_killteam_runtime.py`.
   - Cover invalid phase values.
   - Cover negative counters and duplicate identifiers.
   - Cover stale active-operative references and corrupted marker ledgers.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001f-1 Phase and turn validator | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one validator that checks phase names, turning-point bounds, and active-side consistency. |
| KT-001f-2 Counter and resource validator | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one validator that rejects negative CP/VP values and malformed counter projections. |
| KT-001f-3 Entity uniqueness validator | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one validator that rejects duplicate live GUIDs in operatives, objectives, markers, terrain, counters, and zones. |
| KT-001f-4 Active-operative resolver checks | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one validator that ensures the active operative exists and matches the current team and visibility expectations. |
| KT-001f-5 Setup-time validation hook | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Run validation at the end of setup before the runtime reports readiness. |
| KT-001f-6 Mutation-time validation hook | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Run validation after every committed state mutation so corruption is caught immediately. |
| KT-001f-7 Observation-time validation hook | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Run validation before observation emission when state may have been partially updated. |
| KT-001f-8 Negative-state regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Add tests that inject invalid phase, turn, counter, and duplicate-entity state and assert failure is closed. |
| KT-001f-9 Corruption and stale-reference tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Add tests for stale active-operative references, corrupted marker ledgers, and invalid counter projections. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: invariant helpers and validation
  call sites.
- `tests/test_killteam_runtime.py`: negative-state, corruption, and stale-
  reference regression tests.

### KT-001g Documentation alignment

Keep the schema, vocabulary, and roadmap in sync with the runtime model.

Order of work:

1. Update `docs/wiki/killteam.md`.
   - Describe the canonical state model and its public/private split.
   - Reflect the new setup bootstrap, observation projection, and revision
     vocabulary.
2. Update `docs/adr/0009-killteam-semantic-opponent.md`.
   - Align the ADR language with the canonical state schema and the
     round-trip contract.
   - Keep the hidden-information and host-adjudication boundaries explicit.
3. Update `docs/wiki/roadmap.md`.
   - Mark KT-001 progress accurately.
   - Keep the implementation order aligned with the file-level checklist.
4. Update surrounding references if needed.
   - Touch `docs/wiki/README.md` only if the navigation or terminology changes.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-001g-1 Wiki state-model update | `docs/wiki/killteam.md` | `tts_mcp/runtime/killteam_runtime.py` | Document the canonical state model, public/private split, setup bootstrap, and observation projection in the main Kill Team wiki page. |
| KT-001g-2 ADR schema alignment | `docs/adr/0009-killteam-semantic-opponent.md` | `tts_mcp/runtime/killteam_runtime.py` | Update the ADR to describe the canonical state, round-trip contract, and fail-closed validation boundary. |
| KT-001g-3 Roadmap progress update | `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Keep KT-001 status aligned with the file-level checklist and mark only completed substeps as done. |
| KT-001g-4 Doc navigation review | `docs/wiki/README.md` | `docs/wiki/roadmap.md` | Add or keep only the navigation entries needed to surface the KT-001 planning and implementation artifacts. |
| KT-001g-5 Terminology consistency pass | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `tts_mcp/runtime/killteam_runtime.py` | Make sure state names, revision terms, and observation vocabulary match the runtime schema exactly. |
| KT-001g-6 Cross-reference hygiene | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md`, `docs/wiki/README.md` | `docs/wiki/killteam-tickets.md` | Remove stale references, duplicate terms, or outdated rollout language that would confuse the implementation order. |
| KT-001g-7 Documentation review checks | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | - | Verify the updated docs still describe the same state model and the same current implementation boundaries. |

File ownership:

- `docs/wiki/killteam.md`: state-model and observation description.
- `docs/adr/0009-killteam-semantic-opponent.md`: architecture and boundary
  record.
- `docs/wiki/roadmap.md`: backlog status and sequencing.
- `docs/wiki/README.md`: navigation only, if needed.

## KT-001 execution order

Use the KT-001 subtasks in this order:

1. KT-001a, because the canonical `KillTeamState` and its helpers define the
   substrate every other step depends on.
2. KT-001b, because setup must populate that substrate before any observation
   or mutation logic can rely on it.
3. KT-001c, because observation must come from the canonical state before the
   runtime can be validated as state-driven.
4. KT-001d, because revision and event helpers should be shared before more
   mutating actions depend on them.
5. KT-001e, because the round-trip contract must be defined before later
   persistence work or recovery logic depends on it.
6. KT-001f, because validation should lock the state shape after the model and
   serialization contract are stable.
7. KT-001g, because the docs should be updated after the runtime contract is
   stable enough to describe accurately.

Implementation checkpoint:

- Do not start the next KT-001 subtask until the current subtask has its
  matching tests and any required documentation update in place.
- Keep KT-001c and KT-001e aligned: observation parity and round-trip parity
  should describe the same canonical state shape.
- Keep KT-001f last among the runtime subtasks so its invariants validate the
  final KT-001 state model instead of a partial draft.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-003a Marker ledger schema | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add a canonical marker/token ledger to the match state with stable IDs, linked entity references, and lifecycle metadata. |
| KT-003b Marker spawn helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper for spawning a live marker object at a validated position with a deterministic projection back into state. |
| KT-003c Marker move/update helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper for moving or updating an existing marker without reintroducing duplicate live GUIDs. |
| KT-003d Marker removal helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper for removing a marker from both the runtime ledger and the live scene projection. |
| KT-003e Token category handling | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Distinguish objective markers, status markers, control tokens, and tactical annotations in the state model. |
| KT-003f Linkage to objectives and operatives | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Record which entity a marker belongs to so later scoring and activation logic can query it without guessing. |
| KT-003g Observation projection for markers | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Ensure markers and tokens appear in observation output with stable identity, position, and ownership metadata. |
| KT-003h Failure-mode tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover duplicate GUIDs, missing live objects, stale marker references, and invalid placement or removal requests. |
| KT-003i Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the marker/token vocabulary if the runtime contract changes in a way that affects the docs. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: marker ledger, marker lifecycle
  helpers, token categorization, linkage metadata, and observation projection.
- `tests/test_killteam_runtime.py`: marker lifecycle, failure-mode, and
  projection tests.
- `tests/test_server.py`: only if the public observation contract needs to
  expose marker/token fields.
- `docs/wiki/killteam.md`: user-facing explanation of marker and token
  semantics.
- `docs/adr/0009-killteam-semantic-opponent.md`: architecture boundary notes
  for marker and token handling.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-003 changes the plan.

Execution order:

1. KT-003a, because the ledger is the substrate for every marker/token action.
2. KT-003b and KT-003e together, because spawn behavior and type categories
   need to agree before tests can lock the contract.
3. KT-003c and KT-003d, because move/update/remove rely on the same lifecycle
   metadata.
4. KT-003f, because linkage to objectives and operatives depends on the ledger
   shape being stable.
5. KT-003g, because observations should expose the final marker model only
   after the runtime shape is stable.
6. KT-003h, because the failure modes validate the finished lifecycle.
7. KT-003i, because the docs should describe the final contract, not a draft.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-004a Activation state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the minimal activation-related state needed to track the active operative, activation status, and per-turn activation history. |
| KT-004b Start-activation helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that starts an activation only when the current phase and state allow it. |
| KT-004c APL spend helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that spends APL from the active operative and records the change in the activation history. |
| KT-004d End-activation helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that closes the current activation, clears activation-specific state, and records the final activation event. |
| KT-004e Activation history recording | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Record the sequence of activation actions so later replay and debugging can reconstruct what happened. |
| KT-004f Legality checks for activation steps | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject activation steps when the operative is inactive, the phase is wrong, or the requested spend would be illegal. |
| KT-004g Runtime observation of activation state | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Expose the current activation state in observation output without leaking hidden or irrelevant internals. |
| KT-004h Activation regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover a full activation, illegal activation entry, illegal APL spend, and activation state reset after end-activation. |
| KT-004i Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the activation contract or activation-state vocabulary changes. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: activation state, activation helpers,
  legality checks, activation history, and observation projection.
- `tests/test_killteam_runtime.py`: activation lifecycle and failure-mode
  tests.
- `tests/test_server.py`: only if the public observation contract needs
  activation-state fields.
- `docs/wiki/killteam.md`: human-facing activation model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: activation boundary and
  authority notes if the runtime contract changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-004 affects the plan.

Execution order:

1. KT-004a, because the activation state shape is the substrate for everything
   else in the activation lifecycle.
2. KT-004b and KT-004c, because starting an activation and spending APL are the
   two core legal actions.
3. KT-004d and KT-004e, because ending the activation and recording the
   sequence give the lifecycle its audit trail.
4. KT-004f, because legality should be locked down once the helper shape is
   clear.
5. KT-004g, because observation should reflect the activation state after the
   lifecycle is stable.
6. KT-004h, because the tests should validate the complete lifecycle and the
   main failure paths.
7. KT-004i, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-005a Turning-point state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the minimal turn-level state needed to track the current turning point, initiative side, phase, ready state, and per-turn bookkeeping. |
| KT-005b Start-turning-point helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that starts a turning point, resets the right per-turn flags, and marks the new phase boundary. |
| KT-005c End-turning-point helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that closes a turning point, finalizes per-turn history, and prepares state for the next turn. |
| KT-005d Initiative and readying rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add helpers for initiative ownership, readying operatives, and any turn-bound state that must flip at the turn boundary. |
| KT-005e Turn boundary validation | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject turning-point transitions when the current phase, initiative state, or active-operative state is inconsistent. |
| KT-005f End-of-turn projection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Expose turn and ready-state changes in observations so the next action sees the correct game-loop boundary. |
| KT-005g Turning-point regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover advancing a turn, readying behavior, initiative preservation, and invalid turn-boundary transitions. |
| KT-005h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the turn-boundary contract or terminology changes after the runtime shape is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: turning-point state, boundary
  helpers, readiness transitions, validation, and observation projection.
- `tests/test_killteam_runtime.py`: turn-boundary and ready-state regression
  tests.
- `tests/test_server.py`: only if the public observation contract needs turn
  boundary fields.
- `docs/wiki/killteam.md`: human-facing turn/initiative model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: decision record for turn
  ownership and boundary behavior if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-005 changes the plan.

Execution order:

1. KT-005a, because the turn-state fields are the substrate for the lifecycle.
2. KT-005b and KT-005c, because the start and end helpers define the turn
   boundary itself.
3. KT-005d, because initiative and readying are turn-bound rules that depend on
   the boundary helpers.
4. KT-005e, because legality should be checked once the lifecycle shape is
   established.
5. KT-005f, because observations need to reflect the new turn state after the
   lifecycle is stable.
6. KT-005g, because the tests should verify the complete turn flow and failure
   paths.
7. KT-005h, because the docs should be updated after the contract is settled.

### KT-006 Command point economy

Implement a clear CP resource model.

Scope:

- Gain CP from mission rules or turn progression.
- Spend CP on tactical ploys or other allowed uses.
- Validate that CP cannot go negative and every change is auditable.

Acceptance criteria:

- CP gain and spend actions update the live counter and the runtime model.
- Overspend attempts are rejected without mutating the match state.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-006a CP state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the minimal CP-specific state needed to track current value, source history, and live projection identity. |
| KT-006b CP gain helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that increases CP from a legal source and records the change in state history. |
| KT-006c CP spend helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that decreases CP only when enough resource exists and records the spend. |
| KT-006d CP validation rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject negative CP, overspend attempts, malformed counter projections, and illegal source transitions. |
| KT-006e Live counter projection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Keep the runtime CP value and the live TTS counter synchronized after every committed CP change. |
| KT-006f CP history and audit trail | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Record where CP came from, where it went, and which action ID caused the change. |
| KT-006g CP regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover gain, spend, overspend, repeated spend, and observation parity after CP changes. |
| KT-006h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the CP vocabulary or resource lifecycle changes in the runtime contract. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: CP state, CP helpers, validation, live
  projection, and history.
- `tests/test_killteam_runtime.py`: CP behavior, failure-mode, and projection
  tests.
- `tests/test_server.py`: only if the public observation contract needs CP
  fields.
- `docs/wiki/killteam.md`: human-facing CP lifecycle description if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  if the CP contract changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-006 changes the plan.

Execution order:

1. KT-006a, because the CP state fields are the substrate for the resource
   lifecycle.
2. KT-006b and KT-006c, because gain and spend are the core legal resource
   actions.
3. KT-006d, because legality should be locked once the helper shape is clear.
4. KT-006e, because the live counter must mirror the canonical state.
5. KT-006f, because the audit trail depends on the helper and projection shape.
6. KT-006g, because the tests should cover all legal and illegal CP paths.
7. KT-006h, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-007a Scoring state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the minimal scoring-specific state needed to track VP buckets, mission scoring history, objective ownership, and score-linked markers. |
| KT-007b Objective scoring helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that awards points for an objective and records the scoring reason in state history. |
| KT-007c Mission scoring helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper for scoring mission rules or tac-op style points without conflating them with CP or turn progression. |
| KT-007d Score-marker linkage | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Keep score-linked markers associated with the objective or scoring event that created them. |
| KT-007e Scoring validation rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject negative VP changes, duplicate scoring events, missing objective references, and score updates that do not match a legal source. |
| KT-007f Score observation projection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Expose VP totals, mission score summaries, and scored-objective state in observations without leaking hidden details. |
| KT-007g Scoring regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover objective scoring, mission scoring, repeated scoring, invalid scoring, and observation parity after VP changes. |
| KT-007h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the score vocabulary or scoring lifecycle changes in the runtime contract. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: scoring state, scoring helpers,
  validation, linked markers, and observation projection.
- `tests/test_killteam_runtime.py`: objective scoring, mission scoring,
  failure-mode, and parity tests.
- `tests/test_server.py`: only if the public observation contract needs score
  fields.
- `docs/wiki/killteam.md`: human-facing scoring model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: scoring authority and
  boundary notes if the runtime contract changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-007 changes the plan.

Execution order:

1. KT-007a, because the scoring state fields are the substrate for the
   subsystem.
2. KT-007b and KT-007c, because objective and mission scoring are the core
   legal scoring actions.
3. KT-007d, because markers should stay linked to the event or objective that
   created them.
4. KT-007e, because legality should be locked once the score helpers are
   defined.
5. KT-007f, because observations need to surface the final score model after
   the lifecycle is stable.
6. KT-007g, because the tests should cover all legal and illegal score paths.
7. KT-007h, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-008a Combat state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the minimal combat-specific state needed to track attack context, defense context, damage projections, and wound resolution history. |
| KT-008b Attack resolution helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that resolves attack dice, hit counts, crits, and attack-side outcome metadata. |
| KT-008c Defense resolution helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that resolves defense dice, saves, crit saves, and defense-side outcome metadata. |
| KT-008d Damage and wound application helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that applies damage to the target operative, updates wounds, and records the resulting state change. |
| KT-008e Physical-dice contract hooks | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Keep the attack and defense workflow aligned with the already-established physical-dice path, including uncertainty handling and readback expectations. |
| KT-008f Combat validation rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject attacks that are out of range, out of line of sight, missing required dice, or inconsistent with the combat state. |
| KT-008g Combat observation projection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Expose combat-relevant outcome state in observations without leaking hidden information or speculative results. |
| KT-008h Combat regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover successful attacks, blocked attacks, invalid target states, uncertain commits, and parity between state and observation after combat. |
| KT-008i Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the combat contract or terminology changes after the runtime shape is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: combat state, attack/defense/damage
  helpers, validation, and observation projection.
- `tests/test_killteam_runtime.py`: combat lifecycle, uncertainty, and
  regression tests.
- `tests/test_server.py`: only if the public observation contract needs
  combat outcome fields.
- `docs/wiki/killteam.md`: human-facing combat model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: decision record for combat
  authority and uncertainty boundaries if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-008 changes the plan.

Execution order:

1. KT-008a, because the combat state fields are the substrate for the
   resolution pipeline.
2. KT-008b and KT-008c, because attack and defense resolution are the two core
   combat subproblems.
3. KT-008d, because damage and wounds should be applied only after attack and
   defense are settled.
4. KT-008e, because the physical-dice contract must remain aligned with the
   existing combat slice.
5. KT-008f, because combat legality should be locked once the resolution shape
   is clear.
6. KT-008g, because observations should expose the final combat result after
   the pipeline is stable.
7. KT-008h, because the tests should cover the full combat lifecycle and
   failure paths.
8. KT-008i, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-009a Decision-state inputs | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the minimal decision inputs needed from the canonical state: public board state, score pressure, visible threats, and available legal actions. |
| KT-009b Candidate action generation | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Build the set of candidate actions the policy engine is allowed to rank for the current state. |
| KT-009c Action scoring model | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Score each candidate using board safety, scoring value, threat reduction, resource cost, and turn efficiency. |
| KT-009d Deterministic ranking helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Rank candidates in a stable order so repeated evaluations on the same state produce the same result. |
| KT-009e Legality and visibility gating | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject candidates that depend on hidden, stale, or illegal information before they reach the ranking stage. |
| KT-009f Explainability payload | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Return the decision rationale, ranking factors, and rejected-candidate notes in a structured form for debugging and operator review. |
| KT-009g Decision regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover deterministic ranking, legality rejection, explanation payloads, and repeated-evaluation parity. |
| KT-009h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the decision-engine contract or terminology changes after the runtime shape is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: decision inputs, candidate generation,
  scoring, ranking, legality gating, and explainability payloads.
- `tests/test_killteam_runtime.py`: decision ranking, rejection, and parity
  tests.
- `tests/test_server.py`: only if the public observation or operator surface
  needs to expose decision explanations.
- `docs/wiki/killteam.md`: human-facing decision-engine description if it
  changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  for the policy layer if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-009 changes the plan.

Execution order:

1. KT-009a, because the decision engine needs a stable input contract.
2. KT-009b, because the engine cannot score actions before it can enumerate
   legal candidates.
3. KT-009c, because scoring candidates is the basis for ranking.
4. KT-009d, because stable ranking turns scoring into a repeatable policy.
5. KT-009e, because hidden-information and legality gates must trim the
   candidate set before the engine explains anything.
6. KT-009f, because the explanation payload should reflect the final ranked
   candidates.
7. KT-009g, because the tests should lock the ranking and rejection behavior.
8. KT-009h, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-010a Goal schema | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the canonical goal/priority data structure to represent strategic intent, priority weights, status, and source facts. |
| KT-010b Goal taxonomy | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the allowed high-level goals such as objective hold, deny scoring, preserve units, eliminate threats, and safe-end-turn. |
| KT-010c Priority scoring helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that turns board state, score state, and threat state into ranked strategic priorities. |
| KT-010d Goal update helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that updates the current goal set when the board or score state changes. |
| KT-010e Explanation payload | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Return a structured explanation for why each goal has its current priority and what facts drove the update. |
| KT-010f Goal-validation rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject invalid goals, duplicate active goals, malformed priority weights, and stale source references. |
| KT-010g Goal regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover goal creation, reprioritization, invalid goal input, and explanation parity after state changes. |
| KT-010h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the strategic-priority contract or terminology changes after the runtime shape is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: goal schema, taxonomy, priority
  scoring, goal updates, validation, and explanation payloads.
- `tests/test_killteam_runtime.py`: goal creation, reprioritization, invalid
  input, and explanation parity tests.
- `tests/test_server.py`: only if the public surface needs to expose goal
  explanations.
- `docs/wiki/killteam.md`: human-facing strategic-priority model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  for the priority layer if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-010 changes the plan.

Execution order:

1. KT-010a, because the goal schema is the substrate for all priority logic.
2. KT-010b, because the engine needs a controlled vocabulary of strategic
   goals.
3. KT-010c, because priorities must be computed before they can be updated or
   explained.
4. KT-010d, because goal updates depend on the priority scoring model.
5. KT-010e, because explanation output should reflect the final goal state.
6. KT-010f, because validation should lock down malformed or stale goal data.
7. KT-010g, because tests should cover goal creation, reprioritization, and
   explanation parity.
8. KT-010h, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-011a Match-loop state fields | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add the orchestration state needed to track phase progression, loop checkpoints, completion state, and resume metadata. |
| KT-011b Loop step planner | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that chooses the next match-loop step from the canonical state and the current phase. |
| KT-011c Setup-to-start transition | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that advances the game from setup into the first legal live-play state once setup is complete. |
| KT-011d Activation/turn/scoring sequencing | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that chains activations, turning points, and scoring windows in the correct order. |
| KT-011e Endgame detection | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that detects match completion, handles winner state, and stops the loop safely. |
| KT-011f Resume and checkpoint metadata | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add checkpoint data so an interrupted but valid match loop can resume from the last committed step. |
| KT-011g Loop orchestration tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover setup-to-live transitions, loop progression, endgame detection, and resume behavior. |
| KT-011h Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the orchestrator contract or phase vocabulary changes after the runtime shape is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: orchestration state, step planner,
  state transitions, endgame detection, and resume metadata.
- `tests/test_killteam_runtime.py`: loop sequencing, endgame, and resume
  regression tests.
- `docs/wiki/killteam.md`: human-facing match-loop description if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  for the orchestrator if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-011 changes the plan.

Execution order:

1. KT-011a, because the match-loop state is the substrate for orchestration.
2. KT-011b, because the controller needs a step-planning primitive.
3. KT-011c, because setup-to-start is the first live-loop boundary.
4. KT-011d, because sequencing activations, turns, and scoring windows is the
   core orchestration behavior.
5. KT-011e, because endgame detection stops the controller safely.
6. KT-011f, because resume metadata depends on the checkpointed loop shape.
7. KT-011g, because tests should cover the full loop and recovery behavior.
8. KT-011h, because the docs should be updated after the contract is settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-012a Information-classification model | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the canonical classification for public, private, last-known, hidden, and host-adjudicated facts. |
| KT-012b Legality gate helpers | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one shared gate that every semantic action can use before it mutates state or calls the bridge. |
| KT-012c Hidden-info rejection rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject any action that would depend on concealed opponent identity, private deployment, or unavailable board facts. |
| KT-012d Ambiguity and contradiction handling | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Fail closed when observations, map geometry, or state projections disagree and a host ruling is required. |
| KT-012e Host-adjudication handoff | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py`, `tests/test_server.py` | Expose a structured path for pausing play, recording the dispute, and resuming only after a ruling. |
| KT-012f Illegal-action response model | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Standardize the failure shape for illegal actions so callers can distinguish rejection, ambiguity, and uncertain commit. |
| KT-012g Enforcement tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover hidden-info access, illegal state use, contradictory evidence, and host-ruling escalation. |
| KT-012h Server-seam policy checks | `tests/test_server.py` | `tts_mcp/app/server.py` | Verify the public server surface does not expose hidden state or bypass the legality gate. |
| KT-012i Documentation alignment | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Update the docs only if the legality or hidden-information vocabulary changes after the runtime contract is finalized. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: fact classification, legality gates,
  hidden-info rejection, ambiguity handling, adjudication handoff, and failure
  model.
- `tests/test_killteam_runtime.py`: hidden-info, legality, ambiguity, and
  escalation tests.
- `tests/test_server.py`: only if the public observation/tool surface needs
  explicit hidden-info checks.
- `docs/wiki/killteam.md`: human-facing legality and hidden-information model
  if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  for the policy layer if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-012 changes the plan.

Execution order:

1. KT-012a, because every other legality rule depends on the fact classes.
2. KT-012b, because the shared gate should exist before any specific rejection
   rule is written.
3. KT-012c, because hidden-information rejection is the core policy boundary.
4. KT-012d, because contradiction handling sits on top of the fact model and
   hidden-info rules.
5. KT-012e, because host-ruling handoff depends on the legality and ambiguity
   model being stable.
6. KT-012f, because callers need a stable failure shape after the gate logic is
   defined.
7. KT-012g, because tests should lock the enforcement behavior and escalation
   paths.
8. KT-012h, because the server surface should be checked only after the policy
   contract exists.
9. KT-012i, because the docs should be updated after the contract is settled.

### KT-013 Persistence and replay

Add durable recovery for long matches.

Scope:

- Persist match state, action history, and scoring history.
- Restore a match from saved state after a disconnect or restart.
- Enable replay from logs for debugging and testing.

Acceptance criteria:

- A saved game can be restored with the same strategic state and score.
- Replay reproduces the same sequence of committed actions.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-013a Persistence schema | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the canonical snapshot shape for saving match state, history, revision data, and resume metadata. |
| KT-013b Snapshot export helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that exports the current match state and history into a durable save payload. |
| KT-013c Snapshot import helper | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add one helper that restores a valid match snapshot into the canonical runtime state. |
| KT-013d Replay log format | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the event log structure needed to replay actions in order with the original action IDs and revisions. |
| KT-013e Resume validation rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Reject snapshots that are incomplete, inconsistent, or incompatible with the current schema version. |
| KT-013f Recovery and replay tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover save/restore, resume after interruption, replay ordering, and failure on malformed or stale snapshots. |
| KT-013g Operator-facing recovery notes | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Document the eventual recovery and replay workflow only if the runtime contract changes in a way that affects operators. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: snapshot schema, export/import
  helpers, replay log shape, and resume validation.
- `tests/test_killteam_runtime.py`: persistence, recovery, replay, and failure
  tests.
- `docs/wiki/killteam.md`: human-facing recovery model if it changes.
- `docs/adr/0009-killteam-semantic-opponent.md`: authority and boundary notes
  for persistence and replay if it changes.
- `docs/wiki/roadmap.md`: progress and sequencing if KT-013 changes the plan.

Execution order:

1. KT-013a, because the snapshot schema is the substrate for persistence.
2. KT-013b and KT-013c, because export and import define the recovery path.
3. KT-013d, because replay depends on a stable event log shape.
4. KT-013e, because stale or incompatible snapshots must fail closed.
5. KT-013f, because the tests should lock down save, restore, and replay
   behavior.
6. KT-013g, because the docs should be updated after the recovery contract is
   settled.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-014a Fixture matrix | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Define the canonical fixture matrix that covers setup, markers, activations, combat, scoring, CP, and turn progression. |
| KT-014b Deterministic happy-path tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Add repeatable tests for the main legal flows through the full game loop. |
| KT-014c Failure-mode tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Add repeatable tests for illegal actions, stale state, uncertainty, and hidden-info rejection. |
| KT-014d Bridge-behavior tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Add tests that cover bridge disconnects, partial commits, and readback mismatches. |
| KT-014e Server-seam coverage | `tests/test_server.py` | `tts_mcp/app/server.py` | Verify the public tool surface still exposes the expected Kill Team actions and observation payloads after the runtime changes. |
| KT-014f Scenario fixture organization | `tests/fixtures/` or `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Organize reusable fixture builders so regression tests stay small, legible, and deterministic. |
| KT-014g Live-validation boundary | `docs/wiki/killteam.md`, `docs/wiki/roadmap.md` | `tests/test_killteam_runtime.py` | Document which tests are deterministic and which require live TTS validation, without mixing the two concerns. |
| KT-014h Regression checklist maintenance | `docs/wiki/killteam-tickets.md` | `tests/test_killteam_runtime.py` | Keep the execution checklist aligned with the actual regression surface as new game-loop layers land. |

File ownership:

- `tests/test_killteam_runtime.py`: deterministic scenario coverage and
  bridge-behavior regression tests.
- `tests/test_server.py`: only if the public Kill Team surface needs to be
  validated from the server seam.
- `tests/fixtures/` or `tests/test_killteam_runtime.py`: reusable fixture
  builders if the tests need shared setup helpers.
- `docs/wiki/killteam.md`: human-facing note about deterministic vs live
  validation if it changes.
- `docs/wiki/roadmap.md`: sequencing and validation-status notes if KT-014
  changes the plan.
- `docs/wiki/killteam-tickets.md`: the living checklist and execution order.

Execution order:

1. KT-014a, because the fixture matrix defines the scope of the regression
   suite.
2. KT-014b, because happy-path tests establish the baseline legal flows.
3. KT-014c, because failure modes lock down the boundary conditions.
4. KT-014d, because bridge-behavior regressions tend to surface only in
   interaction tests.
5. KT-014e, because server-seam checks should follow the runtime coverage.
6. KT-014f, because reusable fixtures keep the suite maintainable.
7. KT-014g, because the docs should clearly separate deterministic and live
   validation responsibilities.
8. KT-014h, because the checklist should stay synchronized with the evolving
   regression surface.

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

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-015a Kill Team wiki overview | `docs/wiki/killteam.md` | `docs/wiki/killteam-tickets.md` | Rewrite the Kill Team overview so it reflects the canonical state, the opponent role, and the current execution plan. |
| KT-015b ADR alignment pass | `docs/adr/0009-killteam-semantic-opponent.md` | `docs/wiki/killteam.md` | Make the ADR match the current runtime contract, including hidden-information boundaries and the staged opponent model. |
| KT-015c Roadmap status pass | `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Keep roadmap status labels synchronized with the KT-001 through KT-014 execution plan. |
| KT-015d API-reference cross-links | `docs/wiki/api-reference.md`, `docs/wiki/api-and-rules.md` | `docs/wiki/killteam.md` | Add or update links so the Kill Team-specific guidance is easy to find from the API and rules pages. |
| KT-015e Operator workflow notes | `docs/wiki/development.md` | `docs/wiki/killteam.md` | Document the practical workflow for testing, validating, and maintaining the opponent loop. |
| KT-015f README navigation pass | `docs/wiki/README.md` | `docs/wiki/killteam-tickets.md` | Make sure the wiki navigation points at the current Kill Team planning and implementation artifacts. |
| KT-015g Terminology consistency audit | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md`, `docs/wiki/api-reference.md` | `tts_mcp/runtime/killteam_runtime.py` | Align names for state, revision, visibility, scoring, and recovery so the docs and runtime use the same vocabulary. |
| KT-015h Documentation regression checks | `docs/wiki/killteam.md`, `docs/adr/0009-killteam-semantic-opponent.md`, `docs/wiki/roadmap.md` | - | Verify the final doc set still explains the same boundaries, order of implementation, and current limitations. |

File ownership:

- `docs/wiki/killteam.md`: Kill Team overview, opponent model, and operational
  guidance.
- `docs/adr/0009-killteam-semantic-opponent.md`: architecture and authority
  record.
- `docs/wiki/roadmap.md`: implementation sequencing and status labels.
- `docs/wiki/api-reference.md` and `docs/wiki/api-and-rules.md`: cross-links and
  rule-reference guidance.
- `docs/wiki/development.md`: operator workflow notes for testing and
  validation.
- `docs/wiki/README.md`: navigation only.
- `docs/wiki/killteam-tickets.md`: living checklist and planning artifact.

Execution order:

1. KT-015a, because the overview should be current before anything else points
   to it.
2. KT-015b, because the ADR should match the same contract as the overview.
3. KT-015c, because roadmap sequencing must reflect the current ticket plan.
4. KT-015d, because API and rules cross-links depend on the core guidance being
   stable.
5. KT-015e, because operator workflow notes should follow the stable docs.
6. KT-015f, because navigation should point at the settled planning artifacts.
7. KT-015g, because terminology drift should be caught after the main docs are
   aligned.
8. KT-015h, because the final doc set should be checked for consistency once
   the content is in place.

### KT-016 Setup deployment geometry model

Status:

- KT-016a and KT-016b are already implemented in the runtime.
- KT-016c and KT-016d remain to freeze stale-context gating and the regression matrix.

Define the live board-context model that setup planning will trust.

Question:

- What live geometry, occupancy, and revision facts must the setup planner see
  before it can decide whether a deployment slot is legal and still current?

Scope:

- Capture deployment-zone bounds, model footprints, terrain blockers,
  objectives, and visible enemy/friendly operatives in one revision-stamped
  context object.
- Treat map revision and placement context revision as hard validity gates.
- Keep the context bounded so the planner can reason about the board without
  scanning the entire scene ad hoc.
- Make legality fail closed when a candidate slot would overlap a model,
  protrude outside the deployment zone, or rely on stale geometry.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-016a Deployment-context snapshot | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the live setup context with deployment-zone bounds, terrain, objectives, friendly and hostile occupancy, and revision metadata. |
| KT-016b Footprint and clearance rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Decide how model bounds, terrain geometry, and objective footprints invalidate a candidate placement slot. |
| KT-016c Stale-context gating | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Fail closed when a placement plan is older than the current map revision or the live board changed after planning. |
| KT-016d Geometry regression tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover dense boards, boundary slots, overlapping models, and stale-revision rejection. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: deployment-context snapshot and
  legality gates.
- `tests/test_killteam_runtime.py`: dense-board and stale-context tests.

Execution order:

1. KT-016a, because the planner needs a canonical board-context snapshot.
2. KT-016b, because legality rules depend on how footprints and clearance are
   measured.
3. KT-016c, because stale-context handling must be decided before slot scoring
   can rely on it.
4. KT-016d, because the geometry contract should be pinned before the planner
   consumes it.

### KT-017 Context-aware setup placement policy

Status:

- KT-017a, KT-017b, and KT-017c are already implemented in the runtime.
- KT-017d remains to lock the placement-policy regression cases.

Decide how the setup planner should rank legal deployment slots.

Question:

- How should the planner score legal setup candidates across cover, exposure,
  objective pressure, friendly support, hostile threat lanes, and faction
  style?

Scope:

- Rank legal slots across the full deployment zone rather than defaulting to
  zone-center placement.
- Prefer cover and safe staging by default, but allow faction or mission style
  to bias toward aggressive pressure or objective contest.
- Keep tie-breakers deterministic so the same board state always yields the
  same placement choice.
- Make the planner explain its ranking so the AI can justify why a slot won.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-017a Candidate generation | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Enumerate legal deployment candidates across the available footprint instead of using a single center point. |
| KT-017b Tactical scoring model | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Define the score inputs for cover, exposure, objectives, friendly spacing, hostile proximity, and faction style. |
| KT-017c Deterministic tie-breaks | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Ensure repeated planning on the same context returns the same ranked result. |
| KT-017d Placement-policy tests | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover cover-first, objective-first, and threat-avoidance cases on the same fixture set. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: candidate generation, scoring, and
  ranking helpers.
- `tests/test_killteam_runtime.py`: tactical-policy regression tests.

Execution order:

1. KT-017a, because the scorer needs candidate placements to rank.
2. KT-017b, because the ranking contract is the core policy decision.
3. KT-017c, because deterministic tie-breaking keeps the planner stable.
4. KT-017d, because the chosen policy should be locked down with tests.

### KT-018 Setup turn-order policy

Status:

- KT-018a through KT-018d are implemented and covered by runtime and gameplay regression tests.

Decide which side acts next and how the current deployment pass advances when
placement is already planned from board context.

Question:

- What rule should decide the next setup side, the active batch, and when a
  pass is considered complete?

Scope:

- Keep the existing alternating deployment cadence, but define the pass
  boundary in terms of board state rather than a fixed center slot.
- Preserve the active batch across repeated observations until a legal commit
  advances it.
- Make the next-side decision deterministic when a batch completes, a side has
  no remaining legal placements, or the planner cannot improve the current
  pass.
- Keep the already-placed AI models in the setup state so the next pass can
  continue from the correct remainder.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-018a Next-side rule | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Decide how the setup state machine advances from one side to the next when the current pass is complete or exhausted. |
| KT-018b Batch carry-forward | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Decide how batch counters and already-placed models stay attached to the active pass across repeated observations. |
| KT-018c Planner handoff | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Decide how the tactical planner feeds the current pass without changing the alternating cadence. |
| KT-018d Turn-order tests | `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover side switching, batch completion, repeated observation stability, and deterministic pass advancement. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: setup turn-order, batch counters,
  and pass advancement rules.
- `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py`:
  turn-order and batch progression coverage.

Execution order:

1. KT-018a, because the next-side rule determines the rest of the turn-order
   contract.
2. KT-018b, because batch carry-forward has to stay consistent with the active
   pass.
3. KT-018c, because the planner has to feed the turn-order rule.
4. KT-018d, because the turn-order contract should be pinned with tests.

### KT-019 Setup recovery policy

Status:

- KT-019a through KT-019d are implemented and covered by runtime, gameplay, and controller regression tests.

Decide what setup state survives pauses, human batches, and host-triggered
resets.

Question:

- What should happen to setup history after `!ai start fresh`, a human
  reconciliation pass, an uncertain commit, or a pending placement rollback?

Scope:

- Define what `!ai start fresh` clears and what it preserves.
- Define when human-side reconciliation resumes AI setup after a human pass.
- Make rollback and uncertain-commit recovery explicit so placement can be
  retried only when the board state is still trustworthy.
- Keep recovery separate from turn-order so each policy stays narrow.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-019a Setup-history model | `tts_mcp/runtime/killteam_runtime.py`, `tts_mcp/app/ai_controller.py` | `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py` | Decide which deployed models, batches, and recovery markers persist across setup turns. |
| KT-019b Human resume rule | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_gameplay_runtime.py` | Decide when human-side reconciliation allows the AI to resume after a human pass. |
| KT-019c Reset and rollback rule | `tts_mcp/runtime/killteam_runtime.py`, `tts_mcp/app/ai_controller.py` | `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py` | Decide how fresh-start, rollback, and uncertain-commit cases clear or preserve setup history. |
| KT-019d Recovery tests | `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Cover history reset, replay of a pending setup turn, recovery after a stale or partial placement, and human resume behavior. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: setup recovery, resume markers, and
  commit rollback rules.
- `tts_mcp/app/ai_controller.py`: persisted setup-history reset behavior if
  the controller contract needs to change.
- `tests/test_killteam_runtime.py`, `tests/test_gameplay_runtime.py`:
  recovery and reset coverage.

Execution order:

1. KT-019a, because the recovery contract needs a history model.
2. KT-019b, because the human-resume rule determines when the AI may continue.
3. KT-019c, because fresh-start and rollback behavior must be defined
   together.
4. KT-019d, because the recovery policy should be pinned with tests.

### KT-020 Setup regression matrix and docs alignment

Status:

- KT-020a through KT-020d are implemented and covered by runtime tests, docs, and roadmap updates.

Decide the validation matrix and documentation updates for the new setup
planner.

Question:

- Which deterministic tests, live validation cases, and doc updates are
  required to prove the new geometry-aware setup path works on dense, blocked,
  and stale boards?

Scope:

- Define the fixture matrix for cover, overlap, objectives, hostile pressure,
  friendly spacing, and stale-revision cases.
- Keep deterministic runtime tests separate from any live TTS validation
  checklist.
- Update the wiki, roadmap, and API reference once the setup planner contract
  is settled.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-020a Deterministic fixture matrix | `tests/test_killteam_runtime.py` | `tts_mcp/runtime/killteam_runtime.py` | Define the dense-board and geometry fixtures used to validate the new deployment planner. |
| KT-020b Live validation checklist | `docs/wiki/killteam.md` | `docs/wiki/roadmap.md` | Spell out the live TTS scenarios needed to prove the planner-backed autorun path against the current Save 131 fixture or future equivalents, including the fail-closed no-legal-slot case. |
| KT-020c Wiki and API alignment | `docs/wiki/killteam.md`, `docs/wiki/api-reference.md`, `docs/wiki/api-and-rules.md` | `docs/wiki/roadmap.md` | Update the setup-phase wording so the public docs describe geometry-aware placement and the rejected fallback path instead of center-of-zone behavior. |
| KT-020d Roadmap status update | `docs/wiki/roadmap.md` | `docs/wiki/killteam-tickets.md` | Mark the new setup expansion as the next Kill Team setup workstream after the current slice. |

File ownership:

- `tests/test_killteam_runtime.py`: deterministic setup regression coverage.
- `docs/wiki/killteam.md`, `docs/wiki/api-reference.md`,
  `docs/wiki/api-and-rules.md`: setup guidance updates.
- `docs/wiki/roadmap.md`: sequencing and status updates.

Execution order:

1. KT-020a, because the regression matrix has to exist before validation can
   be trusted.
2. KT-020b, because live validation should be planned after the deterministic
   matrix is known.
3. KT-020c, because the public docs should describe the settled setup contract.
4. KT-020d, because the roadmap should point at the new setup workstream once
   the plan is clear.

### KT-021 Autorun setup gateway execution

Status:

- KT-021a through KT-021c are implemented and covered by runtime, gateway,
  and regression tests.

Question:

- How should `KILLTEAM_AUTORUN_SETUP` be routed so one AI-authored MOVE uses
  the placement-only bridge without entering the incompatible full runtime?

Scope:

- Treat the chat-level autorun request as one bounded AI placement turn.
- Advertise only setup ping and compact, explicitly tagged placement context.
- Keep terrain-aware y adjustment, model collision checks, and readback in the
  placement runtime; never call the full Save 131 planner as a fallback.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-021a Gateway placement handoff | `tts_mcp/app/http_gateway.py`, `tts_mcp/app/server.py` | `tests/test_http_gateway.py`, `tests/test_server.py` | Route `KILLTEAM_AUTORUN_SETUP` through the placement-only AI context and one model-authored MOVE path. |
| KT-021b Runtime fail closed | `tts_mcp/runtime/gameplay_runtime.py`, `tts_mcp/runtime/killteam_runtime.py` | `tests/test_gameplay_runtime.py`, `tests/test_killteam_runtime.py` | Keep the runtime setup macro fail-closed when it cannot produce a legal slot or the live board state is stale. |
| KT-021c Gateway regression test | `tests/test_http_gateway.py` | `tts_mcp/runtime/killteam_setup_runtime.py` | Prove that the chat-level autorun request does not dispatch the runtime macro, exposes only setup tools, and verifies one terrain-aware MOVE. |

File ownership:

- `tts_mcp/app/http_gateway.py`: autorun routing and runtime handoff.
- `tests/test_http_gateway.py`: gateway-level regression coverage.
- `tts_mcp/runtime/gameplay_runtime.py`, `tts_mcp/runtime/killteam_runtime.py`: runtime semantic setup flow, planner evidence, and stale-context support.

Execution order:

1. KT-021a, because the gateway handoff is the actual bug surface.
2. KT-021b, because the runtime fail-closed behavior must remain authoritative.
3. KT-021c, because the regression needs to prove the runtime macro is the path
   used by chat-level autorun.

### KT-022 Setup placement for operative tokens and equipment

Status:

- Planned as the next setup-placement slice after model placement is complete.

Question:

- How should setup-time placement cover operative tokens, equipment, and other
  non-model fixtures without widening the model-placement contract?

Scope:

- Place operative tokens, equipment, and similar setup fixtures through an
  explicit bounded placement path.
- Keep legality checks, readback, and failure handling separate from the
  model-placement workflow.
- Reuse the existing geometry and occupancy facts where fixture placement needs
  them, but do not force non-model items through model-specific assumptions.
- Keep the setup docs, roadmap, and regression coverage aligned with the
  fixture-specific placement contract.

Implementation subtasks:

| Subtask | Primary file(s) | Supporting file(s) | Outcome |
| --- | --- | --- | --- |
| KT-022a Token placement rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add explicit legality and placement handling for operative tokens and other setup markers. |
| KT-022b Equipment placement rules | `tts_mcp/runtime/killteam_runtime.py` | `tests/test_killteam_runtime.py` | Add placement handling for equipment and similar setup fixtures, including collision, snapping, and zone checks as applicable. |
| KT-022c Setup-context surface | `tts_mcp/app/http_gateway.py`, `tts_mcp/runtime/killteam_setup_runtime.py` | `tests/test_http_gateway.py`, `tests/test_killteam_setup_runtime.py` | Expose the bounded setup context needed to place tokens and equipment without broadening the full runtime. |
| KT-022d Regression and docs alignment | `tests/test_killteam_runtime.py`, `docs/wiki/killteam.md`, `docs/wiki/roadmap.md` | `tts_mcp/runtime/killteam_runtime.py` | Lock the token/equipment placement contract and describe the supported setup objects. |

File ownership:

- `tts_mcp/runtime/killteam_runtime.py`: token and equipment placement rules,
  legality checks, and readback hooks.
- `tts_mcp/app/http_gateway.py` and `tts_mcp/runtime/killteam_setup_runtime.py`:
  bounded setup-context exposure if the placement surface needs to broaden.
- `tests/test_killteam_runtime.py` and `tests/test_killteam_setup_runtime.py`:
  fixture-placement regression coverage.
- `docs/wiki/killteam.md` and `docs/wiki/roadmap.md`: setup-placement wording
  and sequencing updates.

Execution order:

1. KT-022a, because token placement needs a canonical legality contract first.
2. KT-022b, because equipment placement should reuse the same fixture model
   after the token path is settled.
3. KT-022c, because any setup-context expansion must stay bounded.
4. KT-022d, because the docs and regression surface should match the runtime
   contract once the placement behavior is stable.
