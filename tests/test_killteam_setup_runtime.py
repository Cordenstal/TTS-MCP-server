from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tts_mcp.runtime.killteam_setup_runtime import (
    KillTeamSetupRuntime,
    KillTeamSetupUncertainCommit,
    TTSKillTeamSetupBridge,
    verify_killteam_setup_bridge_source,
)


class FakeKillTeamSetupBridge:
    def __init__(self, objects):
        self.objects = {item["guid"]: copy.deepcopy(item) for item in objects}
        self.calls = []

    def ping(self):
        self.calls.append(("ping",))
        return {
            "bridge": "tts-mcp",
            "bridge_version": "2026-07-29-setup-placement-v1",
            "object_count": len(self.objects),
        }

    def list_objects(self, **kwargs):
        self.calls.append(("list_objects", dict(kwargs)))
        name_contains = str(kwargs.get("name_contains", "")).strip().lower()
        tag = str(kwargs.get("tag", "")).strip().lower()
        compact = bool(kwargs.get("compact", True))
        results = []
        for item in self.objects.values():
            if name_contains and name_contains not in str(item.get("name", "")).lower():
                continue
            if tag and not any(str(value).strip().lower() == tag for value in item.get("tags", [])):
                continue
            if compact:
                results.append({
                    "guid": item["guid"],
                    "name": item.get("name", ""),
                    "type": item.get("type", ""),
                    "tags": copy.deepcopy(item.get("tags", [])),
                    "position": copy.deepcopy(item.get("position", {})),
                    "locked": bool(item.get("locked", False)),
                })
            else:
                results.append(copy.deepcopy(item))
        max_results = max(1, min(int(kwargs.get("max_results", 1000)), 1000))
        return {
            "count": min(len(results), max_results),
            "truncated": len(results) > max_results,
            "objects": results[:max_results],
        }

    def move_object(self, guid, position):
        self.calls.append(("move_object", guid, copy.deepcopy(position)))
        obj = self.objects[guid]
        obj["position"] = dict(position)
        return {
            "status": "verified",
            "guid": guid,
            "name": obj.get("name", ""),
            "tags": copy.deepcopy(obj.get("tags", [])),
            "position": copy.deepcopy(position),
        }

    def place_model(self, guid, position):
        self.calls.append(("place_model", guid, copy.deepcopy(position)))
        obj = self.objects[guid]
        obj["position"] = dict(position)
        return {
            "status": "verified",
            "guid": guid,
            "name": obj.get("name", ""),
            "tags": copy.deepcopy(obj.get("tags", [])),
            "position": copy.deepcopy(position),
        }


def setup_object(guid, *, name, tags, x, y, z):
    return {
        "guid": guid,
        "name": name,
        "type": "Figurine",
        "tags": list(tags),
        "position": {"x": x, "y": y, "z": z},
    }


