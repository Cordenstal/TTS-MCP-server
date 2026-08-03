# Roadmap

Status labels:

- `[done]` implemented and validated.
- `[next]` highest-value work for the next implementation cycle.
- `[planned]` agreed direction, not yet scheduled.
- `[later]` useful after the foundations are stable.

## 0. Working principles

- Read structured state before mutating the game.
- Resolve objects by GUID; names and visual descriptions are discovery hints.
- Treat TTS state as authoritative and screenshots as complementary evidence.
- Keep every bridge action explicit, bounded, typed, and documented.
- Return post-action state whenever the TTS API can provide it.
- Require approval for destruction, broad scene changes, and hidden-information
  access.
- Preserve request IDs, callback semantics, and compatibility with existing
  Global scripts.

## 1. Safe generic control-plane MVP — current priority

- `[done]` Select the product boundary: explicit MCP scene control, not
  autonomous generic game play.
- `[done]` Define visibility-safe observations, configurable player identity,
  exact-GUID mutation, scene epochs, and fail-closed uncertainty behavior.
- `[done]` Define scene-only, fail-fast plans with single-owner serialization,
  20-step/60-second budgets, durable idempotency, and post-state verification.
- `[next]` Build the capability registry and versioned result/error schemas.
- `[next]` Add the deterministic fake bridge and policy-focused test fixture.
- `[next]` Implement the MVP reversible action set: move, rotate, rename, and
  lock/unlock existing visible objects.
- `[next]` Add Python/Lua compatibility tests and opt-in live-TTS validation.

Completion criteria:

1. A client can inspect visible structured state and resolve one object
   uniquely.
2. A bounded plan can perform one reversible action and return verified
   post-state with freshness metadata.
3. Ambiguity, hidden state, stale preconditions, concurrent plans, bridge
   disconnects, and unknown commits fail closed with stable error classes.
4. The same contract passes deterministic tests and an opt-in live-TTS smoke
   test against a dedicated game-neutral fixture.

## 2. Current foundation

- `[done]` `tts_ping`, object listing, object detail, camera, screenshots.
- `[done]` Move, rotate, name, lock, spawn, destroy, and broadcast actions.
- `[done]` Game rules, session checkpoints, audit events, and AI gateway.
- `[done]` Host-only AI lifecycle/approval commands with persistent controller
  state and six-character alphanumeric action IDs.
- `[done]` Bounded `tts_execute_action_plan` with destructive-action opt-in.
- `[done]` Compile check and unit tests for action-plan validation.
- `[done]` Guarded numbered-save inspection/editing with timestamped backups.
- `[done]` Explicit Windows GUI save loading with bounded coordinate profiles and
  post-load callback reporting.

## 3. Exact structured observation — next

Make the AI able to answer “where exactly is this object?” without relying on
an image.

- `[done]` Expand object summaries with bounds, normalized bounds, visual
  bounds, velocity, angular velocity, resting state, smooth-move targets,
  transform axes, zone GUIDs, and container item summaries.
- `[done]` Add nearest-object and axis-aligned world-region queries using
  object centers and world-space bounds.
- `[done]` Add distance and relative-transform queries.
- `[next]` Add distance and relative-transform queries.
- `[next]` Add zone membership, container membership, and snap-point details.
- `[next]` Add spatial-placement validation before a move or spawn.

Completion criteria:

1. A test fixture can place several objects with known bounds.
2. The MCP can distinguish their centers, extents, and nearest neighbors.
3. A placement request can report overlap, clearance, and final error.

## 4. API knowledge and tool contracts — next

Give the AI a searchable, local explanation of what the MCP and TTS API can do.

- `[done]` Add `tts_describe_capabilities` with tool categories, mutation
  status, confirmation requirements, and verification expectations.
- `[next]` Add `tts_search_api_docs` and `tts_get_api_reference`.
- `[next]` Document coordinate systems, rotations, GUIDs, object types,
  containers, zones, physics, timing, and visibility boundaries.
- `[next]` Add game-specific rule/index files without mixing them into the
  generic TTS API reference.
- `[next]` Add schema examples for every read and write tool.

Completion criteria:

1. A new contributor can discover an action without reading implementation
   code.
2. The model can determine whether an action is safe and what it returns.
3. API docs and actual bridge handlers are checked for drift.

## 5. Visual connectivity and verification — next

