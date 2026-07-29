from pathlib import Path
import unittest


class KillTeamSetupLuaBridgeSourceTests(unittest.TestCase):
    def test_setup_bridge_exposes_placement_only_actions(self) -> None:
        source = Path("tts_killteam_setup_global.lua").read_text(encoding="utf-8")

        self.assertIn('local MCP_BRIDGE_VERSION = "2026-07-29-setup-placement-v1"', source)
        self.assertIn("function onLoad()", source)
        self.assertIn("MCP_HANDLERS.setup_ping", source)
        self.assertIn("MCP_HANDLERS.setup_list_objects", source)
        self.assertIn("MCP_HANDLERS.setup_place_model", source)
        self.assertIn("printToAll(\"Kill Team setup placement bridge loaded.\"", source)
        self.assertIn("printToAll(\"Kill Team setup placement bridge is active.\"", source)
        self.assertIn("print(\"[tts-mcp-response]\"", source)
        self.assertIn("Wait.frames(function()", source)
        self.assertIn("setPositionSmooth", source)
        self.assertIn("setPosition(", source)
