# ADR-0007: Guarded numbered-save editing with explicit GUI loading

## Status

Accepted

## Context

The server needs to edit a local numbered TTS save and make the edited state
take effect in the running game. TTS stores saves as JSON, but its documented
External Editor protocol can update scripts/UI and reload the current save; it
does not expose a command to load an arbitrary save file from disk. Loading a
local save is a TTS Save & Load menu operation.

Directly editing a save is broad and can replace the live scene when loaded.
An unverified overwrite could also destroy the user's last recoverable copy.

## Decision

Add three bounded operations:

1. Inspect only a numbered `TS_Save_<number>.json` directly under the local
   TTS `Saves` directory.
2. Apply at most 200 JSON Pointer `add`, `replace`, or `remove` operations,
   requiring `allow_irreversible=true` for a real write. Create a timestamped
   sibling backup and atomically replace the original file.
3. Load the edited file through explicit Windows GUI automation. The caller
   supplies coordinates relative to the detected TTS window for the Games
   button, Save & Load button, search box, and result row. The operation
   requires explicit approval and reports, but does not overclaim, a
   post-load script-state callback.

Replacing the entire JSON root is forbidden. The loader never accepts an
arbitrary executable command, targets only a visible window whose title
contains `Tabletop Simulator`, and does not run while coordinates are missing
or outside the detected window.

## Consequences

The file workflow is recoverable through the generated backup and produces
before/after hashes. GUI loading works without an undocumented TTS protocol,
but coordinates must be calibrated for the current Unity layout and window
size. The External Editor callback cannot prove the save filename, so the
result is described as a load request plus observed callback rather than an
absolute identity claim.

