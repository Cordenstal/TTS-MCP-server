# Kill Team opponent

This page records the agreed design for the first serious game-specific
opponent: the AI plays one side of the `Kill Team 3.0 Quick and Easy` variant
represented by the canonical `TS_Save_131.json` fixture.

## Role and authority

The AI is an autonomous opponent, not a generic scene manipulator. It may
execute legal, non-destructive Kill Team actions after announcing a bounded
plan. It must pause for missing rules, ambiguous observations, host rulings,
or uncertain TTS commits.

The Python runtime owns the versioned canonical game state and append-only
event log. TTS is the physical projection and an observation source. Every
semantic action is validated, committed once with an action ID, projected to
TTS, and post-verified. Unknown commit status enters read-only recovery;
actions are never retried automatically.

The AI receives a role-filtered observation projection:

- complete state for its own roster, dice, counters, and private setup;
- public terrain, deployment areas, objectives, and coordinates;
- enemy models only when currently observable, with last-known information
  kept separate from current facts;
- no opponent hidden deployment, private zones, or concealed object data.

## Setup lifecycle

Starting a game is an explicit setup phase:

1. Select the versioned fixture setup profile for the loaded save.
2. Discover native tagged objects, exact stable anchors, and global snap points
   in the live TTS table through bounded queries.
3. Bind team ownership to TTS player identity/color.
4. Validate the AI roster, dice, roller, CP, VP counters, terrain,
   deployment areas, objectives, and calibration markers.
5. Build the role-filtered initial state and report every ambiguity.
6. Freeze the initial map model and enable semantic gameplay only after setup
   succeeds.

Canonical runtime metadata uses the versioned `tts_mcp:` vocabulary, but a
supported save does not need to be rewritten to contain those tags. A Python
fixture setup profile maps native tags and stable anchors into canonical
roles. Lua remains fixture-agnostic and exposes only bounded tag, exact-GUID,
and global-snap-point queries. Setup fails closed on missing, duplicate, or
contradictory mappings. The save file is a fixture definition and test oracle;
live TTS observations remain authoritative for every actionable fact.

The `TS_Save_131.json` fixture binds the AI to Blue and the Plague Marines.
It references AI dice `2831c0`, `bde8ee`, `87bb98`, `967871`, `ffeef7`, and
`d08c28`; AI roller `175503`; CP counter `2cc38b`; Kill VP `d9b193`; Tac VP
`7ff953`; and Crit VP `53befd`. The Red player owns read-only roll station
`f1adc9`. Its native roles include `_dice_blue`, `dice_roller`,
`_deployment_zone_blue`, `combat_zone`, `KT_MISSION_TERRAIN`, and
`KT_MISSION_OBJECTIVE`. These are fixture references, not permanent gameplay
identities.

The model descriptions may be parsed once for static profile data. Dynamic
wounds, AP, statuses, activations, resources, and scoring remain runtime state
and may be mirrored to TTS names, counters, and markers.

When the Save 131 fixture profile is not in use, the runtime can also enter a
generic semantic pregame-setup mode. In that mode it discovers side-tagged
faction-deck containers, roster model containers, `Roster List <side>` zones,
`Deployed Zone <side>` zones, and deployment zones, then tracks initiative,
roster locking, and deployment cadence in the typed state machine.
The generic object scan first tries the canonical `tts_mcp:` setup tags, then
falls back to a raw compact scene scan when that canonical scan is empty.

### Setup contract gaps

The current implementation already covers the Save 131 setup-validation
vertical slice, the roster/deployment cadence, the tactical placement
planner, and the KT-018 through KT-020 setup contract. The remaining setup
work is KT-021 gateway enforcement for `KILLTEAM_AUTORUN_SETUP`.

- KT-021: what the gateway must do to keep `KILLTEAM_AUTORUN_SETUP` on the
  planner-backed legal slot path and fail closed when no legal slot exists.

### Setup decision checklist

KT-018 through KT-020 are settled and the answers below are now reflected in
the runtime, tests, and backlog. KT-021 remains open.

