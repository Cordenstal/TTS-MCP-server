from pathlib import Path
import unittest


class LuaBridgeSourceTests(unittest.TestCase):
    def test_external_message_decodes_before_unwrapping_envelope(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        decode_index = source.index("local function mcp_decode_message")
        unwrap_index = source.index("local function mcp_unwrap_external_message")
        handler_index = source.index("function mcp_handleExternalMessage")

        self.assertLess(decode_index, unwrap_index)
        self.assertLess(unwrap_index, handler_index)
        self.assertIn('tostring(data.messageID or "") == "2"', source)
        self.assertIn("data = mcp_unwrap_external_message(data)", source)

    def test_on_chat_does_not_consume_player_chat(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        chat_handler = source[source.index("function onChat(message, sender)"):]

        self.assertNotIn("return true", chat_handler)

    def test_ai_chat_uses_an_explicit_opaque_color(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        compact_source = source.replace(" ", "")

        self.assertIn("printToAll(text,{r=1,g=1,b=1,a=1})", compact_source)
        self.assertNotIn("printToAll(text)", source)

    def test_on_chat_posts_nonempty_messages_and_reports_delivery(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        chat_handler = source[source.index("function onChat(message, sender)"):]

        self.assertIn("mcp_forward_chat(message, sender)", chat_handler)
        self.assertIn("WebRequest.custom(", chat_handler)
        self.assertIn('MCP_HTTP_CHAT_URL', chat_handler)
        self.assertIn("chat received; sending to http://127.0.0.1:8765/chat", chat_handler)
        self.assertIn('HTTP status: " .. tostring(request.response_code) .. " body: " .. body', chat_handler)

    def test_large_chat_response_uses_non_pattern_trim(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        sanitizer = source[
            source.index("local function mcp_public_chat_text(value)"):
            source.index("local function mcp_decode_message(data)")
        ]
        self.assertIn("local function mcp_trim(value)", source)
        self.assertNotIn('string.match(text, "^%s*(.-)%s*$")', source)
        self.assertNotIn("string.gmatch(", sanitizer)
        self.assertNotIn("string.gsub(", sanitizer)

    def test_mcp_responses_use_hidden_http_transport_not_player_chat(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn('local MCP_HTTP_BRIDGE_RESPONSE_URL = "http://127.0.0.1:8765/bridge/response"', source)
        self.assertIn("local function mcp_post_bridge_response(response)", source)
        helper_start = source.index("local function mcp_send_bridge_response")
        helper_end = source.find("\nend", helper_start)
        helper_source = source[helper_start:helper_end]
        self.assertIn("pcall(mcp_post_bridge_response, response)", helper_source)
        self.assertIn("pcall(sendExternalMessage, response)", helper_source)
        self.assertIn("Wait.frames(function()", helper_source)

        for function_name in ("mcp_send_ok", "mcp_send_error"):
            start = source.index(f"local function {function_name}")
            end = source.find("\nend", start)
            function_source = source[start:end]
            self.assertIn("mcp_send_bridge_response(response)", function_source)
            self.assertNotIn("[tts-mcp-response]", function_source)

    def test_killteam_dice_and_counter_handlers_are_allowlisted(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn("MCP_HANDLERS.killteam_roll_dice", source)
        self.assertIn("MCP_HANDLERS.set_counter_value", source)
        self.assertIn('mcp_has_tag(die, "tts_mcp:entity=die")', source)
        self.assertIn("getRotationValue", source)
        self.assertIn("Counter.setValue", source)

    def test_killteam_dice_and_los_handlers_decode_scalar_safe_inputs(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        dice_handler = source[
            source.index("MCP_HANDLERS.killteam_roll_dice"):
            source.index("MCP_HANDLERS.set_counter_value")
        ]
        los_handler = source[
            source.index("MCP_HANDLERS.killteam_probe_los"):
            source.index("MCP_HANDLERS.killteam_roll_dice")
        ]

        self.assertIn('mcp_decode_json_array(args.dice_guids_json, "dice_guids_json")', dice_handler)
        self.assertIn("mcp_has_tag(die, args.die_tag)", dice_handler)
        self.assertIn("x = tonumber(args.eye_x)", los_handler)
        self.assertIn("y = tonumber(args.eye_y)", los_handler)
        self.assertIn("z = tonumber(args.eye_z)", los_handler)

    def test_killteam_red_observation_and_semantic_damage_are_bounded(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn("MCP_HANDLERS.killteam_observe_defense_roll", source)
        self.assertIn("expected_count", source)
        self.assertIn("MCP_HANDLERS.killteam_apply_damage", source)
        self.assertIn('operative.call("damage"', source)
        self.assertIn("expected_wounds", source)
        self.assertIn("before_wounds", source)
        self.assertIn("after_wounds", source)

    def test_killteam_roster_handler_reads_bounded_dedicated_container_contents(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn("MCP_HANDLERS.killteam_get_roster", source)
        self.assertIn("mcp_container_items(container)", source)
        self.assertIn("truncated = items.truncated", source)

    def test_killteam_los_probe_uses_bounded_physics_raycast_evidence(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn("MCP_HANDLERS.killteam_probe_los", source)
        self.assertIn("positionToWorld", source)
        self.assertIn("getBounds", source)
        self.assertIn("getTransformRight", source)
        self.assertIn("getTransformUp", source)
        self.assertIn("Physics.cast", source)
        self.assertIn("type = 1", source)
        self.assertIn("max_distance", source)
        self.assertIn("visibility_fraction", source)
        self.assertIn("physics_colliders_only", source)

    def test_compact_object_summary_retains_model_identity_metadata(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("local function mcp_compact_object_summary")
        end = source.index("-- TTS Vector", start)
        compact = source[start:end]

        self.assertIn("description = mcp_try(function() return obj.getDescription() end)", compact)
        self.assertIn("type = mcp_try(function() return obj.type end)", compact)

    def test_object_listing_skips_stale_tts_references_instead_of_aborting(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.list_objects = function")
        end = source.index("MCP_HANDLERS.find_nearest_objects", start)
        listing = source[start:end]

        self.assertIn("mcp_live_object(obj)", listing)
        self.assertIn("pcall(function()", listing)
        self.assertIn("summary.guid", listing)
        self.assertIn("mcp_safe_object_tags(obj)", source)

    def test_external_message_boundary_returns_a_correlated_error_when_dispatch_escapes(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("function onExternalMessage(data)")
        boundary = source[start:]

        self.assertIn("pcall(mcp_handleExternalMessage, data)", boundary)
        self.assertIn("mcp_send_error,", boundary)
        self.assertIn("request_id,", boundary)

    def test_ping_exposes_bridge_version_without_requiring_scene_enumeration(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.ping = function")
        end = source.index("MCP_HANDLERS.list_objects", start)
        handler = source[start:end]

        self.assertIn("bridge_version = MCP_BRIDGE_VERSION", handler)
        self.assertIn("local object_count = mcp_try(function() return #getObjects() end)", handler)
        self.assertIn("object_count = tonumber(object_count) or -1", handler)

    def test_external_message_prefers_root_scalar_fields_over_managed_nested_values(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("function mcp_handleExternalMessage(data)")
        end = source.index("-- Remove this wrapper", start)
        boundary = source[start:end]

        self.assertIn("local nested_args = mcp_try(function() return data.args end)", boundary)
        self.assertIn("local args = {}", boundary)
        self.assertIn("local value = mcp_try(function() return data[field] end)", boundary)
        self.assertIn("if value == nil and nested_args ~= nil then", boundary)
        self.assertIn("args[field] = value", boundary)

    def test_external_message_dispatches_killteam_collection_before_nested_args(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("function mcp_handleExternalMessage(data)")
        end = source.index("-- Remove this wrapper", start)
        boundary = source[start:end]

        fast_path = boundary.index('if action == "killteam_list_objects" then')
        nested_args = boundary.index(
            "local nested_args = mcp_try(function() return data.args end)"
        )
        self.assertLess(fast_path, nested_args)
        self.assertIn('data, "query_tag_count", "query_tag_", 32', boundary)
        self.assertIn('data, "required_guid_count", "required_guid_", 32', boundary)
        self.assertIn('data, "snap_point_tag_count", "snap_point_tag_", 16', boundary)
        self.assertNotIn(
            'tostring(data.query_tags_json or "[]")',
            boundary,
        )

    def test_deployment_resolver_and_guid_reads_bypass_managed_nested_args(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("function mcp_handleExternalMessage(data)")
        end = source.index("-- Remove this wrapper", start)
        boundary = source[start:end]
        nested_args = boundary.index(
            "local nested_args = mcp_try(function() return data.args end)"
        )

        self.assertLess(
            boundary.index('if action == "killteam_deployment_test_objects"'),
            nested_args,
        )
        self.assertLess(
            boundary.index(
                'if action == "get_object" or action == "get_snap_points" then'
            ),
            nested_args,
        )
        resolver_start = source.index(
            "MCP_HANDLERS.killteam_deployment_test_objects = function"
        )
        resolver_end = source.index(
            "MCP_HANDLERS.killteam_deployment_name_search = function",
            resolver_start,
        )
        resolver = source[resolver_start:resolver_end]
        self.assertIn("getObjectsWithTag(tag)", resolver)
        self.assertIn("for _, obj in ipairs(getObjects()) do", resolver)
        self.assertIn("string.find(object_name, name, 1, true)", resolver)
        self.assertNotIn("mcp_canonical_deployment_tag", resolver)
        self.assertIn("mcp_deployment_object_summary(obj)", resolver)
        summary_start = source.index(
            "local function mcp_deployment_object_summary(obj)"
        )
        summary_end = source.index(
            "MCP_HANDLERS.killteam_deployment_test_objects = function",
            summary_start,
        )
        summary = source[summary_start:summary_end]
        self.assertIn("guid =", summary)
        self.assertIn("tags =", summary)
        self.assertIn("position =", summary)
        self.assertNotIn("bounds =", summary)
        self.assertNotIn("getDescription", summary)
        self.assertNotIn("getRotation", summary)
        self.assertNotIn("mcp_zone_guids", summary)
        self.assertIn('wanted_model_name = "plague marine warrior"', resolver)
        self.assertIn('wanted_target_tag = "_deployment_zone_blue"', resolver)
        self.assertNotIn('"*_*plague*_*marine_war_1"', resolver)
        self.assertNotIn('wanted_combat_tag = "combat_zone"', resolver)
        self.assertNotIn('wanted_target_tag = "_deployment_test_blue"', resolver)
        self.assertIn("count = 2", resolver)

    def test_deployment_name_search_is_zero_argument_and_bounded(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.killteam_deployment_name_search = function")
        end = source.index("MCP_HANDLERS.killteam_list_objects = function", start)
        handler = source[start:end]
        boundary_start = source.index("function mcp_handleExternalMessage(data)")
        boundary_end = source.index("-- Remove this wrapper", boundary_start)
        boundary = source[boundary_start:boundary_end]

        self.assertIn('"plague marine"', handler)
        self.assertIn('"novitiate dialogus"', handler)
        self.assertIn('"novitiate hospitaller"', handler)
        self.assertIn('"blue die"', handler)
        self.assertIn('"blue kustom 40k dice roller"', handler)
        self.assertIn('"deployment"', handler)
        self.assertIn("for _, obj in ipairs(getObjects()) do", handler)
        self.assertIn("if #matches < 20 then", handler)
        self.assertIn("mcp_deployment_object_summary(obj)", handler)
        self.assertLess(
            boundary.index('action == "killteam_deployment_name_search"'),
            boundary.index("local nested_args = mcp_try(function() return data.args end)"),
        )

    def test_killteam_snapshot_uses_tagged_objects_and_exact_required_guids(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.killteam_list_objects = function")
        end = source.index("MCP_HANDLERS.killteam_get_roster", start)
        handler = source[start:end]

        self.assertIn("getObjectsWithTag(entity_tag)", handler)
        self.assertIn("getObjectFromGUID(guid)", handler)
        self.assertIn("required_guids_json", handler)
        self.assertIn("query_tags_json", handler)
        self.assertIn("snap_point_tags_json", handler)
        self.assertIn("Global.getSnapPoints()", handler)
        self.assertIn("snap_points = snap_points", handler)
        self.assertNotIn("for _, obj in ipairs(getObjects())", handler)

    def test_killteam_snapshot_skips_uninspectable_tagged_objects(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.killteam_list_objects = function")
        end = source.index("MCP_HANDLERS.killteam_get_roster", start)
        handler = source[start:end]

        self.assertIn("local summary_ok, summary = pcall(function()", handler)
        self.assertIn("if not summary_ok or type(summary) ~= \"table\" then", handler)

    def test_external_message_bridge_keeps_killteam_collection_inputs_scalar(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        handler = source[
            source.index("MCP_HANDLERS.killteam_list_objects = function"):
            source.index("MCP_HANDLERS.killteam_get_roster")
        ]

        self.assertIn('mcp_decode_json_array(args.query_tags_json, "query_tags_json")', handler)
        self.assertIn('mcp_decode_json_array(args.required_guids_json, "required_guids_json")', handler)
        self.assertIn('mcp_decode_json_array(args.snap_point_tags_json, "snap_point_tags_json")', handler)

    def test_killteam_collection_probe_is_bounded_by_stage_and_index(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("MCP_HANDLERS.killteam_probe_collection = function")
        end = source.index("MCP_HANDLERS.killteam_list_objects = function", start)
        handler = source[start:end]

        self.assertIn("local allowed_stages = {", handler)
        self.assertIn('tag_lookup = true', handler)
        self.assertIn('required_summary = true', handler)
        self.assertIn('snap_summary = true', handler)
        self.assertIn("math.max(1, math.min(tonumber(args.probe_index) or 1, 32))", handler)
        self.assertNotIn("load(", handler)
        self.assertNotIn("require(", handler)

    def test_compact_summary_reads_counter_component_safely(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        start = source.index("local function mcp_counter_value")
        end = source.index("local function mcp_container_items", start)
        counter_reader = source[start:end]

        self.assertIn("mcp_try(function() return obj.Counter end)", counter_reader)
        self.assertNotIn("obj == nil or obj.Counter == nil", counter_reader)
