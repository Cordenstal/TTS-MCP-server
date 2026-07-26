# Kill Team opponent

This page records the agreed design for the first serious game-specific
opponent: the AI plays one side of the `Kill Team 3.0 Quick and Easy` variant
represented by the canonical `TS_Save_129.json` fixture.

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

1. Load and parse the save once as a static fixture/setup source.
2. Discover tagged objects in the live TTS table.
3. Bind team ownership to TTS player identity/color.
4. Validate the AI roster, dice, roller, CP, VP counters, terrain,
   deployment areas, objectives, and calibration markers.
5. Build the role-filtered initial state and report every ambiguity.
6. Freeze the initial map model and enable semantic gameplay only after setup
   succeeds.

Required metadata uses a versioned `tts_mcp:` namespace. Every operative has
a stable `operative_id`, `profile_id`, and team ownership. Dice, counters,
terrain, objectives, deployment areas, and status markers have explicit roles
and owners. Setup fails closed on missing, duplicate, or contradictory
metadata.

The current fixture references AI dice `2831c0`, `bde8ee`, `87bb98`, `967871`,
`ffeef7`, and `d08c28`; roller `175503`; CP counter `2cc38b`; and VP counters
`7ff953`, `53befd`, and `d9b193`. These are fixture/configuration references,
not permanent gameplay identities. Tags are authoritative for discovery.

The model descriptions may be parsed once for static profile data. Dynamic
wounds, AP, statuses, activations, resources, and scoring remain runtime state
and may be mirrored to TTS names, counters, and markers.

## Observation and map model

Before each activation and before each attack, the AI must obtain a fresh
observation. It may use structured object queries and approved camera views in
the public combat zone or its own side. Screenshots provide context and
evidence; they do not bypass visibility rules or replace exact structured
identity and coordinates.

The combat zone is discovered for each game. Its model includes tagged terrain,
deployment areas, objectives, objects, and coordinates. Terrain is mutable:
doors, barricades, objectives, or other map objects may change during play.
Each change creates a new map revision and invalidates affected LOS results.

TTS coordinates use `x` and `z` for the horizontal board plane and `y` for
height above that plane. Setup calibration defines the board origin, axis
orientation, ground height, and world-units-per-inch scale. Rules calculations
use Kill Team inches; TTS coordinates are used for placement and physical
queries.

Terrain geometry comes from live position, rotation, scale, and bounds by
default. Explicit metadata may override irregular footprints and rules
semantics such as blocking, cover, height, or terrain type. Line of sight is
computed from the tagged geometry first. Camera evidence may clarify an
ambiguous case; geometry/evidence conflicts pause for host adjudication and
are recorded with their map revision and camera evidence.

## Semantic gameplay

The AI uses game actions, never raw TTS mutations. The first vertical slice is
one complete ranged activation:

- observe the current state and visibility;
- validate turning point, phase, initiative, active operative, and APL;
- move an operative using an explicit path/waypoints;
- check distance, terrain, LOS, and target visibility;
- roll attack dice through the tagged AI dice pool and roller;
- resolve hits, saves, damage, wounds, and statuses;
- update CP/VP through semantic resource/scoring events;
- mirror the result to TTS and verify every relevant projection.

The runtime exposes semantic actions such as `move_operative`, `shoot`,
`roll_attack_dice`, `score_objective`, `gain_cp`, and `spend_cp`. GUIDs are
adapter internals. The rules engine is typed and executable; `rules.md` is a
host-managed context/reference and never the sole legality authority.

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