1. KT-016: What exact board-context facts must the planner trust before it
   scores a deployment slot?
   - Decide the minimum live geometry, occupancy, objective, and revision
     snapshot the planner can rely on.
   - Decide which stale-context conditions fail closed.
   - Decide whether the context is derived once per setup turn or refreshed
     before every placement recommendation.
2. KT-017: How should legal setup slots be ranked?
   - Decide the score inputs for cover, exposure, objective pressure, friendly
     spacing, hostile lanes, and faction style.
   - Decide the tie-break order so repeated planning is deterministic.
   - Decide whether the current `ceil(N/3)` cadence should prefer safety,
     pressure, or a named faction policy when those preferences conflict.
3. KT-018: What ends a setup pass and how does the next side advance?
   - Decide whether the current alternating cadence is fixed or configurable.
   - Decide how the current batch is preserved across repeated observations.
   - Decide what happens when a side has no remaining legal placements or the
     planner cannot improve the current pass.
4. KT-019: What setup history survives recovery?
   - Decide what `!ai start fresh` clears versus preserves.
   - Decide how human reconciliation resumes AI setup after a human batch.
   - Decide how pending placements and uncertain commits are retried, rolled
     back, or invalidated.
5. KT-020: What proves the setup contract is settled?
   - Decide the deterministic fixture matrix for dense boards, blockers,
     objectives, hostile pressure, and stale revisions.
   - Decide which live Save 131 scenarios remain mandatory.
   - Decide which public docs and API references must change with the final
     contract.

### Setup decision table

| Ticket | Current state | Settled answer | Default owner |
| --- | --- | --- | --- |
| KT-016 | The runtime already builds a live deployment snapshot for setup planning, including deployment-zone bounds, terrain blockers, objectives, and visible occupancy. | Settled: one revision-stamped snapshot per setup turn with hard stale-context gates on map revision, occupancy, objective, and support-height changes. | Runtime + docs |
| KT-017 | The runtime already computes a tactical recommended position from live geometry and faction play style. | Settled: explicit faction-style mapping first, then deterministic tie-breaks over priority, objective distance, cover, threat distance, exposure, path distance, and board coordinates. | Runtime + docs |
| KT-018 | The runtime already tracks alternating setup passes, batch progress, and pass completion after successful placements. | Settled: `ceil(N/3)` remains the cadence, batch carry-forward is stable across repeated observations, and the pass advances when the batch is complete or no legal placements remain. | Runtime + gameplay |
| KT-019 | The runtime already has rollback and reconciliation hooks for setup deployment. | Settled: `!ai start fresh` clears setup history, human reconciliation resumes only after explicit batch acknowledgment, and unsafe uncertain commits stay in read-only recovery. | Runtime + controller |
| KT-020 | The docs, tickets, and API pages now agree that the setup slice exists but is still contract-staged. | Settled: deterministic dense-board fixtures, Save 131 live validation notes, and docs/API wording now match the geometry-aware setup contract. | Docs + tests |

### Setup grilling sequence

| Step | Ticket | Question | Recommended answer |
| --- | --- | --- | --- |
| 1 | KT-016 | What is the minimum board-context snapshot the planner must trust before it ranks a slot? | Use one revision-stamped snapshot per setup turn with deployment-zone bounds, terrain support surfaces, objective footprints, visible friendly/enemy occupancy, support-height metadata, and a hard stale-context gate on map revision or affecting occupancy/objective/support changes. |
| 2 | KT-017 | What should the planner optimize when multiple legal slots exist? | Use an explicit faction-style map first, fall back to tag inference, and break ties deterministically after the style-specific priority, objective distance, cover, threat distance, exposure, path distance, and board coordinates. |
| 3 | KT-018 | What ends a setup pass and advances the next side? | Keep the alternating cadence with `ceil(N/3)` as the default, keep the current batch fixed until it is complete, and advance once the batch is done unless the board is stale or ambiguous. |
| 4 | KT-019 | What setup history survives recovery and host reset? | Make `!ai start fresh` a full table reset back to selected teams, add a separate board-reset command that preserves team and roster choices while clearing deployed board state, resume only after explicit human batch-complete acknowledgment, and use read-only recovery for unsafe uncertain commits. |
| 5 | KT-020 | What proves the setup contract is stable enough to freeze? | Lock a deterministic fixture matrix, keep Save 131 as the canonical live validation path, add fixture-specific live checklists only when a new profile is supported, and update the docs and API wording to match the final contract. |

