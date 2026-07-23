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

## 1. Current foundation

- `[done]` `tts_ping`, object listing, object detail, camera, screenshots.
- `[done]` Move, rotate, name, lock, spawn, destroy, and broadcast actions.
- `[done]` Game rules, session checkpoints, audit events, and AI gateway.
- `[done]` Host-only AI lifecycle/approval commands with persistent controller
  state and six-character alphanumeric action IDs.
- `[done]` Bounded `tts_execute_action_plan` with destructive-action opt-in.
- `[done]` Compile check and unit tests for action-plan validation.

## 2. Exact structured observation — next

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

## 3. API knowledge and tool contracts — next

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

## 4. Visual connectivity and verification — next

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

## 5. Reliable action planning

- `[done]` Add `dry_run` to action plans.
- `[done]` Add per-step preconditions and postconditions.
- `[done]` Add `verify_after_each`, settle time, and stop-on-failure.
- `[done]` Add bounded in-memory idempotency keys to prevent duplicate plan
  execution during client retries.
- `[planned]` Add affected-object summaries before and after every plan.
- `[planned]` Separate reversible, approval-required, and forbidden operations.

## 6. Semantic scene index

- `[done]` Resolve natural-language references into ranked candidate GUIDs with
  evidence and confidence scores.
- `[done]` Search names, tags, descriptions, types, and GUIDs.
- `[done]` Add explicit aliases such as “red player marker” or “supply deck”.
- `[done]` Return ambiguity instead of guessing tied or weak matches.
- `[done]` Persist aliases in SQLite and support game-scoped roles.

## 7. Game-domain tools

- `[done]` Inspect and manipulate bounded container contents.
- `[done]` Read zone occupancy and snap-point definitions.
- `[done]` Take from and put objects into containers.
- `[done]` Add scene requirement and zone occupancy validators.
- `[done]` Add placement tools for adjacent-to, inside-zone, and align-to.
- `[next]` Add on-top-of, snap-to-point, stack, and arrange operations.

## 8. Recovery and asynchronous execution — later

- `[later]` Scene snapshots for affected objects.
- `[later]` Rollback for reversible action plans.
- `[later]` Quarantine workflow for destructive operations.
- `[later]` Job IDs and status polling for spawn, physics, screenshots, and
  multi-frame operations.
- `[later]` Headless or live-TTS integration fixtures for protocol testing.

## 9. AI-to-game interaction — next

- `[done]` Forward ordinary in-game chat to the configured AI backend.
- `[done]` Add host-only lifecycle/status controls and persisted approvals.
- `[done]` Add D&D/game-specific prompt construction and intent-aware context.
- `[done]` Add bounded AI command parsing with host approval for destruction.
- `[done]` Add post-command readback verification and bounded retries.
- `[done]` Serialize AI command execution at persisted autonomous turn boundaries.
- `[next]` Add priority/FIFO scheduling for multiple queued autonomous turns.
- `[planned]` Add chess move planning, object mapping, and transition
  verification.

## Implementation order

Build in this order unless a production issue changes the priority:

1. Expand structured object observation.
2. Add spatial queries and placement validation.
3. Add searchable API/capability documentation.
4. Add screenshot calibration and metadata.
5. Add focus-object capture and visual before/after verification.
6. Add action-plan idempotency and affected-object snapshots.
7. Add game setup and invariant validators.
8. Add high-level placement tools.
9. Add snapshots, rollback, and asynchronous jobs.

Every step should update the relevant wiki page, README tool inventory, Lua
dispatcher, Python tests, and live-TTS validation notes where applicable.
