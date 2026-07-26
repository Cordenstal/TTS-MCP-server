# TTS MCP Wiki

This is the living notebook for the Tabletop Simulator MCP. It records what
the system is, why it is shaped this way, what is already implemented, and
what should be built next. Keep it practical: update the wiki when behavior,
tool contracts, safety boundaries, or roadmap priorities change.

## Start here

- [Roadmap](roadmap.md) — prioritized ongoing goals and implementation order.
- [Architecture](architecture.md) — process boundaries and data flow.
- [API and rules](api-and-rules.md) — tool-contract and domain-knowledge plan.
- [Kill Team opponent](killteam.md) — agreed hidden-information opponent
  architecture and first vertical slice.
- [Observation and spatial reasoning](observation-and-visuals.md) — structured
  state, screenshots, and exact object location.
- [Development workflow](development.md) — how to change, test, and verify the
  bridge safely.

## Project north star

The AI should be able to inspect a live table, identify the intended object
with evidence, make a bounded change, and verify the result through structured
state plus visual context. Vision is helpful for understanding layout; the
TTS API is authoritative for exact identity and coordinates.

## Current state

Implemented foundations include:

- Python MCP server over stdio.
- TTS External Editor request/callback bridge.
- Lua Global-script dispatcher with an allowlisted action set.
- GUID-first object listing and inspection.
- Camera control and configurable OS screenshot capture.
- Game-rule files and persistent AI session/audit storage.
- Bounded action plans with per-step results.
- Explicit protection around destructive actions and arbitrary Lua.

The wiki roadmap is intentionally ahead of the implementation. A roadmap
item is not complete until its tool contract, bridge behavior, tests, and
documentation are all updated.