### Settled decisions

- KT-016 is a per-turn revision-stamped snapshot, not an indefinite cache.
- KT-016 fails closed on geometry revision changes and on occupancy,
  objective, or support-height changes that affect legality or scoring.
- KT-017 uses an explicit faction-style map first, with tag inference as the
  fallback.
- KT-017 keeps deterministic tie-breaks after the style-specific priority,
  objective distance, cover, threat distance, exposure, path distance, and
  board coordinates.
- KT-018 keeps `ceil(N/3)` as the default cadence and fixes the current batch
  until it is complete.
- KT-018 advances once the batch is complete unless the board is stale or
  ambiguous.
- KT-019 makes `!ai start fresh` a full table reset to the selected-team
  point.
- KT-019 adds a separate board-reset command that preserves the selected teams
  and roster choices while clearing deployed board state.
- KT-019 resumes setup only after explicit human acknowledgment that the batch
  is complete.
- KT-019 rolls back uncertain or partial commits only when the runtime can
  prove the rollback is safe; otherwise it stops in read-only recovery.
- KT-020 treats Save 131 as the canonical live validation path.
- KT-020 requires deterministic coverage for dense boards, boundary slots,
  overlaps, objectives, hostile pressure lanes, friendly spacing, stale
  revisions, and the current Save 131 flow.

## Observation and map model

Before each activation and before each attack, the AI must obtain a fresh
observation. It may use structured object queries and approved camera views in
the public combat zone or its own side. Screenshots provide context and
evidence; they do not bypass visibility rules or replace exact structured
identity and coordinates.

The MCP client and in-game AI gateway share the same setup/observation seam.
`tts_killteam_setup` creates a fresh scene epoch by discovering the tagged live
table through bounded bridge actions. The fixture profile supplies native query
tags and exact anchors; the Lua bridge does not hard-code this fixture and
falls back to a raw compact scene enumeration only when the canonical tagged
scan is empty.
The placement-only setup bridge is separate from that full runtime. It
exposes `tts_killteam_setup_ping`, `tts_killteam_setup_context`,
`tts_killteam_setup_list_objects`, and `tts_killteam_setup_place_model` for
manual or debug compatibility. The AI-owned setup turn uses the dedicated
placement action; the legacy move alias remains available for compatibility.
The context tool includes only explicitly tagged
live operatives, terrain, deployment-zone, and objective objects so the AI can
inspect the footprint before it commits to a position. During this turn the
gateway does not advertise or invoke the full setup or Save 131 planner. A
missing or malformed MOVE is rejected rather than replaced by a center or
planner fallback.
`tts_killteam_setup_ping` now verifies that the loaded Global script matches
the checked-in `tts_killteam_setup_global.lua` before any placement command
runs.
`KILLTEAM_AUTORUN_SETUP` is a chat-level AI setup request, not a runtime Lua
  macro; the gateway turns it into one bounded AI placement batch through the
  placement bridge and then stops for that turn. The batch size is fixed at
  `ceil(N/3)` for the setup session, so six Plague Marines are placed as `2+2+2`.
`tts_killteam_observe` then returns the current revision, observation ID,
visible operative records, terrain, AI dice references, counters, roller GUID,
and an explicit truncation flag. Setup is a start-of-game operation and must
not be repeated during an activation. The gateway exposes these two bounded
tools to the AI backend. The gateway also accepts the bounded semantic
`tts_killteam_plan_objective_move` planner for objective-control placement and
`SETUP_MOVE[candidate_id]` command for initial AI placement; the runtime uses the live
figurine GUID at the move step and keeps the semantic operative identity
separate. Activation and attacks remain on the semantic MCP interface.

