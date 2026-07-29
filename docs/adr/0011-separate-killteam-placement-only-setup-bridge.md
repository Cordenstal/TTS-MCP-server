# ADR-0011: Separate a placement-only Kill Team setup bridge from the full runtime

## Status

Accepted

## Context

The existing Kill Team runtime and Global Lua bridge bundle setup discovery,
roster selection, deployment cadence, combat, validation, and wound
projection into one large control path. That makes the setup placement slice
hard to isolate when the rest of the runtime is still unstable.

The project also needs a narrow setup path that can move a single live model to
an exact setup coordinate without depending on the full Kill Team state
machine. That path should stay easy to test and should fail independently of
the larger runtime.

## Decision

Add a dedicated placement-only Kill Team setup runtime and a separate Global
Lua bridge with a small allowlisted surface:

- `setup_ping` for bridge availability and versioning.
- `setup_list_objects` for bounded discovery during placement.
- `setup_place_model` for exact movement plus readback verification.

The placement-only path uses distinct MCP tool names and a distinct command
family (`KILLTEAM_SETUP_PLACE[...]`) so it remains separate from the larger
Kill Team runtime and its legacy setup-deployment flow.

The full runtime remains available for roster setup, deployment cadence,
combat, line of sight, and validation. The placement-only bridge is a narrow
tool, not a replacement for the full adapter.

## Consequences

The setup placement slice can be exercised without loading the rest of the
Kill Team runtime logic. This reduces the blast radius of failures, makes the
bridge source smaller and easier to inspect, and gives the AI a dedicated
placement-only path when the legacy runtime is unavailable.

The tradeoff is deliberate duplication: a second bridge file, a second runtime
module, and a second set of tests and docs must stay synchronized. The docs and
prompting must also keep the two Kill Team paths clearly distinguished so the
placement-only flow does not silently drift back into the larger runtime.
