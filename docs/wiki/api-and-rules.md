# API and rules

## Tool contract requirements

Every MCP tool should document:

- Whether it reads or mutates.
- Required and optional arguments.
- Units and coordinate conventions.
- Identity rules, especially GUID requirements.
- Whether the operation is reversible.
- Whether approval is required.
- Whether it is synchronous or deferred.
- The exact return shape.
- How the result should be verified.

## Identity rules

Names, descriptions, tags, and screenshots are discovery signals. GUIDs are
the mutation identity. If a natural-language reference resolves to multiple
objects, return candidates and ask for disambiguation rather than guessing.

## Coordinate rules

- Positions are TTS world coordinates in `{x, y, z}` order.
- For Kill Team, `x` and `z` form the horizontal combat-zone plane; `y` is
  height above the board plane. Rules distance uses calibrated game inches,
  not raw world units.
- Rotations are Euler angles in degrees unless a tool explicitly says otherwise.
- Object centers are not object extents; use bounds for placement decisions.
- Smooth movement can mean the immediate response is a target state, not yet a
  settled physical state.

## Semantic game actions

Game-specific adapters should expose intent-level actions such as
`move_operative`, `shoot`, `roll_attack_dice`, `score_objective`, `gain_cp`,
and `spend_cp`. These actions validate rules and state before translating into
bounded TTS mutations. Raw GUID-based movement and counter writes remain
bridge primitives, not the gameplay API.

## Safety classes

| Class | Examples | Handling |
| --- | --- | --- |
| Read-only | list, inspect, search, screenshot | Execute directly |
| Reversible mutation | move, rotate, rename, lock | Return prior and post-state when possible |
| Approval mutation | spawn, broadcast, broad plans | Require explicit intent when impact is broad |
| Destructive | destroy, reset, broad scene change | Require explicit confirmation and opt-in |
| Forbidden | arbitrary Lua, hidden information access | Do not expose |

## Documentation sources

The generic API reference should be based on the official TTS API and checked
against the installed game version. Useful reference areas include Object,
Base, Physics, Player, Zone, Container, and UI APIs. The official reference
documents object bounds and transforms and provides tag and physics-cast APIs:

- [TTS API introduction](https://api.tabletopsimulator.com/intro/)
- [Object API](https://api.tabletopsimulator.com/object/)
- [Base API](https://api.tabletopsimulator.com/base/)
- [Physics API](https://api.tabletopsimulator.com/physics/)

Do not copy large external documentation dumps into the repository without a
clear versioning and update strategy. Prefer a compact MCP-focused reference
with links and examples.