During AI-owned setup and the deployment smoke test, the runtime now projects
the placement `y` value onto the highest terrain support under the model
footprint so elevated terrain is respected instead of clipping the model into
the surface. The bridge reports the support surface used, and the runtime
accepts the elevated read-back only when it matches that evidence. If another
model or objective occupies the footprint, the slot is rejected and the AI must
choose a different position.

`tts_killteam_probe_line_of_sight` is the bounded physical visibility query.
It accepts semantic attacker and visible-target IDs, converts them to TTS
object GUIDs inside the runtime, and asks Lua to cast exactly nine rays from
the attacker's configurable local eye point to a 3x3 target silhouette. Lua
ignores the observer's own collider, reports the first relevant hit for each
sample, and returns visible-ray count, visibility fraction, blocker GUIDs,
sample points, and collider uncertainty. The AI should call this before
moving into an exposed lane and before preparing a ranged attack. It is an
on-demand query; it is not run every frame.

`tts_killteam_search_deployment_names` is the bounded name-resolution query for
the supported live fixture. It searches the known Plague Marine, Novitiate
Dialogus, and deployment names without enumerating the full scene, then
returns compact live summaries. Call it before movement or LOS work and
confirm the intended model's `Figurine` type, `Operative` tag, faction tags,
and unique live GUID.

### Validated named-model attack workflow

The live attack test establishes the bounded workflow for models that have
display names and faction tags rather than canonical `tts_mcp:*` tags:

1. Use `tts_killteam_search_deployment_names`, normalize display-name markup,
   and require one live `Figurine` matching the intended name, `Operative`, and
   faction tags. The Plague Marine Warrior requires Chaos/LEGIONARY evidence;
   Novitiate Dialogus requires Imperium/NOVITIATE evidence. The returned GUIDs
   are authoritative only for that current action.
2. Resolve named Blue Dice individually and require their `_dice_blue` tags.
   Resolve the unique Blue roller from `_blue_dice_roller`; it may be used to
   recover a die from an earlier failed attempt, but it is not the roll API.
3. Run the nine-ray physics LOS probe against the resolved GUIDs. At least one
   target ray is required before a ranged attack dice commit.
4. Invoke TTS's native `Object.roll()` operation for the selected physical
   dice. Do not use `putObject` to insert them into the roller: that bypasses
   the roller's player-drop callback and produces no roll. Wait for native
   dice to settle before reading their upward faces.
5. A missing face after the roll is an uncertain physical commit. Keep the
   dice/result in place and use read-only settled-value recovery; never reroll
   automatically. Do not project wounds until the defender provides physical
   save results, including whether a save is normal or critical.

`tts_killteam_get_roster` is the fallback roster query. It reads only the
dedicated AI roster container, currently GUID `e5adb7`, and returns bounded
contained-item metadata such as names, descriptions, tags, and item GUIDs.
Setup always verifies that the container exists, but the AI inspects its
contents only when a live operative lacks required profile/identity data or
another operative must be selected. It must not use arbitrary container
inspection to discover hidden state.

The combat zone is discovered for each game. Its model includes tagged terrain,
deployment areas, objectives, objects, and coordinates. Terrain is mutable:
doors, barricades, objectives, or other map objects may change during play.
Each change creates a new map revision and invalidates affected LOS results.

TTS coordinates use `x` and `z` for the horizontal board plane and `y` for
height above that plane. Setup calibration defines the board origin, axis
orientation, ground height, and world-units-per-inch scale. Rules calculations
use Kill Team inches; TTS coordinates are used for placement and physical
queries.

Placement candidates are server-owned records rather than independent AI
coordinate guesses. A candidate binds one eligible, undeployed AI operative
GUID to one target and footprint, while every live operative remains an
occupancy blocker, including already placed AI and opponent models. Setup
rejects a target copied from another model, rejects a same-position no-op,
validates all candidates in the batch before dispatch, and then rechecks
occupancy after each verified placement. Elevated terrain support determines
the final `y`; for zero-size deployment LayoutZones, the zone transform scale
supplies the horizontal deployment rectangle.