- `[done]` Add screenshot metadata: rectangle, dimensions, timestamp, output
  size, mean color, contrast, and blank-frame health.
- `[done]` Add screen-region calibration with monitor inventory and
  stale/blank-frame detection.
- `[done]` Add focus-object-and-capture using object bounds.
- `[done]` Add structured object-settle polling for smooth movement.
- `[next]` Add before/after visual verification for action plans.
- `[next]` Add optional annotated screenshots with GUID labels, bounds, axes,
  and target markers generated on the Python side.

Completion criteria:

1. The system can prove that the configured rectangle contains TTS.
2. A camera move waits for settlement before capture.
3. A mutation can return structured and visual verification evidence.

## 6. Reliable action planning

- `[done]` Add `dry_run` to action plans.
- `[done]` Add per-step preconditions and postconditions.
- `[done]` Add `verify_after_each`, settle time, and stop-on-failure.
- `[done]` Add bounded in-memory idempotency keys to prevent duplicate plan
  execution during client retries.
- `[planned]` Add affected-object summaries before and after every plan.
- `[planned]` Separate reversible, approval-required, and forbidden operations.

## 7. Semantic scene index

- `[done]` Resolve natural-language references into ranked candidate GUIDs with
  evidence and confidence scores.
- `[done]` Search names, tags, descriptions, types, and GUIDs.
- `[done]` Add explicit aliases such as “red player marker” or “supply deck”.
- `[done]` Return ambiguity instead of guessing tied or weak matches.
- `[done]` Persist aliases in SQLite and support game-scoped roles.

## 8. Game-domain tools

- `[done]` Inspect and manipulate bounded container contents.
- `[done]` Read zone occupancy and snap-point definitions.
- `[done]` Take from and put objects into containers.
- `[done]` Add scene requirement and zone occupancy validators.
- `[done]` Add placement tools for adjacent-to, inside-zone, and align-to.
- `[next]` Add on-top-of, snap-to-point, stack, and arrange operations.

## 9. Recovery and asynchronous execution — later

- `[planned]` Add save-file backup discovery and operator-assisted rollback.
- `[later]` Scene snapshots for affected objects.
- `[later]` Rollback for reversible action plans.
- `[later]` Quarantine workflow for destructive operations.
- `[later]` Job IDs and status polling for spawn, physics, screenshots, and
  multi-frame operations.
- `[later]` Headless or live-TTS integration fixtures for protocol testing.

## 10. AI-to-game interaction — later adapter work

- `[done]` Forward ordinary in-game chat to the configured AI backend.
- `[done]` Add host-only lifecycle/status controls and persisted approvals.
- `[done]` Add game-specific opponent prompt construction and intent-aware context.
- `[done]` Add bounded AI command parsing with host approval for destruction.
- `[done]` Add post-command readback verification and bounded retries.
- `[done]` Serialize AI command execution at persisted autonomous turn boundaries.
- `[done]` Add the hybrid checkers domain seam: TTS physical observations,
  durable canonical position, deterministic legal move generation, alpha-beta
  tactical search, complete multi-jump execution, and post-landing
  reconciliation.
- `[done]` Require explicit player prompting for Save 128 Black turns and
  mutual agreement for draws.
- `[done]` Start player chat without automatic scene lists or screenshots.
- `[done]` Add a validated, read-only observation tool loop with native and
  strict-JSON backend protocols, compact ephemeral results, and 4-call/15-second
  defaults.
- `[next]` Add priority/FIFO scheduling for multiple queued autonomous turns.
- `[planned]` Add chess move planning, object mapping, and transition
  verification.
- `[next]` Run an opt-in live Save 128 full-game validation and calibrate search
  depth/time against the local AI backend and TTS physics.

## 11. Kill Team semantic opponent — live fixture integration next

The first high-level game adapter targets the `Kill Team 3.0 Quick and Easy`
variant and the canonical `TS_Save_131.json` fixture. The complete design is
recorded in [the Kill Team wiki page](killteam.md),
[ADR-0009](../adr/0009-killteam-semantic-opponent.md), and
[ADR-0010](../adr/0010-native-killteam-fixture-profiles.md). The execution
backlog is tracked in [Kill Team opponent tickets](killteam-tickets.md).

- `[done]` Implement the agreed AI-opponent role, hidden-information boundary, and
  host-adjudication policy.
