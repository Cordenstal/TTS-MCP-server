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

## Observation and map model

Before each activation and before each attack, the AI must obtain a fresh
observation. It may use structured object queries and approved camera views in
the public combat zone or its own side. Screenshots provide context and
evidence; they do not bypass visibility rules or replace exact structured
identity and coordinates.

The MCP client and in-game AI gateway share the same setup/observation seam.
`tts_killteam_setup` creates a fresh scene epoch by discovering the tagged live
table through bounded bridge actions. The fixture profile supplies native query
tags and exact anchors; the Lua bridge does not hard-code this fixture and does
not walk unrelated mod objects through generic `list_objects`.
`tts_killteam_observe` then returns the current revision, observation ID,
visible operative records, terrain, AI dice references, counters, roller GUID,
and an explicit truncation flag. Setup is a start-of-game operation and must
not be repeated during an activation. The gateway exposes these two bounded
tools to the AI backend. The gateway also accepts the bounded semantic
`KILLTEAM_PLACE[operative_id,x,y,z]` command for initial AI placement; the
runtime resolves the operative ID to a live GUID. Activation and attacks
remain on the semantic MCP interface.

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
7. Fire `96fe20`'s Boltgun: four Blue attack dice, hit on 3+, damage 3/4.
   Physical randomness is valid; the test does not require damage.
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
- roll attack dice through the tagged AI dice pool and roller;
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
`tts_killteam_probe_line_of_sight`, `tts_killteam_place_operative`,
`tts_killteam_deploy_test_model`,
`tts_killteam_activate_operative`, `tts_killteam_shoot`,
`tts_killteam_begin_setup_validation`, and
`tts_killteam_complete_setup_validation`. The in-game gateway starts the
isolated deployment smoke test with `KILLTEAM_DEPLOY_TEST` and
starts the fixture pipeline with `KILLTEAM_VALIDATE_SETUP[action_id]`. The
fixture pipeline resumes only
when authenticated Red or host chat says `Defense roll complete`.

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
Kill Team setup, rosters, snap points, dice, or game rules. This is a test seam for later tactical
model selection and deployment; it is not yet a tactical deployment
planner.

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
