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
next AI card, the next setup card, and the next tactical deployment slot.

## Decision

Treat the chat-level `KILLTEAM_AUTORUN_SETUP` message as an AI setup request,
not as an executable runtime macro. The AI observes the live placement bridge,
starts from initiative when the game opens,
selects a fixed `ceil(N/3)` batch of distinct AI models and tactical positions,
emits one `SETUP_MOVE[candidate_id]` per model, and stops until a new setup request is
sent. For six models, each request therefore contains two setup commands. The gateway
translates those `MOVE` commands into the setup runtime's verified placement path, which
uses the dedicated placement action for the actual TTS commit while keeping the
placement-only bridge narrow. The setup flow also selects bounded equipment,
ploy, and tactical-op cards when those cards are present on the AI side. The
setup context exposes only explicitly tagged operatives, terrain, deployment
zones, and objectives. The setup turn cannot call the full runtime setup or
Save 131 planner. `setup_ping` proves loaded-vs-disk parity by reading the
active Global script and comparing its hash to the checked-in bridge source.

Each setup candidate has a stable candidate ID, operative GUID, source
position, exact target, terrain support, and model footprint. The gateway
requires every emitted `SETUP_MOVE` to name one live candidate from the
authoritative `recommended_batch` for the current turn and normalizes
the target to that candidate before dispatch. Legacy `MOVE[guid,x,y,z]` is
accepted only when its coordinates match the same candidate. It rejects a
cross-paired GUID/position, a no-op candidate, or overlapping candidates in a
single batch before any placement is sent to TTS. LayoutZone and
ScriptingTrigger deployment geometry uses the object's scale when TTS reports
zero-size bounds. Setup resume requests may be issued as `KILLTEAM_AUTORUN_SETUP`
or clear natural language such as "place your next model"; both use the same
placement-only validation path. Standalone setup command lines are parsed
separately from prose examples, and a malformed candidate token may only be
repaired to an unused candidate in the authoritative batch.

Because the placement bridge does not own controller history, its ranked
recommendations may include models placed by an earlier setup turn. After
filtering those models, the gateway refills an undersized recommendation from
the bridge-provided candidate pool, requiring distinct GUIDs and
non-overlapping footprints. The refill uses the remaining-model target, so a
final partial batch does not wait for a full `ceil(N/3)` group.
During a setup turn, the gateway now passes persisted placed GUIDs into the
context collector before ranking. This makes the primary planner history-aware
and leaves the refill as a defensive boundary rather than the normal path.
Placed GUIDs exclude models only from the move-candidate roster; the planner
continues to use every live operative, including placed AI and human models,
as an occupancy blocker when selecting each resumed batch.
If the AI emits fewer placement commands than the current batch requires, the
gateway completes the response from the fresh ordered `recommended_batch`
before validation. Completion is allowed only when that authoritative batch
contains exactly the required number of candidates. The completed batch still
passes candidate binding, spacing, occupancy, terrain-height, dispatch, and
readback verification. Extra, mixed, duplicated, stale, or insufficient
batches remain rejected.

The runtime resolves the placement `y` against terrain support at the target
footprint using the model's TTS pivot-to-bottom offset, so elevated deployment
pieces land on top of terrain instead of reusing the source `y` coordinate
blindly. The bridge returns the selected
support height and GUIDs, and the runtime reconciles that result before marking
the placement verified. If another model or objective already occupies the
footprint, the runtime rejects that slot instead of trying to force the model
through it.

- The runtime validates GUID ownership, coordinate shape, movement, and
  post-placement readback.
- The chat gateway forwards the setup request to the AI backend and consumes
  only the AI's bounded placement batch, rejecting duplicate GUIDs or an
  incorrect number of setup commands.
- Setup targets are recorded before dispatch. If TTS commits a placement but
  the request ends during readback, the next live setup context reconciles the
  pending model before selecting another batch.
- The host lifecycle command `!ai begin killteam` starts a brand-new Kill Team
  game, clears the controller's setup history, and immediately requests
  `KILLTEAM_AUTORUN_SETUP` so initial setup begins from scratch.
- `!ai start fresh killteam` remains a compatibility alias for the same full
  Kill Team startup path.
- The host lifecycle command `!ai start fresh` still clears the controller's
  setup history for a game that is already selected.
- Lower-level setup commands remain available for manual control, debugging,
  and tests, including the compatibility `setup_place_model` form.

## Consequences

The AI owns the tactical decision within the planner's recommended legal batch
at every placement while the runtime keeps
the mutation safe and testable. Human models remain human-placed.

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