- `[partial]` Implement setup discovery, AI-side dice/counters, map
  calibration, mutable terrain, and player-perspective observation.
  Deterministic canonical-tag tests pass; native `TS_Save_131.json` profile
  normalization remains.
- `[done]` Define the versioned Kill Team state schema and event types.
- `[partial]` Build setup ingestion and fail-closed invariant validation.
  Native tags, exact anchors, and global snap-point uniqueness remain. Generic
  roster-card setup now validates clean starts, initiative as a first-class
  setup stage, roster legality, physical model availability, and official
  alternating deployment-pass cadence.
- `[partial]` Add role-filtered structured observations. Approved camera views
  for activation/attack preparation remain.
- `[partial]` Implement calibrated combat-zone geometry, terrain overrides,
  and range queries. On-demand nine-ray physics LOS evidence is implemented;
  collider calibration, cover policy, and mutable-map evidence reconciliation
  remain.
- `[done]` Implement the typed rules adapter for one ranged activation.
- `[partial]` Implement semantic movement, shooting, dice rolling, saves,
  damage, and wounds. Resource/scoring projections remain.
- `[done]` Route Kill Team `Your turn` prompts to a bounded tactical-turn
  request that claims the initiative token, performs one legal AI action, and
  passes initiative to the next player.
- `[partial]` Add uncertain-commit recovery and action idempotency. Human-event
  reconciliation and host rulings remain.
- `[done]` Validate the first slice against a deterministic fake bridge.
- `[partial]` The native `TS_Save_131.json` fixture profile and opt-in
  setup-validation pipeline are implemented and covered by deterministic
  bridge/runtime tests. A fresh-save live TTS run remains.
- `[planned]` Replace the current keyword-based deployment style heuristic with
  an explicit faction heuristics tag map so team play style can be configured
  from tags instead of inferred ad hoc from names and profiles.

### Kill Team vertical-slice update plan

This update closes the observation and physical LOS seams so the same deep Kill
Team module can be used by both an MCP client and the in-game HTTP AI gateway.
Work remains bounded to setup, observation, and the existing one-operative
ranged-action slice:

1. `[done]` Define one role-filtered observation contract containing the AI
   roster, visible enemy operatives, tagged terrain, dice/counter references,
   map revision, observation ID, and truncation/uncertainty status.
2. `[done]` Add an explicit gateway setup/observation adapter. Setup must run
   once per loaded game before the AI can request Kill Team state; repeated
   setup must replace the prior scene epoch rather than reuse stale state.
3. `[done]` Expose bounded Kill Team observation tools to the AI backend while
   keeping arbitrary mutations behind the semantic MCP interface. The gateway
   may execute only the bounded semantic initial-placement command after a
   role-filtered observation; it must not expose raw hidden objects or Lua.
   The semantic setup surface now also covers AI roster-card selection, roster
   locking, one-card-at-a-time setup deployment, rollback of the pending setup
   operative, and one-step human-side reconciliation.
4. `[done]` Make compact object evidence sufficient for inspection by retaining
   descriptions/profile metadata, exact type, tags, transforms, bounds, and
   truncation information. Add the bounded fallback roster query for dedicated
   AI container `e5adb7`; large boards must use an intentional summary rather
   than silently dropping objects. The dedicated snapshot avoids generic
   enumeration and now normalizes native fixture tags plus global snap points.
5. `[partial]` Validate the Python-to-Lua observation request/response path with a
   fake bridge and Lua source compatibility checks, including empty scenes,
   large scenes, hidden objects, missing setup, and callback errors. The
   bounded LOS probe now has fake-bridge/runtime/source coverage; live TTS
   callback coverage remains.
6. `[done]` Add an on-demand nine-ray Kill Team LOS probe. It ignores the
   observer collider, identifies first blockers, returns target visibility
   fraction and collider uncertainty, and is called by ranged shooting before
   dice are rolled.
7. `[done]` Add a versioned Python fixture profile for `TS_Save_131.json`.
   Normalize its native tags and stable anchors through fixture-agnostic,
   bounded Lua tag/GUID/snap-point queries. Treat the save and expected GUIDs
   as test oracles; use only live TTS evidence for actions.
8. `[done]` Resolve the unique `_start_test_spot`, discover deployment subject
   `96fe20` and visible ranged target `377732`, place and verify the subject,
   then require at least one successful target ray from the nine-ray LOS probe.
