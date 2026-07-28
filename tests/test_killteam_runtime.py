import copy
import copy
import unittest

from killteam_runtime import (
    KillTeamConfig,
    KillTeamRuntime,
    KillTeamRuleError,
    KillTeamSetupError,
    KillTeamUncertainCommit,
    SAVE_131_FIXTURE_PROFILE,
    TTSKillTeamBridge,
    parse_profile_description,
)


class FakeKillTeamBridge:
    def __init__(self, objects, rolls=None, snap_points=None, defense_faces=None, zone_snap_points=None):
        self.objects = {item["guid"]: copy.deepcopy(item) for item in objects}
        self.wounds = {
            item["guid"]: int(
                item.get("script_wounds", (item.get("profile") or {}).get("wounds", 0))
            )
            for item in objects
        }
        self.rolls = list(rolls or [])
        self.snap_points = copy.deepcopy(snap_points or [])
        self.zone_snap_points = copy.deepcopy(zone_snap_points or {})
        self.defense_faces = list(defense_faces or [])
        self.calls = []
        self.list_calls = []
        self.roster = {
            "container_guid": "e5adb7",
            "items": [{
                "guid": "roster-model-1",
                "name": "Plague Marine Heavy Gunner",
                "description": "M 5 APL 3 SV 3+ W 14",
                "tags": ["plague-marine", "heavy-gunner"],
            }],
        }

    def list_objects(self, **_kwargs):
        self.list_calls.append(dict(_kwargs))
        return {
            "objects": [copy.deepcopy(item) for item in self.objects.values()],
            "snap_points": copy.deepcopy(self.snap_points),
        }

    def get_object(self, guid):
        return copy.deepcopy(self.objects[guid])

    def get_snap_points(self, guid):
        self.calls.append(("get_snap_points", guid))
        return {
            "guid": guid,
            "snap_points": copy.deepcopy(self.zone_snap_points.get(guid, [])),
        }

    def move_object(self, guid, position):
        self.calls.append(("move_object", guid, position))
        self.objects[guid]["position"] = dict(position)
        return copy.deepcopy(self.objects[guid])

    def roll_dice(self, *, team, dice_guids, roller_guid, purpose, die_tag=""):
        self.calls.append((
            "roll_dice",
            team,
            tuple(dice_guids),
            roller_guid,
            purpose,
            die_tag,
        ))
        if not self.rolls:
            raise AssertionError("the fake roller ran out of configured results")
        return {"faces": list(self.rolls.pop(0)), "roller_guid": roller_guid}

    def observe_defense_roll(self, *, station_guid, expected_count):
        self.calls.append(("observe_defense_roll", station_guid, expected_count))
        return {
            "station_guid": station_guid,
            "faces": list(self.defense_faces),
        }

    def apply_damage(self, guid, *, damage, expected_wounds):
        self.calls.append(("apply_damage", guid, damage, expected_wounds))
        current = self.wounds[guid]
        if current != expected_wounds:
            raise AssertionError("unexpected wound precondition")
        after = max(0, current - damage)
        self.wounds[guid] = after
        return {
            "guid": guid,
            "before_wounds": current,
            "after_wounds": after,
            "damage": damage,
        }

    def set_object_name(self, guid, name):
        self.calls.append(("set_object_name", guid, name))
        self.objects[guid]["name"] = name
        return self.get_object(guid)

    def set_counter_value(self, guid, value):
        self.calls.append(("set_counter_value", guid, value))
        self.objects[guid]["counter_value"] = value
        return self.get_object(guid)

    def probe_line_of_sight(self, observer_guid, target_guid, *, eye_local=None, debug=False):
        self.calls.append(("probe_line_of_sight", observer_guid, target_guid, eye_local, debug))
        blockers = [
            item["guid"]
            for item in self.objects.values()
            if any(str(tag).endswith("blocks_los=true") for tag in item.get("tags", []))
        ]
        visible = not blockers
        return {
            "observer_guid": observer_guid,
            "target_guid": target_guid,
            "visible": visible,
            "visible_rays": 9 if visible else 0,
            "total_rays": 9,
            "visibility_fraction": 1.0 if visible else 0.0,
            "samples": [],
            "blocker_guids": blockers,
            "collider_warning": "physics_colliders_only",
        }

    def get_roster(self, container_guid):
        self.calls.append(("get_roster", container_guid))
        return copy.deepcopy(self.roster)


