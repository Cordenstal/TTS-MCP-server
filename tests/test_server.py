from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

try:
    from tts_mcp.app import server
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-gated test import
    server = None
    _SERVER_IMPORT_ERROR = exc
else:
    _SERVER_IMPORT_ERROR = None


class ServerCaptureTests(unittest.TestCase):
    def test_capture_view_snapshot_falls_back_when_mss_is_unavailable(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        sample = Image.new("RGB", (4, 2), color=(12, 34, 56))

        with patch.object(server, "mss", None), patch.object(
            server.PILImageGrab,
            "grab",
            return_value=sample,
        ) as grab:
            image, metadata = server._capture_view_snapshot(10, 20, 4, 2, 2)

        self.assertEqual(grab.call_count, 1)
        self.assertEqual(metadata["rectangle"], {"left": 10, "top": 20, "width": 4, "height": 2})
        self.assertEqual(metadata["output_size"], {"width": 2, "height": 1})
        self.assertEqual(image.size, (2, 1))
        self.assertFalse(metadata["blank_frame_suspected"])

    def test_killteam_setup_observation_uses_generic_fixture_profile(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")

        calls: list[dict[str, object]] = []

        with patch.object(
            server,
            "_killteam_setup_sync",
            side_effect=lambda **kwargs: calls.append(kwargs) or {"status": "ready"},
        ):
            result = server._ai_observation_tool(
                "tts_killteam_setup",
                {
                    "ai_team": "ai",
                    "units_per_inch": 1.25,
                    "ai_dice_count": 2,
                    "opponent_dice_count": 3,
                },
            )

        self.assertEqual(result, {"status": "ready"})
        self.assertEqual(calls, [{
            "ai_team": "ai",
            "units_per_inch": 1.25,
            "ai_dice_count": 2,
            "opponent_dice_count": 3,
            "fixture_profile": "",
            "initiative_side": "",
        }])


if __name__ == "__main__":
    unittest.main()
