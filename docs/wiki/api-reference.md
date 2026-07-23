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

`tts_get_scene_summary` is the preferred broad inspection call. It includes
object identity, transforms, bounds, movement state, velocity, axes, zone
membership, and bounded container summaries.

`tts_calibrate_view` validates a screen rectangle and reports monitor geometry.
`tts_capture_view_info` returns capture timestamp, dimensions, contrast, and a
blank-frame heuristic. Use these before relying on a screenshot from a new
display layout.

`tts_focus_object_and_capture` derives a camera target and distance from the
object's bounds. `tts_wait_for_object_settle` should be used after smooth moves
or spawns before treating the returned position as final.

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
