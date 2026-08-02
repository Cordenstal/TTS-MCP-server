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

    def test_killteam_setup_context_filters_to_explicit_placement_objects(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")

        objects = [
            {
                "guid": "operative-1",
                "name": "Plague Marine",
                "type": "Figurine",
                "tags": ["Operative"],
                "position": {"x": 1, "y": 1, "z": 1},
                "bounds": {"size": {"x": 1, "y": 2, "z": 1}},
            },
            {
                "guid": "terrain-1",
                "name": "bba946",
                "type": "LayoutZone",
                "tags": ["KT_MISSION_TERRAIN"],
                "position": {"x": 1, "y": 3, "z": 1},
                "bounds": {"size": {"x": 8, "y": 4, "z": 8}},
            },
            {
                "guid": "bag-1",
                "name": "Faction Bag",
                "type": "Bag",
                "tags": [],
            },
        ]
        with patch.object(
            server,
            "_killteam_setup_call",
            return_value={"objects": objects},
        ):
            result = server._killteam_setup_context_sync(max_results=20)

        self.assertEqual([item["guid"] for item in result["categories"]["operatives"]], ["operative-1"])
        self.assertEqual([item["guid"] for item in result["categories"]["terrain"]], ["terrain-1"])
        self.assertEqual(result["count"], 2)
        self.assertEqual([item["guid"] for item in result["objects"]], ["operative-1", "terrain-1"])

    def test_killteam_setup_context_builds_two_model_terrain_adjusted_batch(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        objects = [
            {
                "guid": f"operative-{index}",
                "name": "Plague Marine",
                "type": "Figurine",
                "tags": ["Operative"],
                "position": {"x": 0, "y": 1, "z": 0},
                "bounds": {"center": {"x": 0, "y": 1, "z": 0}, "size": {"x": 1, "y": 2, "z": 1}},
            }
            for index in range(6)
        ]
        objects.extend([
            {
                "guid": "zone-blue",
                "name": "Blue Deployment",
                "type": "LayoutZone",
                "tags": ["_deployment_zone_blue"],
                "position": {"x": 0, "y": 1, "z": 0},
                "bounds": {"center": {"x": 0, "y": 1, "z": 0}, "size": {"x": 20, "y": 2, "z": 20}},
            },
            {
                "guid": "terrain-1",
                "name": "bba946",
                "type": "LayoutZone",
                "tags": ["KT_MISSION_TERRAIN"],
                "position": {"x": -6, "y": 3, "z": -6},
                "bounds": {"center": {"x": -6, "y": 3, "z": -6}, "size": {"x": 6, "y": 4, "z": 6}},
            },
        ])
        with patch.object(server, "_killteam_setup_call", return_value={"objects": objects}):
            result = server._killteam_setup_context_sync(max_results=50)

        self.assertEqual(result["setup_plan"]["batch_size"], 2)
        terrain_candidates = [
            candidate for candidate in result["setup_plan"]["candidates"]
            if "terrain-1" in candidate["support_guids"]
        ]
        self.assertTrue(terrain_candidates)
        self.assertTrue(all(candidate["position"]["y"] >= 4.0 for candidate in terrain_candidates))

    def test_killteam_setup_context_excludes_placed_models_before_ranking(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        objects = [
            {
                "guid": f"operative-{index}",
                "name": "Plague Marine",
                "type": "Figurine",
                "tags": ["Operative"],
                "position": {"x": 0, "y": 1, "z": 0},
                "bounds": {"center": {"x": 0, "y": 1, "z": 0}, "size": {"x": 1, "y": 2, "z": 1}},
            }
            for index in range(6)
        ]
        objects.append({
            "guid": "zone-blue",
            "name": "Blue Deployment",
            "type": "LayoutZone",
            "tags": ["_deployment_zone_blue"],
            "position": {"x": 0, "y": 1, "z": 0},
            "bounds": {"center": {"x": 0, "y": 1, "z": 0}, "size": {"x": 20, "y": 2, "z": 20}},
        })
        with patch.object(server, "_killteam_setup_call", return_value={"objects": objects}):
            result = server._killteam_setup_context_sync(
                max_results=50,
                exclude_guids=["operative-0", "operative-1"],
            )

        remaining_guids = [item["guid"] for item in result["categories"]["operatives"]]
        self.assertNotIn("operative-0", remaining_guids)
        self.assertNotIn("operative-1", remaining_guids)
        self.assertEqual(len(remaining_guids), 4)
        recommended = result["setup_plan"]["recommended_batch"]
        self.assertEqual(len(recommended), 2)
        self.assertTrue(all(item["guid"] not in {"operative-0", "operative-1"} for item in recommended))
        self.assertNotEqual(
            recommended[0]["footprint"],
            recommended[1]["footprint"],
        )

    def test_killteam_setup_context_uses_excluded_and_opponent_models_as_blockers(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")

        def operative(guid: str, name: str, x: float, tags: list[str] | None = None) -> dict[str, object]:
            return {
                "guid": guid,
                "name": name,
                "type": "Figurine",
                "tags": tags or ["Operative"],
                "position": {"x": x, "y": 1, "z": 0},
                "bounds": {"center": {"x": x, "y": 1, "z": 0}, "size": {"x": 1, "y": 2, "z": 1}},
            }

        objects = [
            operative("candidate-0", "Plague Marine", -30),
            operative("candidate-1", "Plague Marine", -31),
            operative("candidate-2", "Plague Marine", -32),
            operative("candidate-3", "Plague Marine", -33),
            # The highest scoring slot is at x=9.5, z=0. These models must
            # remain blockers even though neither is eligible to move.
            operative("deployed-ai", "Plague Marine", 9.5),
            operative("opponent", "Opponent Operative", 4.75, ["Operative", "Red"]),
            {
                "guid": "zone-blue",
                "name": "Blue Deployment",
                "type": "LayoutZone",
                "tags": ["_deployment_zone_blue"],
                "position": {"x": 0, "y": 1, "z": 0},
                "bounds": {"center": {"x": 0, "y": 1, "z": 0}, "size": {"x": 20, "y": 2, "z": 20}},
            },
        ]
        with patch.object(server, "_killteam_setup_call", return_value={"objects": objects}):
            result = server._killteam_setup_context_sync(
                max_results=50,
                exclude_guids=["deployed-ai"],
            )

        recommended = result["setup_plan"]["recommended_batch"]
        self.assertEqual(len(recommended), 2)
        self.assertEqual([item["guid"] for item in recommended], ["candidate-0", "candidate-1"])
        for candidate in recommended:
            self.assertFalse(server._setup_rects_overlap(candidate["footprint"], server._setup_box(objects[4])))
            self.assertFalse(server._setup_rects_overlap(candidate["footprint"], server._setup_box(objects[5])))

    def test_killteam_setup_context_uses_layout_zone_scale_when_bounds_are_zero(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        objects = [
            {
                "guid": f"operative-{index}",
                "name": "Plague Marine",
                "type": "Figurine",
                "tags": ["Operative"],
                "position": {"x": 30 + index, "y": 1.5, "z": -35 - index},
                "bounds": {"center": {"x": 30 + index, "y": 1.5, "z": -35 - index}, "size": {"x": 1, "y": 2, "z": 1}},
            }
            for index in range(6)
        ]
        objects.append({
            "guid": "zone-blue",
            "name": "LayoutZone",
            "type": "Layout",
            "tags": ["_deployment_zone_blue"],
            "position": {"x": 0, "y": 8, "z": -8},
            "scale": {"x": 30, "y": 14, "z": 6},
            "bounds": {"center": {"x": 0, "y": 8, "z": -8}, "size": {"x": 0, "y": 0, "z": 0}},
        })
        with patch.object(server, "_killteam_setup_call", return_value={"objects": objects}):
            result = server._killteam_setup_context_sync(max_results=50)

        self.assertEqual(result["setup_plan"]["batch_size"], 2)
        self.assertGreater(result["setup_plan"]["candidate_count"], 0)
        self.assertTrue(result["setup_plan"]["recommended_batch"])
        self.assertTrue(all(candidate.get("candidate_id") for candidate in result["setup_plan"]["candidates"]))


if __name__ == "__main__":
    unittest.main()