A fresh setup context also fixes the authoritative batch order for the turn.
If the model returns only part of that batch, the gateway fills the missing
candidate IDs from the ordered recommendation and validates the complete batch
before any mutation. This prevents response-formatting omissions from stopping
a resumed setup pass without allowing guessed or stale placements.

For `TS_Save_131.json`, the profile declares one TTS world unit per inch and
validates the unique `combat_zone` LayoutZone at approximately 30 by 22 world
units. It does not require a physical calibration marker.

Terrain geometry comes from live position, rotation, scale, and bounds by
default. Explicit metadata may override irregular footprints and rules
semantics such as blocking, cover, height, or terrain type. Range and movement
use the canonical map model; live LOS uses the on-demand sampled physics probe
so the result reflects actual TTS colliders. Camera evidence may clarify an
ambiguous case; structured geometry, collider evidence, and camera evidence
conflicts pause for host adjudication and are recorded with their map revision.

The probe reports `collider_warning=physics_colliders_only`. Physics casts
measure TTS physics colliders, which may differ from a rendered custom mesh.
Missing or unsuitable custom colliders are therefore an uncertainty source;
the runtime fails closed on a blocked or malformed probe and preserves the
evidence for adjudication. Cover thresholds and other Kill Team policy remain
Python rules decisions rather than Lua raycast decisions.

## Setup-validation pipeline

`tts_killteam_setup` remains read-only. The separate setup-validation pipeline
is a resumable opt-in live test and requires the host to freshly load
`TS_Save_131.json` before every run:

1. Normalize and validate the live fixture through its setup profile.
2. Discover the only live Blue/Plague Marine operative outside the combat
   zone. The test-only identity oracle requires GUID `96fe20`; the GUID is not
   supplied to the AI as its choice.
3. Discover the only currently visible enemy operative in `combat_zone`. The
   identity oracle requires GUID `377732`.
4. Resolve exactly one global snap point tagged `_start_test_spot`. The current
   fixture position is `x=-24.1579723`, `y=1.481601`,
   `z=-9.286173`; live snap-point data is authoritative.
5. Place `96fe20` at the full snap-point position and verify the live readback
   within the normal placement tolerance.
6. Cast the nine-ray silhouette LOS probe to `377732`. At least one ray must
   reach the target. Zero target rays, malformed bounds, or unavailable
   collider evidence stops the pipeline before dice.
7. Fire `96fe20`'s Boltgun with four resolved Blue attack dice using TTS's
   native die Roll operation, not mechanical insertion into the roller. Hit
   on 3+, damage 3/4. Physical randomness is valid; the test does not require
   damage.
8. Pause and ask Red to roll `377732`'s three defense dice at 4+ through
   read-only roll station `f1adc9`. Resume only after an explicit Red/host
   acknowledgment that the defense roll is complete, then read the settled
   physical results.
9. Resolve the attack, apply any resulting wounds through a semantic wound
   action, and verify the target's real wound state. Renaming the model is not
   a wound update.
10. Persist structured evidence for identity resolution, snap position,
    placement readback, LOS samples, dice, damage, and wound readback. Player
    chat receives only a concise completed, pending, or failed result.

The pipeline never manipulates Red dice, silently selects another placement,
automatically retries a possibly committed move/roll/damage action, or resets
the scene. A lost callback enters read-only recovery. The run leaves physical
results intact; the host reloads the fixture before another run.

## Semantic gameplay

The AI uses game actions, never raw TTS mutations. The first vertical slice is
one complete ranged activation:

- observe the current state and visibility;
- validate turning point, phase, initiative, active operative, and APL;
- move an operative using an explicit path/waypoints;
- check distance, terrain, LOS, and target visibility;
- resolve the tagged AI dice and invoke native physical rolls;
- pause for the human defender's physical roll, then resolve hits, saves,
  damage, wounds, and statuses;
- update CP/VP through semantic resource/scoring events;
- mirror the result to TTS and verify every relevant projection.

