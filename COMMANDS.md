# Command Index

This file is the root-level index for the repo's named command surfaces. Keep
it aligned with `README.md`, the wiki pages, and the server tool definitions.

## Chat Commands

- `!ai begin killteam` - start a fresh Kill Team session from the top, select
  Kill Team if needed, clear prior Kill Team state, and launch the full setup
  autostart path.
- `!ai start fresh killteam` - compatibility alias for `!ai begin killteam`.
- `!ai start fresh` - reset the currently selected game's controller/session
  state and start that game fresh.
- `!ai start` - resume the current selected game without clearing session
  history.
- `!ai game <name>` - select a game ruleset without starting play.
- `!ai pause` - pause autonomous AI play.
- `!ai resume` - resume autonomous AI play.
- `!ai stop` - stop autonomous AI play.
- `!ai status` - report the current AI controller state.
- `!ai approve ACTION_ID` - approve a pending host-reviewed action.
- `!ai reject ACTION_ID` - reject a pending host-reviewed action.

## Kill Team Semantic Commands

- `KILLTEAM_ROLL_INITIATIVE` - perform the explicit physical initiative roll
  override before roster locking.
- `KILLTEAM_AUTORUN_SETUP` - run one bounded AI-owned setup pass.
- `KILLTEAM_SELECT_ROSTER[contained_guid]` - select a roster card from a
  bounded container.
- `KILLTEAM_SELECT_SETUP[card_guid]` - select a non-operative setup card.
- `KILLTEAM_LOCK_ROSTERS` - lock both rosters and begin official setup cadence.
- `KILLTEAM_START_DEPLOYMENT[operative_id]` - begin one AI model deployment
  within the current setup pass.
- `KILLTEAM_DEPLOY_SETUP[guid,x,y,z]` - deploy the pending setup operative by
  live figurine GUID and exact coordinates.
- `KILLTEAM_ROLLBACK_PENDING` - roll back the currently pending setup
  operative.
- `KILLTEAM_RECONCILE_SETUP[side_id]` - reconcile the current setup pass with
  the live table state.
- `KILLTEAM_PLACE[guid,x,y,z]` - semantic placement for the live figurine.
- `KILLTEAM_SETUP_PLACE[guid,x,y,z]` - placement-only setup bridge move.
- `KILLTEAM_DEPLOY_TEST` - one-off deployment smoke test for the tagged model
  and zone pair.
- `KILLTEAM_VALIDATE_SETUP[action_id]` - start the Save 131 validation slice.

## Kill Team MCP Tools

- `tts_killteam_setup` - build the full Kill Team setup snapshot.
- `tts_killteam_setup_ping` - verify the dedicated placement-only setup bridge
  is loaded and matches disk.
- `tts_killteam_setup_list_objects` - list bounded objects through the
  placement-only setup bridge.
- `tts_killteam_setup_context` - return the compact AI planning context for
  Kill Team setup.
- `tts_killteam_setup_place_model` - place one model through the placement-only
  setup bridge.
- `tts_killteam_observe` - return the full Kill Team observation snapshot.
- `tts_killteam_get_roster` - inspect the dedicated AI roster container.
- `tts_killteam_plan_setup_board` - plan legal setup positions from board
  geometry.
- `tts_killteam_plan_objective_move` - suggest an objective-control move for
  one AI operative.
- `tts_killteam_execute_setup_board` - execute a bounded setup-board plan.
- `tts_killteam_select_roster_card` - choose a roster card during setup.
- `tts_killteam_select_setup_card` - choose a non-operative setup card.
- `tts_killteam_lock_rosters` - lock both rosters before deployment begins.
- `tts_killteam_roll_initiative` - perform the explicit initiative override.
- `tts_killteam_start_setup_deployment` - open one AI deployment action.
- `tts_killteam_deploy_setup_operative` - commit the pending AI deployment.
- `tts_killteam_rollback_pending_deployment` - clear or undo the current
  pending deployment.
- `tts_killteam_reconcile_setup_step` - reconcile a setup step from the live
  table state.
- `tts_killteam_probe_line_of_sight` - inspect LOS between two operatives.
- `tts_killteam_place_operative` - place or move one AI operative.
- `tts_killteam_deploy_test_model` - run the deterministic smoke test piece
  placement.
