# ADR-0009: Kill Team semantic opponent with hidden-information state

## Status

Accepted

## Context

The project needs to play Kill Team rather than only manipulate arbitrary TTS
objects. Kill Team combines tactical planning, hidden deployment, physical
terrain, line of sight, dice, counters, mutable status, and human actions.
The AI will play one side as an opponent. The first target is the `Kill Team
3.0 Quick and Easy` variant represented by the `TS_Save_131.json` fixture.

Raw TTS mutations and screenshots cannot establish game legality. A raw object
list can also expose concealed opponent state unless it is filtered by the
AI's player perspective.

## Decision

Build Kill Team as a role-specific adapter over the generic TTS control plane.

- The Python runtime owns a versioned canonical state and append-only event
  log. TTS is the physical projection and observation source.
- The AI receives only its own private state, public combat-zone state, and
  currently observable enemy state. Hidden enemy state is never exposed.
- Game startup is an explicit, fail-closed setup phase driven by a versioned
  fixture setup profile. The profile normalizes native save tags and stable
  anchors into roster, dice, roller, counter, terrain, deployment, objective,
  ownership, and calibration roles without modifying the save. See ADR-0010.
- The save may be inspected offline to select and validate its fixture profile,
  but actionable setup and runtime state comes from live structured queries,
  approved camera views, Lua deltas, and periodic snapshots.
- The rules engine owns legality, phases, activations, movement, LOS, dice
  resolution, damage, statuses, resources, and scoring. Markdown rules are
  context only. Missing rules and geometry/evidence conflicts pause for a
  host ruling.
- The AI emits semantic actions. Adapters translate them into bounded TTS
  operations. Semantic actions have unique IDs, are atomic and idempotent, and
  never retry after an uncertain commit.
- Fresh observation is required before each activation and attack. The AI
  announces a bounded plan, executes legal non-destructive actions
  autonomously, re-observes after each action, and replans on state change.
- The active Kill Team turn loop is bounded. When the player says `Your turn`
  or an equivalent initiative-pass prompt, the gateway hands the request to a
  tactical-turn action that claims the initiative token, performs one legal AI
  action, ends the activation, and passes initiative back to the next player
  before waiting for the next prompt.
- TTS uses `x/z` as the horizontal plane and `y` as height. Setup calibration
  records origin, orientation, ground height, and world-units-per-inch scale.
  Terrain uses bounds by default with explicit metadata overrides. Map changes
  create revisions and invalidate affected LOS results.
- Physical dice are authoritative in live play. The AI may move only its Blue
  dice into roller `175503`. A defending Red player rolls their own dice
  through read-only roll station `f1adc9`; resolution pauses until an explicit
  Red/host completion acknowledgment, then reads the settled physical results.
  Runtime resources and statuses are authoritative; TTS counters and markers
  mirror them.
- Human TTS changes are reconciled as external events. Host adjudications are
  explicit, logged, and scoped to the current state.

The first vertical slice is one complete ranged activation using the canonical
fixture: setup, observation, movement, LOS/range, attack dice, saves, damage,
wounds, resource/scoring updates, TTS projection, and verification. Melee,
ploys, equipment abilities, and advanced scoring follow after this loop is
reliable.

## Consequences

The AI can inspect the table like a player while retaining an anti-cheating
boundary. Tactical decisions can be re-planned from current observations, and
every important result is explainable through state revisions, dice results,
map revisions, and audit evidence.

The adapter requires a typed state schema, visibility projection, semantic
action API, map/LOS model, event reconciliation, and deterministic fake bridge
before live play can be considered reliable. TTS GUIDs remain implementation
details discovered through profile-mapped tags or exact anchors and validated
against the live scene at setup.

## Alternatives rejected

- Raw `MOVE`/counter commands as the gameplay API: they do not express or
  validate Kill Team intent.
- TTS-only game state: it cannot safely represent hidden information, history,
  rules state, or uncertain commits.
- Screenshot-only LOS and object recognition: it is not precise or auditable
  enough for legality-critical decisions.
- Full-save injection on every turn: it is large, stale-prone, and risks
  exposing irrelevant or concealed state.
- Automatic retries after lost callbacks: dice and damage could be applied
  twice.