The first executable slice covers setup ingestion, role-filtered observation,
waypoint placement, activation/AP, 2D range, on-demand sampled-physics LOS,
physical AI attack dice, the human defense-roll handoff, damage, and verified
wound-state projection. Resource scoring, camera-assisted ambiguity handling,
broader human-event reconciliation, and turn/scenario rules remain subsequent
slices. The public MCP entry points are
`tts_killteam_setup`, `tts_killteam_observe`,
`tts_killteam_setup_ping`, `tts_killteam_setup_list_objects`,
`tts_killteam_setup_place_model`, `tts_killteam_get_roster`,
`tts_killteam_plan_objective_move`,
`tts_killteam_select_roster_card`,
`tts_killteam_select_setup_card`,
`tts_killteam_lock_rosters`, `tts_killteam_start_setup_deployment`,
`tts_killteam_deploy_setup_operative`,
`tts_killteam_rollback_pending_deployment`,
`tts_killteam_reconcile_setup_step`,
`tts_killteam_probe_line_of_sight`, `tts_killteam_place_operative`,
`tts_killteam_deploy_test_model`,
`tts_killteam_activate_operative`, `tts_killteam_shoot`,
`tts_killteam_begin_setup_validation`, and
`tts_killteam_complete_setup_validation`. The in-game gateway starts the
isolated deployment smoke test with `KILLTEAM_DEPLOY_TEST` and
starts the fixture pipeline with `KILLTEAM_VALIDATE_SETUP[action_id]`. The
fixture pipeline resumes only
when authenticated Red or host chat says `Defense roll complete`.
During live play the chat gateway also recognizes `Your turn` and related
initiative-pass prompts while Kill Team is active, routes them to the tactical
turn request, claims the initiative token for the AI side, executes one
bounded tactical action, ends activation, and then passes initiative to the
next player before waiting for the next prompt.
The placement-only setup bridge also accepts `KILLTEAM_SETUP_PLACE[guid,x,y,z]`
for exact model placement without loading the broader setup state machine.
The chat gateway also accepts `KILLTEAM_AUTORUN_SETUP` for the AI-owned setup
pass when the full runtime Lua bridge is loaded. With the placement-only
bridge, use `MOVE[guid,x,y,z]` after resolving the live object through
`tts_killteam_setup_list_objects`. The bridge-level `KILLTEAM_SETUP_PLACE`
form remains available for manual or lower-level debugging paths. The
placement bridge also projects the final `y` onto terrain support when a
terrain piece intersects the chosen footprint, rather than trusting the raw
requested `y`.

### Setup deployment state machine

Semantic pregame setup follows this bounded sequence:

1. `tts_killteam_setup(...)` discovers the tagged setup objects and starts
   model deployment directly from the side-tagged roster containers. The
   generic path queries the standard setup tags directly and does not depend on
   a placeholder target GUID. The Save 131 validation fixture is opt-in; it is
   not the default setup path.
2. The runtime assumes the AI side has initiative by default, so roster
   selection can begin immediately. Use `tts_killteam_roll_initiative` only
   when the host explicitly overrides that default and wants a physical
   initiative roll instead.
3. `KILLTEAM_AUTORUN_SETUP` starts an AI-owned setup pass. The game begins with
   initiative, then the AI selects its operatives, then selects any available
   setup cards such as equipment, ploys, or tactical-op cards, and only then
   starts deployment. The AI observes the live placement objects and setup
   candidates, selects the required number of distinct AI models by role
   priority and board context, chooses distinct tactical legal positions from
   the returned `recommended_batch`, and emits one `SETUP_MOVE[candidate_id]`
   per recommended model. Candidate IDs outside that batch are not legal for
   the current turn. The
   gateway translates those moves into sequential verified placement actions,
   which validate each selected GUID and coordinate. The controller persists
   every successful GUID so a later `KILLTEAM_AUTORUN_SETUP` call resumes from
   the last finished placement instead of repeating the same model. Use `!ai start
   fresh` to clear that setup history. The human never selects or moves an AI
   model. If the observation budget runs out before the model emits a
   placement, the gateway switches to a setup-command-only completion prompt instead of
   asking for more tools it can no longer request.
   Clear natural-language requests such as "place your next model" use the
   same resume path. Existing setup history is normalized by GUID so repeated
   or legacy records do not reset the AI's remaining batch. If the bridge's
   ranked recommendations contain already-placed models, the gateway refills
   the legal batch from the remaining bridge candidates while preserving
   distinct footprints. The persisted placed GUIDs are also supplied to the
   context collector before ranking, so normal second-round planning excludes
   completed models at the source.