- `tts_killteam_search_deployment_names` - search the known deployment-name
  set.
- `tts_killteam_activate_operative` - activate one AI operative.
- `tts_killteam_shoot` - resolve a ranged attack using physical dice.
- `tts_killteam_begin_setup_validation` - start the Save 131 validation slice.
- `tts_killteam_complete_setup_validation` - complete the Save 131 validation
  slice after the Red/host acknowledgment.

## Generic Read Tools

- `tts_ping` - verify the TTS bridge is reachable.
- `tts_list_objects` - list visible objects with bounded summaries.
- `tts_describe_capabilities` - return the current machine-readable safety
  contract.
- `tts_find_nearest_objects` - find objects near a point or GUID.
- `tts_find_objects_in_region` - list objects intersecting a region.
- `tts_measure_distance` - measure between two objects or points.
- `tts_get_relative_transform` - compute relative transform and distance.
- `tts_search_scene` - search for scene objects by text.
- `tts_resolve_object_reference` - resolve a scene reference to a single
  object.
- `tts_register_scene_alias` - persist a semantic alias for a scene object.
- `tts_list_scene_aliases` - list stored semantic aliases.
- `tts_remove_scene_alias` - remove a stored alias.
- `tts_inspect_container` - inspect a container's contents.
- `tts_get_zone_objects` - list objects inside a tagged zone.
- `tts_get_snap_points` - inspect snap points on an object.
- `tts_take_from_container` - remove one item from a container.
- `tts_put_object_into_container` - insert one object into a container.
- `tts_validate_scene_requirements` - check required scene conditions.
- `tts_validate_zone_occupancy` - verify zone occupancy constraints.
- `tts_place_adjacent_to` - place an object adjacent to a target.
- `tts_place_in_zone` - place an object into a named zone.
- `tts_place_in_tagged_zone` - place an object into a tagged board square.
- `tts_align_to_object` - align one object to another.
- `tts_get_scene_summary` - return a compact scene snapshot.
- `tts_capture_view_info` - report screenshot geometry and capture metadata.
- `tts_calibrate_view` - validate a screen rectangle for capture.
- `tts_focus_object_and_capture` - focus the camera and capture a snapshot.
- `tts_wait_for_object_settle` - wait for motion to settle after a move.
- `tts_get_object` - fetch one object's summary.
- `tts_capture_view` - capture the current camera view.
- `tts_recent_chat` - read recent in-game chat.
- `tts_wait_for_chat` - wait for the next chat message.
- `tts_ai_chat` - submit a chat message through the AI gateway.
- `tts_get_scripts` - inspect loaded Lua scripts.
- `tts_recent_events` - read recent bridge events.
- `tts_list_game_rules` - list available game rule files.
- `tts_read_game_rule` - read one game rule file.
- `tts_validate_chess_mapping` - validate the chess square mapping.
- `tts_get_session` - read the persisted AI/session state.
- `tts_checkpoint_session` - persist a completed-turn session checkpoint.
- `tts_audit_events` - read filtered AI/TTS audit events.
- `tts_inspect_save_file` - inspect the default numbered save file.

## Generic Mutation Tools

- `tts_set_camera` - move the camera to a target position.
- `tts_set_camera_and_capture` - move the camera and capture a screenshot.
- `tts_move_object` - move one object to exact coordinates.
- `tts_move_checkers_piece` - validated checker movement along the square
  lattice.
- `tts_rotate_object` - rotate one object.
- `tts_set_object_name` - rename one object.
- `tts_set_object_lock` - lock or unlock one object.
- `tts_spawn_builtin` - spawn a built-in TTS object.
- `tts_destroy_object` - destroy an object with irreversible confirmation.
- `tts_broadcast` - broadcast a message in TTS.
- `tts_execute_action_plan` - execute a bounded multi-step action plan.
- `tts_edit_save_file` - edit the numbered save file with bounded JSON Pointer
  ops.
- `tts_load_save_file` - load a numbered save through the GUI flow.

## Bridge Entry Points

- `tts_mcp_global.lua` - the full runtime Global script bridge.
- `tts_killteam_setup_global.lua` - the placement-only setup bridge.