class KillTeamSetupRuntimeTests(unittest.TestCase):
    def test_ping_reports_bridge_version(self):
        runtime = KillTeamSetupRuntime(FakeKillTeamSetupBridge([]))

        result = runtime.ping()

        self.assertEqual(result["bridge_version"], "2026-07-29-setup-placement-v1")
        self.assertEqual(result["status"], "ready")

    def test_verify_setup_bridge_source_matches_disk_and_caches_success(self):
        with tempfile.TemporaryDirectory() as tempdir:
            disk_path = Path(tempdir) / "tts_killteam_setup_global.lua"
            disk_path.write_text("line 1\nline 2\n", encoding="utf-8")
            calls = []

            def bridge_get_scripts():
                calls.append(True)
                return [{
                    "name": "Global",
                    "script": "line 1\r\nline 2\r\n",
                }]

            first = verify_killteam_setup_bridge_source(
                bridge_get_scripts=bridge_get_scripts,
                bridge_version="2026-07-29-setup-placement-v1",
                disk_path=disk_path,
            )
            second = verify_killteam_setup_bridge_source(
                bridge_get_scripts=bridge_get_scripts,
                bridge_version="2026-07-29-setup-placement-v1",
                disk_path=disk_path,
            )

        self.assertTrue(first["reload_verified"])
        self.assertEqual(first["loaded_hash"], first["disk_hash"])
        self.assertEqual(first["loaded_script_identity"], "Global")
        self.assertEqual(first["verification_source"], "fresh")
        self.assertEqual(second["verification_source"], "cache")
        self.assertEqual(len(calls), 1)

    def test_verify_setup_bridge_source_fails_closed_on_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            disk_path = Path(tempdir) / "tts_killteam_setup_global.lua"
            disk_path.write_text("line 1\nline 2\n", encoding="utf-8")

            result = verify_killteam_setup_bridge_source(
                bridge_get_scripts=lambda: [{
                    "name": "Global",
                    "script": "different source\n",
                }],
                bridge_version="2026-07-29-setup-placement-v1-mismatch",
                disk_path=disk_path,
            )

        self.assertFalse(result["reload_verified"])
        self.assertIn("does not match", result["verification_error"])
        self.assertNotEqual(result["loaded_hash"], result["disk_hash"])

    def test_verify_setup_bridge_source_fails_closed_when_global_script_is_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            disk_path = Path(tempdir) / "tts_killteam_setup_global.lua"
            disk_path.write_text("line 1\nline 2\n", encoding="utf-8")

            result = verify_killteam_setup_bridge_source(
                bridge_get_scripts=lambda: [{
                    "name": "Object",
                    "script": "line 1\nline 2\n",
                }],
                bridge_version="2026-07-29-setup-placement-v1-missing",
                disk_path=disk_path,
            )

        self.assertFalse(result["reload_verified"])
        self.assertIn("Global script state was not found", result["verification_error"])

    def test_list_objects_filters_and_bounds_results(self):
        bridge = FakeKillTeamSetupBridge([
            setup_object("model-1", name="Plague Marine Warrior", tags=["Operative", "_deployment_zone_blue"], x=-20, y=1, z=6),
            setup_object("model-2", name="Target Marker", tags=["objective"], x=4, y=1, z=0),
        ])
        runtime = KillTeamSetupRuntime(bridge)

        result = runtime.list_objects(name_contains="warrior", tag="_deployment_zone_blue", max_results=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["objects"][0]["guid"], "model-1")
        self.assertEqual(bridge.calls[0][0], "list_objects")

    def test_place_model_verifies_exact_position(self):
        bridge = FakeKillTeamSetupBridge([
            setup_object("model-1", name="Plague Marine Warrior", tags=["Operative"], x=-20, y=1, z=6),
        ])
        runtime = KillTeamSetupRuntime(bridge)

        result = runtime.place_model("model-1", {"x": -24.1579723, "y": 1.481601, "z": -9.286173})

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["guid"], "model-1")
        self.assertEqual(bridge.objects["model-1"]["position"], {
            "x": -24.1579723,
            "y": 1.481601,
            "z": -9.286173,
        })
        self.assertIn(("move_object", "model-1", {
            "x": -24.1579723,
            "y": 1.481601,
            "z": -9.286173,
        }), bridge.calls)

    def test_place_model_fails_closed_on_readback_mismatch(self):
        class MismatchBridge(FakeKillTeamSetupBridge):
            def move_object(self, guid, position):
                self.calls.append(("move_object", guid, copy.deepcopy(position)))
                return {
                    "status": "verified",
                    "guid": guid,
                    "name": self.objects[guid].get("name", ""),
                    "tags": copy.deepcopy(self.objects[guid].get("tags", [])),
                    "position": {
                        "x": position["x"] + 1.0,
                        "y": position["y"],
                        "z": position["z"],
                    },
                }

        runtime = KillTeamSetupRuntime(MismatchBridge([
            setup_object("model-1", name="Plague Marine Warrior", tags=["Operative"], x=-20, y=1, z=6),
        ]))

        with self.assertRaises(KillTeamSetupUncertainCommit):
            runtime.place_model("model-1", {"x": -24.1579723, "y": 1.481601, "z": -9.286173})

    def test_deploy_test_model_uses_unique_name_and_target_tag(self):
        bridge = FakeKillTeamSetupBridge([
            setup_object("model-1", name="Plague Marine Warrior", tags=["Operative"], x=-20, y=1, z=6),
            setup_object("target-1", name="Deployment", tags=["_deployment_zone_blue"], x=-18, y=1, z=-8),
        ])
        runtime = KillTeamSetupRuntime(bridge)

        result = runtime.deploy_test_model()

        self.assertEqual(result["model_guid"], "model-1")
        self.assertEqual(result["target_guid"], "target-1")
        self.assertEqual(result["target_position"], {
            "x": -18.0,
            "y": 1.0,
            "z": -8.0,
        })
        self.assertEqual(result["placement"]["position"], {
            "x": -18.0,
            "y": 1.0,
            "z": -8.0,
        })


class TTSKillTeamSetupBridgeTests(unittest.TestCase):
    def test_bridge_maps_to_setup_specific_action_names(self):
        calls = []
        bridge = TTSKillTeamSetupBridge(lambda action, args: calls.append((action, args)) or {"ok": True})

        bridge.ping()
        bridge.list_objects(name_contains="marine", tag="_deployment_zone_blue", max_results=5, compact=True)
        bridge.place_model("model-1", {"x": 1, "y": 2, "z": 3})

        self.assertEqual(calls[0], ("setup_ping", {}))
        self.assertEqual(calls[1], ("setup_list_objects", {
            "name_contains": "marine",
            "tag": "_deployment_zone_blue",
            "max_results": 5,
            "compact": True,
        }))
        self.assertEqual(calls[2], ("setup_place_model", {
            "guid": "model-1",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        }))

    def test_move_object_maps_to_move_object_action(self):
        calls = []
        bridge = TTSKillTeamSetupBridge(lambda action, args: calls.append((action, args)) or {"ok": True})

        bridge.move_object("model-1", {"x": 1, "y": 2, "z": 3})

        self.assertEqual(calls[0], ("move_object", {
            "guid": "model-1",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        }))
