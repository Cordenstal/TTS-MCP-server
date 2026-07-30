from pathlib import Path
import unittest


class KillTeamSetupLuaBridgeSourceTests(unittest.TestCase):
    def test_setup_bridge_exposes_placement_only_actions(self) -> None:
        source = Path("tts_killteam_setup_global.lua").read_text(encoding="utf-8")

        self.assertIn('local MCP_BRIDGE_VERSION = "2026-07-29-setup-placement-v2-chat"', source)
        self.assertIn("function onLoad()", source)
        self.assertIn("function onChat(message, sender)", source)
        self.assertIn('event = "chat_message"', source)
        self.assertIn("mcp_forward_chat(message, sender)", source)
        self.assertIn('local MCP_HTTP_CHAT_URL = "http://127.0.0.1:8765/chat"', source)
        self.assertIn("WebRequest.custom(", source)
        self.assertIn('message = raw_message', source)
        self.assertIn("printToAll(text", source)
        self.assertIn("MCP_HANDLERS.setup_ping", source)
        self.assertIn("MCP_HANDLERS.setup_list_objects", source)
        self.assertIn("MCP_HANDLERS.setup_place_model", source)
        self.assertIn("MCP_HANDLERS.move_object", source)
        self.assertIn("args = mcp_json_safe(args)", source)
        self.assertIn("local function mcp_is_operative_figurine", source)
        self.assertIn('if string.lower(tostring(args.tag or "")) == "operative" and not mcp_is_operative_figurine(obj) then', source)
        self.assertIn("setup placement requires an Operative figurine; got", source)
        self.assertIn("printToAll(\"Kill Team setup placement bridge loaded.\"", source)
        self.assertIn("printToAll(\"Kill Team setup placement bridge is active.\"", source)
        self.assertIn("print(\"[tts-mcp-response]\"", source)
        self.assertIn("Wait.frames(function()", source)
        self.assertIn("setPositionSmooth", source)
        self.assertIn("setPosition(", source)

    def test_setup_bridge_logs_raw_and_normalized_move_types(self) -> None:
        source = Path("tts_killteam_setup_global.lua").read_text(encoding="utf-8")

        self.assertIn("local function mcp_type_name", source)
        self.assertIn("local function mcp_setup_request_summary", source)
        self.assertIn("local function mcp_setup_position_table", source)
        self.assertIn('print(mcp_setup_request_summary(args, request_id, action, "pre"))', source)
        self.assertIn('print(mcp_setup_request_summary(args, request_id, action, "post"))', source)
        self.assertIn('MCP_HANDLERS.setup_place_model = function(args, request_id)', source)
        self.assertIn('MCP_HANDLERS.move_object = function(args, request_id)', source)
        self.assertIn('return mcp_setup_place_model(args, request_id, "move_object")', source)
        self.assertIn('error("position must contain numeric x, y, and z values; "', source)