4. Deployment then follows the configured cadence: starting with the AI-first
   `initiative_side` unless the host overrode it, each side alternates setup
   passes and places `ceil(N/3)` operatives per pass, with a minimum pass of
   one operative and a smaller final remainder when fewer remain.
5. The human side places only its own current batch directly into its deployment
   zone. After the human reports that batch placed, the AI sends another
   `KILLTEAM_AUTORUN_SETUP` request; the gateway calls
   `tts_killteam_reconcile_setup_step` to detect and validate the human models,
   consumes the batch, and then performs one new AI placement turn.
   Reconciliation is never used to place AI models. For a brand-new game, use
   `!ai start fresh killteam` to clear controller history, select Kill Team if
   needed, and immediately enter this autorun setup path.
6. The AI setup planner derives its play style from faction tags. Teams with
   aggressive melee or pressure tags prefer objective pressure and forward
   lanes; ranged or precision-oriented factions prefer cover and standoff
   positions.
7. Every AI placement is verified against live position and geometry, and each
   deployed operative receives a starting `Conceal` order. The lower-level
   roster-card selection and lock actions remain available for tables that
   explicitly use physical roster-card lists.

The setup contract is therefore still intentionally staged: the runtime
already supports the first playable slice, but the docs and backlog still need
to settle geometry, ranking policy, turn-order nuances, recovery semantics,
and the regression matrix before the setup path is considered complete. The
live AI setup plan also exposes ranked deployment evidence in
`recommended_position_evidence`, including the candidate order, support
height, and score metadata for the next legal slot. The dedicated setup
listing also returns live object bounds so the runtime can compute that
support height from the footprint actually occupied on the table. If Kill Team
is already the active game, `!ai start fresh` performs the same reset and
resumes autorun setup.

The runtime exposes semantic actions such as `move_operative`, `shoot`,
`roll_attack_dice`, `score_objective`, `gain_cp`, and `spend_cp`. GUIDs are
adapter internals. The rules engine is typed and executable; `rules.md` is a
host-managed context/reference and never the sole legality authority.

The deterministic deployment smoke test is an explicit Save 131 operation.
It resolves the unique model whose name contains `Plague Marine Warrior` and
the destination tagged `_deployment_zone_blue`, derives their current GUIDs
only for the TTS bridge calls, copies the zone's x/z coordinates while preserving
the model's current y coordinate, and verifies the final model x/z position is
within `0.25` TTS world units of the zone position. It does not inspect full
Kill Team setup, rosters, snap points, dice, or game rules. This is the test
seam for the tactical one-by-one deployment planner.

The AI plans within a bounded horizon, announces its intended plan publicly,
re-observes after each action, and replans when state changes. Its objective
is the scenario victory condition and scoring, followed by preserving models
and resources; kills are valuable only when they support those goals. Hidden
enemy information is represented as visible, last-known, or unknown rather
than invented exact positions.

## Human events and recovery

Human moves, rolls, counter changes, and damage applications are external
events. The runtime reconciles them against the current rules state and
records them. Unexplained or contradictory changes pause play.

A host may issue an explicit, logged rules adjudication containing the disputed
action, engine result, ruling, approver, and resulting state. This is the only
normal path for overriding a deterministic rules result.

All actions and observations carry state/map revisions and audit evidence.
The deterministic fake bridge must exercise visibility, dice, counters,
terrain, manual changes, disconnects, stale observations, and uncertain
commits before live-TTS validation is accepted.