def tag(*entries):
    return [f"tts_mcp:{entry}" for entry in entries]


def operative(guid, *, team, operative_id, profile, x, z, visible=True):
    return {
        "guid": guid,
        "name": operative_id,
        "description": "",
        "tags": tag(
            "entity=operative",
            f"team={team}",
            f"operative_id={operative_id}",
            f"profile={profile}",
            "visibility=public" if visible else "visibility=hidden",
        ),
        "position": {"x": x, "y": 1.0, "z": z},
        "bounds": {"center": {"x": x, "y": 1.0, "z": z}, "size": {"x": 1, "y": 2, "z": 1}},
        "profile": {
            "move": 5,
            "apl": 3,
            "wounds": 14,
            "save": 3,
            "weapons": {
                "boltgun": {"attacks": 4, "hit": 3, "damage": 3, "range": 8}
            },
        } if profile == "plague_warrior" else {
            "move": 5,
            "apl": 2,
            "wounds": 10,
            "save": 4,
            "defense_dice": 3,
        },
        "visible": visible,
    }


def fixture_objects():
    return [
        operative("ai-1", team="ai", operative_id="plague-warrior-01", profile="plague_warrior", x=0, z=0),
        operative("96fe20", team="opponent", operative_id="target-01", profile="target", x=5, z=0),
        operative("enemy-hidden", team="opponent", operative_id="hidden-01", profile="target", x=2, z=2, visible=False),
        {"guid": "die-a", "tags": tag("entity=die", "team=ai"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "die-b", "tags": tag("entity=die", "team=ai"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "die-c", "tags": tag("entity=die", "team=ai"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "die-d", "tags": tag("entity=die", "team=ai"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "def-a", "tags": tag("entity=die", "team=opponent"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "def-b", "tags": tag("entity=die", "team=opponent"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "def-c", "tags": tag("entity=die", "team=opponent"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "roller", "tags": tag("entity=dice_roller"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "cp", "tags": tag("entity=counter", "counter=cp", "team=ai"), "counter_value": 2},
        {"guid": "vp", "tags": tag("entity=counter", "counter=vp", "team=ai"), "counter_value": 0},
        {"guid": "calibration", "tags": tag("entity=calibration", "axis=xz", "units_per_inch=1")},
    ]


def save_131_native_objects():
    return [
        operative("96fe20", team="unused", operative_id="unused", profile="plague_warrior", x=20.6, z=-41.6)
        | {
            "name": "Plague Marine Warrior",
            "tags": ["KTUIMini", "LEGIONARY", "Operative", "Chaos"],
            "description": """Plague Marine Warrior
[D36B3E][[84E680]M[-] [ffffff]5"[-]] [[84E680]APL[-] [ffffff]3[-]] [[84E680]SV[-] [ffffff]3+[-]] [[84E680]W[-] [ffffff]14[-]][-]
[1E87FF]R[-] Boltgun
[84E680]ATK[-] 4 [84E680]HIT[-] 3+ [84E680]DMG[-] 3/4
[84E680]WR[-]: Toxic""",
            "profile": None,
            "script_wounds": 14,
        },
        operative("377732", team="unused", operative_id="unused", profile="target", x=-18.0, z=0.0)
        | {
            "name": "Novitiate Dialogus",
            "tags": ["KTUIMini", "NOVITIATE", "Operative", "Imperium"],
            "description": """[D36B3E][[84E680]APL[-] [ffffff]2[-]] [[84E680]MOVE[-] [ffffff]6"[-]]
[[84E680]SAVE[-] [ffffff]4+[-]] [[84E680]WOUNDS[-] [ffffff]7[-]][-]""",
            "profile": None,
            "script_wounds": 7,
        },
        *[
            {
                "guid": guid,
                "name": "Blue D6",
                "tags": ["_dice_blue"],
                "position": {"x": -40 + index, "y": 1, "z": -30},
            }
            for index, guid in enumerate(("2831c0", "bde8ee", "87bb98", "967871", "ffeef7", "d08c28"))
        ],
        {"guid": "175503", "name": "Blue Dice Roller", "tags": ["_blue_dice_roller"]},
        {"guid": "f1adc9", "name": "Red Dice Roller", "tags": []},
        {"guid": "e5adb7", "name": "Plague Marines", "type": "Bag", "tags": []},
        {"guid": "2cc38b", "name": "CP", "tags": [], "counter_value": 3},
        {"guid": "d9b193", "name": "Kill VP", "tags": [], "counter_value": 0},
        {"guid": "7ff953", "name": "Tac VP", "tags": [], "counter_value": 0},
        {"guid": "53befd", "name": "Crit VP", "tags": [], "counter_value": 0},
        {
            "guid": "a48f81",
            "name": "Combat Zone",
            "type": "LayoutZone",
            "tags": ["combat_zone"],
            "position": {"x": -18.1796, "y": 8.4816, "z": 0.02525},
            "bounds": {
                "center": {"x": -18.1796, "y": 8.4816, "z": 0.02525},
                "size": {"x": 30.0961, "y": 14, "z": 22.1123},
            },
        },
        {
            "guid": "865d5c",
            "name": "Blue Deployment",
            "type": "LayoutZone",
            "tags": ["_deployment_zone_blue"],
            "position": {"x": -18, "y": 1, "z": -8},
            "bounds": {
                "center": {"x": -18, "y": 1, "z": -8},
                "size": {"x": 30, "y": 2, "z": 6},
            },
        },
        {
            "guid": "74bea2",
            "name": "Barrier",
            "tags": ["KT_MANAGED", "KT_MISSION_TERRAIN", "KT_TERRAIN_STYLE=outdoor"],
            "position": {"x": -24.142, "y": 1.4849, "z": -7.9771},
            "bounds": {
                "center": {"x": -24.142, "y": 1.4849, "z": -7.9771},
                "size": {"x": 4, "y": 2, "z": 1},
            },
        },
    ]


class KillTeamRuntimeTests(unittest.TestCase):
    def test_live_bridge_uses_scalar_safe_dedicated_killteam_snapshot(self):
        calls = []
        bridge = TTSKillTeamBridge(
            lambda action, args: calls.append((action, args)) or {"objects": []}
        )

        bridge.list_objects(
            max_results=1000,
            compact=True,
            required_guids=["96fe20"],
            query_tags=["Operative", "_dice_blue"],
            snap_point_tags=["_start_test_spot"],
        )

        self.assertEqual(calls, [(
            "killteam_list_objects",
            {
                "max_results": 1000,
                "query_tags_json": '["Operative","_dice_blue"]',
                "required_guids_json": '["96fe20"]',
                "snap_point_tags_json": '["_start_test_spot"]',
            },
        )])

    def test_live_bridge_uses_zero_argument_deployment_resolver(self):
        calls = []
        bridge = TTSKillTeamBridge(
            lambda action, args: calls.append((action, args)) or {"objects": []}
        )

        bridge.list_objects(
            max_results=2,
            compact=True,
            query_names=["Plague Marine Warrior"],
            query_tags=["_deployment_zone_blue"],
        )

        self.assertEqual(calls, [(
            "killteam_deployment_test_objects",
            {},
        )])

    def test_live_bridge_keeps_dice_and_los_vectors_scalar_safe(self):
        calls = []
        bridge = TTSKillTeamBridge(
            lambda action, args: calls.append((action, args)) or {}
        )

        bridge.roll_dice(
            team="ai",
            dice_guids=["2831c0", "bde8ee"],
            roller_guid="175503",
            purpose="attack",
            die_tag="_dice_blue",
        )
        bridge.probe_line_of_sight(
            "96fe20",
            "377732",
            eye_local={"x": 0, "y": 1.5, "z": 0},
        )

        self.assertEqual(calls[0], (
            "killteam_roll_dice",
            {
                "team": "ai",
                "dice_guids_json": '["2831c0","bde8ee"]',
                "roller_guid": "175503",
                "purpose": "attack",
                "die_tag": "_dice_blue",
            },
        ))
        self.assertEqual(calls[1], (
            "killteam_probe_los",
            {
                "observer_guid": "96fe20",
                "target_guid": "377732",
                "eye_x": 0.0,
                "eye_y": 1.5,
                "eye_z": 0.0,
                "debug": False,
            },
        ))

    def test_live_bridge_reads_object_snap_points(self):
        calls = []
        bridge = TTSKillTeamBridge(
            lambda action, args: calls.append((action, args)) or {"snap_points": []}
        )

        bridge.get_snap_points("865d5c")

        self.assertEqual(calls, [("get_snap_points", {"guid": "865d5c"})])

    def test_save_131_profile_discovers_setup_from_native_tags_and_global_snap_point(self):
        bridge = FakeKillTeamBridge(
            save_131_native_objects(),
            snap_points=[{
                "tags": ["_start_test_spot"],
                "position": {"x": -24.1579723, "y": 1.481601, "z": -9.286173},
            }],
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )

        setup = runtime.setup()
        observation = runtime.observe()

        self.assertEqual(setup["deployment_subject"]["guid"], "96fe20")
        self.assertEqual(setup["visible_target"]["guid"], "377732")
        self.assertEqual(setup["start_test_spot"]["position"], {
            "x": -24.1579723,
            "y": 1.481601,
            "z": -9.286173,
        })
        self.assertEqual(setup["roller_guid"], "175503")
        self.assertEqual(setup["defense_station_guid"], "f1adc9")
        self.assertEqual(setup["roster_container_guid"], "e5adb7")
        self.assertEqual(observation["counters"]["cp"]["guid"], "2cc38b")
        self.assertEqual(observation["counters"]["kill_vp"]["guid"], "d9b193")
        self.assertEqual(observation["counters"]["tac_vp"]["guid"], "7ff953")
        self.assertEqual(observation["counters"]["crit_vp"]["guid"], "53befd")
        self.assertEqual(len(observation["dice"]["ai"]), 6)
        self.assertEqual(bridge.list_calls[0]["required_guids"], [
            "f1adc9",
            "e5adb7",
            "2cc38b",
            "d9b193",
            "7ff953",
            "53befd",
            "74bea2",
        ])
        self.assertIn("_blue_dice_roller", bridge.list_calls[0]["query_tags"])
        self.assertNotIn("dice_roller", bridge.list_calls[0]["query_tags"])

    def test_save_131_validation_shot_pauses_for_red_then_applies_real_wounds(self):
        bridge = FakeKillTeamBridge(
            save_131_native_objects(),
            rolls=[[5, 4, 2, 1]],
            defense_faces=[4, 2, 1],
            snap_points=[{
                "tags": ["_start_test_spot"],
                "position": {"x": -24.1579723, "y": 1.481601, "z": -9.286173},
            }],
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )
        runtime.setup()

        waiting = runtime.begin_setup_validation(action_id="setup-shot-001")

        self.assertEqual(waiting["status"], "awaiting_red_defense_roll")
        self.assertEqual(waiting["attacker_guid"], "96fe20")
        self.assertEqual(waiting["target_guid"], "377732")
        self.assertEqual(waiting["attack_roll"], [5, 4, 2, 1])
        self.assertIn(
            (
                "move_object",
                "96fe20",
                {"x": -24.1579723, "y": 1.481601, "z": -9.286173},
            ),
            bridge.calls,
        )
        self.assertTrue(any(
            call[:3] == ("probe_line_of_sight", "96fe20", "377732")
            for call in bridge.calls
        ))
        self.assertIn(
            (
                "roll_dice",
                "ai",
                ("2831c0", "bde8ee", "87bb98", "967871"),
                "175503",
                "attack",
                "_dice_blue",
            ),
            bridge.calls,
        )
        self.assertFalse(any(call[0] == "observe_defense_roll" for call in bridge.calls))
        self.assertFalse(any(call[0] == "apply_damage" for call in bridge.calls))

        resolved = runtime.complete_setup_validation(
            acknowledged_by="Red",
            action_id="setup-shot-001-defense",
        )

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["defense_roll"], [4, 2, 1])
        self.assertEqual(resolved["damage"], 3)
        self.assertEqual(resolved["target_wounds"], 4)
        self.assertIn(("observe_defense_roll", "f1adc9", 3), bridge.calls)
        self.assertIn(("apply_damage", "377732", 3, 7), bridge.calls)

    def test_save_131_validation_uses_boltgun_critical_damage(self):
        bridge = FakeKillTeamBridge(
            save_131_native_objects(),
            rolls=[[6, 5, 2, 1]],
            defense_faces=[5, 2, 1],
            snap_points=[{
                "tags": ["_start_test_spot"],
                "position": {"x": -24.1579723, "y": 1.481601, "z": -9.286173},
            }],
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )
        runtime.setup()
        runtime.begin_setup_validation(action_id="critical-shot")

        result = runtime.complete_setup_validation(
            acknowledged_by="host",
            action_id="critical-defense",
        )

        self.assertEqual(result["critical_hits"], 1)
        self.assertEqual(result["normal_hits"], 1)
        self.assertEqual(result["unblocked_critical_hits"], 1)
        self.assertEqual(result["unblocked_normal_hits"], 0)
        self.assertEqual(result["damage"], 4)
        self.assertEqual(result["target_wounds"], 3)

    def test_setup_uses_compact_object_observation(self):
        bridge = FakeKillTeamBridge(fixture_objects())

        KillTeamRuntime(bridge).setup()

        self.assertEqual(bridge.list_calls, [{
            "max_results": 1000,
            "compact": True,
            "required_guids": ["96fe20"],
        }])

    def test_setup_discovers_ai_state_and_filters_hidden_opponents(self):
        runtime = KillTeamRuntime(FakeKillTeamBridge(fixture_objects()))

        result = runtime.setup()

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["ai_operatives"], ["plague-warrior-01"])
        self.assertEqual(result["visible_opponents"], ["target-01"])
        self.assertNotIn("hidden-01", runtime.observe()["operatives"])

    def test_setup_and_observe_expose_ai_model_identity_for_placement(self):
        runtime = KillTeamRuntime(FakeKillTeamBridge(fixture_objects()))

        setup = runtime.setup()
        observation = runtime.observe()

        self.assertEqual(setup["ai_models"][0]["operative_id"], "plague-warrior-01")
        self.assertEqual(setup["ai_models"][0]["guid"], "ai-1")
        self.assertEqual(observation["operatives"]["plague-warrior-01"]["guid"], "ai-1")
        self.assertEqual(observation["operatives"]["plague-warrior-01"]["name"], "plague-warrior-01")
        self.assertEqual(observation["operatives"]["plague-warrior-01"]["bounds"]["size"]["x"], 1)

    def test_test_deployment_moves_named_warrior_to_tagged_blue_zone_xz(self):
        objects = save_131_native_objects()
        model = next(item for item in objects if item["guid"] == "96fe20")
        model["guid"] = "aa11bb"
        bridge = FakeKillTeamBridge(objects)
        bridge.get_object = lambda _guid: self.fail(
            "deployment smoke test should verify the move_object response"
        )
        runtime = KillTeamRuntime(bridge)

        result = runtime.deploy_test_model()

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["guid"], "aa11bb")
        self.assertEqual(result["model_name"], "Plague Marine Warrior")
        self.assertEqual(result["target_guid"], "865d5c")
        self.assertEqual(result["target_tag"], "_deployment_zone_blue")
        self.assertLessEqual(result["distance_to_target"], 0.25)
        self.assertEqual(bridge.objects["aa11bb"]["position"], {
            "x": -18,
            "y": 1.0,
            "z": -8,
        })
        self.assertFalse(any(call[0] == "get_snap_points" for call in bridge.calls))
        self.assertEqual(bridge.list_calls, [{
            "max_results": 2,
            "compact": True,
            "query_names": ["Plague Marine Warrior"],
            "query_tags": ["_deployment_zone_blue"],
        }])

    def test_roster_request_returns_dedicated_container_contents(self):
        bridge = FakeKillTeamBridge(fixture_objects())
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        roster = runtime.get_roster()

        self.assertEqual(roster["container_guid"], "e5adb7")
        self.assertEqual(roster["items"][0]["name"], "Plague Marine Heavy Gunner")
        self.assertTrue(any(call == ("get_roster", "e5adb7") for call in bridge.calls))

    def test_observation_contains_resources_and_board_freshness(self):
        runtime = KillTeamRuntime(FakeKillTeamBridge(fixture_objects()))
        runtime.setup()

        observation = runtime.observe()

        self.assertEqual(observation["observation_id"], 1)
        self.assertEqual(observation["map_revision"], 0)
        self.assertEqual(observation["roller_guid"], "roller")
        self.assertEqual(observation["dice"]["ai"], ["die-a", "die-b", "die-c", "die-d"])
        self.assertEqual(observation["counters"]["cp"]["guid"], "cp")
        self.assertEqual(observation["counters"]["cp"]["value"], 2)
        self.assertFalse(observation["truncated"])

    def test_line_of_sight_probe_returns_physical_evidence(self):
        bridge = FakeKillTeamBridge(fixture_objects())
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        evidence = runtime.probe_line_of_sight("plague-warrior-01", "target-01")

        self.assertTrue(evidence["visible"])
        self.assertEqual(evidence["visible_rays"], 9)
        self.assertEqual(evidence["total_rays"], 9)
        self.assertEqual(evidence["observer_guid"], "ai-1")
        self.assertEqual(evidence["target_guid"], "96fe20")
        self.assertNotEqual(evidence["target_guid"], "-1")
        self.assertEqual(evidence["collider_warning"], "physics_colliders_only")
        self.assertIn(
            ("probe_line_of_sight", "ai-1", "96fe20", None, False),
            bridge.calls,
        )

    def test_stale_sentinel_guid_is_not_available_as_a_target(self):
        objects = fixture_objects()
        next(item for item in objects if item["guid"] == "96fe20")["guid"] = "-1"
        bridge = FakeKillTeamBridge(objects)
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        self.assertNotIn("target-01", runtime.observe()["operatives"])
        with self.assertRaisesRegex(KillTeamRuleError, "unknown operative"):
            runtime.probe_line_of_sight("plague-warrior-01", "target-01")
        self.assertFalse(any(call[0] == "probe_line_of_sight" for call in bridge.calls))

    def test_place_activate_and_shoot_resolves_physical_attack_and_damage(self):
        bridge = FakeKillTeamBridge(
            fixture_objects(),
            rolls=[[5, 4, 2, 1], [2, 1, 4]],
        )
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        placement = runtime.place_operative(
            "plague-warrior-01",
            [{"x": 1.0, "y": 1.0, "z": 0.0}, {"x": 2.0, "y": 1.0, "z": 0.0}],
        )
        runtime.activate_operative("plague-warrior-01")
        result = runtime.shoot("plague-warrior-01", "target-01", "boltgun")

        self.assertEqual(placement["status"], "verified")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["attack_roll"], [5, 4, 2, 1])
        self.assertEqual(result["defense_roll"], [2, 1, 4])
        self.assertEqual(result["unblocked_hits"], 1)
        self.assertEqual(result["damage"], 3)
        self.assertTrue(result["los_evidence"]["visible"])
        self.assertEqual(runtime.observe()["operatives"]["target-01"]["wounds"], 7)
        self.assertEqual(bridge.objects["ai-1"]["position"]["x"], 2.0)

    def test_hidden_target_cannot_be_selected(self):
        runtime = KillTeamRuntime(FakeKillTeamBridge(fixture_objects(), rolls=[]))
        runtime.setup()
        runtime.activate_operative("plague-warrior-01")

        with self.assertRaisesRegex(KillTeamRuleError, "not visible"):
            runtime.shoot("plague-warrior-01", "hidden-01", "boltgun")

    def test_blocked_line_of_sight_stops_before_rolling_dice(self):
        objects = fixture_objects()
        objects.append({
            "guid": "wall-1",
            "tags": tag("entity=terrain", "blocks_los=true"),
            "position": {"x": 2.5, "y": 1.0, "z": 0.0},
            "bounds": {"center": {"x": 2.5, "y": 1.0, "z": 0.0}, "size": {"x": 1, "y": 2, "z": 2}},
        })
        bridge = FakeKillTeamBridge(objects, rolls=[])
        runtime = KillTeamRuntime(bridge)
        runtime.setup()
        runtime.activate_operative("plague-warrior-01")

        with self.assertRaisesRegex(KillTeamRuleError, "line of sight"):
            runtime.shoot("plague-warrior-01", "target-01", "boltgun")

        self.assertFalse(any(call[0] == "roll_dice" for call in bridge.calls))
        self.assertTrue(any(call[0] == "probe_line_of_sight" for call in bridge.calls))

    def test_profile_description_parser_reads_formatted_save_profile(self):
        profile = parse_profile_description(
            """[D36B3E][[84E680]M[-] [ffffff]5\"[-]] [[84E680]APL[-] [ffffff]3[-]] [[84E680]SV[-] [ffffff]3+[-]] [[84E680]W[-] [ffffff]14[-]][-]\n"
            "[1E87FF]R[-] Boltgun\n[84E680]ATK[-] 4 [84E680]HIT[-] 3+[-] [84E680]DMG[-] 3/4"""
        )

        self.assertEqual(profile["move"], 5)
        self.assertEqual(profile["apl"], 3)
        self.assertEqual(profile["wounds"], 14)
        self.assertEqual(profile["weapons"]["boltgun"]["attacks"], 4)

    def test_profile_parser_accepts_save_131_long_stat_labels(self):
        profile = parse_profile_description(
            """[D36B3E][[84E680]APL[-] [ffffff]2[-]] [[84E680]MOVE[-] [ffffff]6\"[-]]
[[84E680]SAVE[-] [ffffff]4+[-]] [[84E680]WOUNDS[-] [ffffff]7[-]][-]
[1E87FF]R[-] Autopistol
[84E680]ATK[-] 4 [84E680]HIT[-] 4+ [84E680]DMG[-] 2/3
[84E680]WR[-]: Rng [DA1A18](8\")[-]"""
        )

        self.assertEqual(profile["move"], 6)
        self.assertEqual(profile["save"], 4)
        self.assertEqual(profile["wounds"], 7)
        self.assertEqual(profile["weapons"]["autopistol"]["range"], 8)

    def test_setup_fails_when_required_dice_or_roller_are_missing(self):
        objects = [item for item in fixture_objects() if item["guid"] not in {"die-d", "roller"}]

        with self.assertRaisesRegex(KillTeamSetupError, "roller"):
            KillTeamRuntime(FakeKillTeamBridge(objects)).setup()

    def test_uncertain_action_id_cannot_be_retried(self):
        class ReadbackFailureBridge(FakeKillTeamBridge):
            def get_object(self, guid):
                if guid == "ai-1" and any(call[0] == "move_object" for call in self.calls):
                    raise OSError("simulated readback loss")
                return super().get_object(guid)

        bridge = ReadbackFailureBridge(fixture_objects())
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        with self.assertRaises(KillTeamUncertainCommit):
            runtime.place_operative(
                "plague-warrior-01",
                [{"x": 1.0, "y": 1.0, "z": 0.0}],
                action_id="move-001",
            )
        with self.assertRaisesRegex(KillTeamUncertainCommit, "read-only recovery"):
            runtime.place_operative(
                "plague-warrior-01",
                [{"x": 1.0, "y": 1.0, "z": 0.0}],
                action_id="move-001",
            )


if __name__ == "__main__":
    unittest.main()