9. `[done]` Add the resumable human defense-roll handoff. The AI rolls only its
   four Boltgun dice through `175503`; Red rolls three defense dice through
   read-only station `f1adc9` and explicitly acknowledges completion.
10. `[done]` Add semantic wound projection and readback against the operative's
    real wound state; rename-only damage is invalid.
11. `[next]` Run the complete opt-in live sequence from a freshly loaded
    fixture. Persist detailed audit evidence, leave the resulting scene intact,
    and stop on uncertain callbacks, collider mismatch, visibility
    contradiction, or missing human acknowledgment.
12. `[done]` Add a placement-only Kill Team setup bridge and runtime that can
    ping, list objects, and place a live model at an exact coordinate without
    loading the larger setup/combat runtime.

## 12. Setup expansion — next

The runtime already has the first playable setup slice: roster/deployment
cadence, a tactical placement planner, and the Save 131 validation path. KT-018
through KT-021 are now settled. Model placement is complete; the next setup
slice covers operative tokens, equipment, and other non-model fixtures.
`KILLTEAM_AUTORUN_SETUP` is a bounded AI placement turn through the
placement-only bridge, not a full-runtime batch macro. The gateway advertises
only setup ping and compact setup context, and the runtime verifies one
terrain-aware placement before stopping. The fresh-start launcher for a new
game is `!ai begin killteam`; it selects Kill Team if needed and then starts
the autorun setup path. `!ai start fresh killteam` remains a compatibility
alias.

- `[done]` Define the deployment-context snapshot and occupancy rules that the
  setup planner will trust before it scores any slot. This is the
  geometry-and-staleness foundation for KT-016.
- `[done]` Add candidate generation and tactical scoring for cover, exposure,
  objective pressure, friendly spacing, hostile threat lanes, and faction
  style. This is the core placement-policy work for KT-017.
- `[done]` Wire the planner into the setup state machine so each alternating
  pass advances the correct side and batch instead of falling back to a
  zone-center move. This is KT-018.
- `[done]` Define the setup recovery policy so fresh-start, human
  reconciliation, pending placements, and uncertain commits behave
  predictably. This is KT-019.
- `[done]` Lock the regression matrix and docs alignment so dense boards,
  blockers, objectives, and stale revisions stay covered by deterministic
  tests and live validation notes. This is KT-020.
- `[done]` Route `KILLTEAM_AUTORUN_SETUP` to one AI-authored `MOVE` turn with a
  placement-only context tool; keep terrain-aware y adjustment and model
  collision validation in the placement runtime. This is KT-021.
- `[next]` Add setup placement for operative tokens, equipment, and other
  non-model fixtures using a separate bounded fixture-placement ticket. This is
  KT-022.

Completion criteria:

1. Setup can explain why a slot is legal, blocked, or stale before it moves a
   model.
2. The planner can pick a non-center slot based on actual board context.
3. Re-running setup on the same board yields the same choice and the same
   recovery behavior.
4. The docs and regression matrix describe the same setup contract as the
   runtime plan.
5. Setup-time tokens and equipment have their own bounded placement contract
   instead of being folded into the model-placement workflow.

### Setup expansion workplan

Work the remaining setup expansion in the following order so the next layer
has the state it depends on before it lands:

1. KT-022, because token and equipment placement should build on the completed
   model-placement contract instead of widening it.

Each ticket should finish with tests and docs for its own scope before the
next one starts. That keeps the runtime changes reviewable and avoids
accidentally broadening the setup contract while it is still being shaped.

## Later implementation order

After the generic MVP is stable, build in this order unless a production issue
changes the priority:

1. Expand structured object observation.
2. Add spatial queries and placement validation.
3. Add searchable API/capability documentation.
4. Add screenshot calibration and metadata.
5. Add focus-object capture and visual before/after verification.
6. Add action-plan idempotency and affected-object snapshots.
7. Add game setup and invariant validators.
8. Add high-level placement tools.
9. Add snapshots, rollback, and asynchronous jobs.
10. Add the Kill Team setup, observation, rules, semantic-action, and
    reconciliation vertical slice described in section 11.

Every step should update the relevant wiki page, README tool inventory, Lua
dispatcher, Python tests, and live-TTS validation notes where applicable.
