# MCP capability reference

Use `tts_describe_capabilities` at the start of an unfamiliar task. It returns
the current machine-readable safety and verification contract. This page is
the human-readable companion; update it when the manifest changes.

## Spatial tools

- `tts_find_nearest_objects` accepts a world point or reference GUID and
  returns bounded object summaries with distances.
- `tts_find_objects_in_region` accepts minimum and maximum world coordinates
  and returns objects whose world-space bounds intersect the region.
- `tts_measure_distance` measures between two GUIDs, two points, or a GUID and
  a point.
- `tts_get_relative_transform` returns position delta, rotation delta, and
  distance from one object to another.

Spatial results are in TTS world units. They are more authoritative than visual
estimates. Use GUIDs for mutation after a spatial query resolves candidates.

## Semantic lookup

Use `tts_search_scene` for ranked candidates and `tts_resolve_object_reference`
for a decision-ready result. A mutation should proceed only when
`resolved=true`; if `ambiguous=true`, ask for clarification or register an
explicit alias with `tts_register_scene_alias`.

Aliases are persisted in the session database. Use `game_name` to scope an
alias to a particular game and `role` to record a semantic role such as
`supply-deck` or `player-marker`. Use `tts_list_scene_aliases` to inspect the
current index and `tts_remove_scene_alias` to delete an alias.

## Observation tools

`tts_list_objects` returns bounded visible object summaries with exact GUIDs,
names, tags, transforms, bounds, and lock state. `tts_get_scene_summary` is a
compact broad inspection call. It includes
object identity, transforms, bounds, movement state, velocity, axes, zone
membership, and bounded container summaries.

The listing response's `total_matching` count includes every valid top-level
object matching the filters, while `count` is the number returned after the
`max_results` bound. TTS references with a missing, empty, or `-1` GUID are
skipped and reported in `skipped_invalid`; they are never exposed as usable
object identities.

`tts_calibrate_view` validates a screen rectangle and reports monitor geometry.
`tts_capture_view_info` returns capture timestamp, dimensions, contrast, and a
blank-frame heuristic. Use these before relying on a screenshot from a new
display layout.

`tts_focus_object_and_capture` derives a camera target and distance from the
object's bounds. `tts_wait_for_object_settle` should be used after smooth moves
or spawns before treating the returned position as final.

`tts_killteam_plan_objective_move` plans a tactical objective-control move for
one AI operative and returns a suggested `MOVE[guid,x,y,z]` target plus the
candidate ranking evidence. Use it before emitting `MOVE[...]` when the goal
is to contest or stage around an objective.

## Mutation workflow

1. Call `tts_describe_capabilities` if the operation or safety class is unclear.
2. Inspect the scene and resolve the target GUID.
3. Use a specific mutation tool or a bounded action plan.
4. Read the returned post-state.
5. Capture a view when visual confirmation is useful.

For coordinated mutations, use action-plan fields such as:

```json
{
  "action": "move_object",
  "args": {"guid": "ABC123", "position": {"x": 1, "y": 2, "z": 3}},
  "preconditions": {"guid": "ABC123", "locked": false},
  "postconditions": {
    "guid": "ABC123",
    "position": {"x": 1, "y": 2, "z": 3},
    "max_position_error": 0.05
  }
}
```

Use `dry_run=true` to validate a plan without changing TTS. Use
`verify_after_each=true` when intermediate state matters. Supply a unique
`idempotency_key` when the client may retry a request; the server replays the
cached result instead of executing the plan twice.

`tts_move_checkers_piece` is the game-specific movement path for the bundled
checkers save. It resolves the live `Checker_black` pieces, infers the square
lattice from their positions, rejects lateral/backward ordinary-man moves and
occupied destinations, preserves the source Y coordinate, and waits for the
piece to settle. Pass `target_zone_tag` (for example `C5`) to use the
authoritative invisible LayoutZone destination; the tool resolves the zone's
world-space X/Z center internally. For ordinary object movement initiated by
the AI, emit `MOVE[guid,x,y,z]` at the command layer and let the bridge resolve
it to the underlying TTS move call. Keep using `tts_move_object` for
unrestricted generic moves.

`tts_place_in_tagged_zone` is the board-game placement primitive for invisible
tagged square zones. For chess, pass the moving piece GUID as `target_guid` and
the destination such as `E4` as `zone_tag`; it resolves the unique `LayoutZone`
and moves the piece to that zone's X/Z center while preserving the piece's
current Y height. It waits for the move to settle and returns the final error,
without requiring world coordinates.

## Game-domain tools

Use `tts_inspect_container` before taking or inserting an item. Container
contents are bounded to protect MCP response size. Use `tts_get_zone_objects`
for current occupancy and `tts_get_snap_points` before implementing placement
logic. Container take operations are deferred and return the actual spawned
object summary.

Use `tts_validate_scene_requirements` for tag/name/type count invariants and
`tts_validate_zone_occupancy` for zone-level checks. Placement helpers use
world-space bounds and reference-object axes; verify their returned state and,
for zones, call the occupancy validator afterward.

Do not use screenshots to infer exact GUIDs, final coordinates, lock state, or
whether a smooth move has completed.

## Numbered save files

`tts_inspect_save_file` reads a numbered save directly under the local TTS
`Saves` directory and returns its size, SHA-256, top-level keys, and object
count. The default is `TS_Save_128.json`.

`tts_edit_save_file` applies bounded JSON Pointer operations. Use
`dry_run=true` first. A write requires `allow_irreversible=true`; the server
creates a timestamped backup and atomically replaces the original file.
Replacing the entire JSON document is forbidden, and operations are limited
in count and value size.

`tts_load_save_file` uses explicit Windows GUI coordinates relative to the
detected Tabletop Simulator window. Supply coordinates for the Games button,
Save & Load button, search box, and matching result row. The tool focuses TTS,
searches by the save stem, selects the result, and confirms with Enter unless a
confirmation coordinate is supplied. Keep the TTS window focused and avoid
other mouse/keyboard input during the bounded workflow. The result reports a
post-load script-state callback when observed, but TTS does not report the
loaded save filename through External Editor.
