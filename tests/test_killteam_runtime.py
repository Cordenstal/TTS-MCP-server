import copy
import copy
import unittest

from tts_mcp.runtime.killteam_runtime import (
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
    def __init__(
        self,
        objects,
        rolls=None,
        snap_points=None,
        defense_faces=None,
        zone_snap_points=None,
        containers=None,
        setup_roster_cards=None,
    ):
        self.objects = {item["guid"]: copy.deepcopy(item) for item in objects}
        self.wounds = {
            item["guid"]: int(
                item.get("script_wounds", (item.get("profile") or {}).get("wounds", 0))
            )
            for item in objects
        }
        self.containers = {
            guid: {
                "guid": guid,
                "name": payload.get("name", guid),
                "items": [copy.deepcopy(item) for item in payload.get("items", [])],
            }
            for guid, payload in (containers or {}).items()
        }
        self.rolls = list(rolls or [])
        self.snap_points = copy.deepcopy(snap_points or [])
        self.zone_snap_points = copy.deepcopy(zone_snap_points or {})
        self.setup_roster_cards = copy.deepcopy(setup_roster_cards or {})
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
        bounds = self.objects[guid].get("bounds") or {}
        if isinstance(bounds.get("center"), dict):
            bounds["center"] = {
                "x": float(position["x"]),
                "y": float(position["y"]),
                "z": float(position["z"]),
            }
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

    def set_object_lock(self, guid, locked):
        self.calls.append(("set_object_lock", guid, locked))
        self.objects[guid]["locked"] = bool(locked)
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
        if container_guid in self.containers:
            return self.inspect_container(container_guid)
        return copy.deepcopy(self.roster)

    def inspect_container(self, guid):
        self.calls.append(("inspect_container", guid))
        container = self.containers[guid]
        items = []
        for index, item in enumerate(container["items"]):
            items.append({
                "guid": item["guid"],
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "index": item.get("index", index),
                "tags": copy.deepcopy(item.get("tags", [])),
            })
        return {
            "container_guid": guid,
            "container": {"guid": guid, "name": container["name"]},
            "count": len(items),
            "total": len(items),
            "truncated": False,
            "items": items,
        }

    def get_zone_objects(self, guid):
        self.calls.append(("get_zone_objects", guid))
        zone = self.objects[guid]
        bounds = zone.get("bounds") or {}
        center = bounds.get("center") or zone.get("position") or {}
        size = bounds.get("size") or {}
        min_x = float(center.get("x", 0)) - abs(float(size.get("x", 0))) / 2
        max_x = float(center.get("x", 0)) + abs(float(size.get("x", 0))) / 2
        min_z = float(center.get("z", 0)) - abs(float(size.get("z", 0))) / 2
        max_z = float(center.get("z", 0)) + abs(float(size.get("z", 0))) / 2
        occupants = []
        for obj in self.objects.values():
            if obj["guid"] == guid:
                continue
            position = obj.get("position") or {}
            try:
                x = float(position["x"])
                z = float(position["z"])
            except (KeyError, TypeError, ValueError):
                continue
            if min_x <= x <= max_x and min_z <= z <= max_z:
                occupants.append(copy.deepcopy(obj))
        return {
            "zone_guid": guid,
            "zone": copy.deepcopy(zone),
            "count": len(occupants),
            "objects": occupants,
        }

    def get_setup_roster_cards(self, zone_guid):
        self.calls.append(("get_setup_roster_cards", zone_guid))
        cards = self.setup_roster_cards.get(zone_guid)
        if cards is None:
            cards = self.get_zone_objects(zone_guid)["objects"]
        return {
            "zone_guid": zone_guid,
            "order_source": "layout_zone.getObjects",
            "count": len(cards),
            "objects": copy.deepcopy(cards),
        }

    def take_from_container(
        self,
        container_guid,
        *,
        item_guid=None,
        index=None,
        position=None,
        flip=False,
        smooth=True,
    ):
        self.calls.append((
            "take_from_container",
            container_guid,
            item_guid,
            index,
            copy.deepcopy(position),
            flip,
            smooth,
        ))
        container = self.containers[container_guid]
        if item_guid:
            wanted = str(item_guid).lower()
            item_index = next(
                (
                    current_index
                    for current_index, item in enumerate(container["items"])
                    if str(item["guid"]).lower() == wanted
                ),
                None,
            )
            if item_index is None:
                raise AssertionError(f"container item {item_guid} is missing")
        else:
            item_index = int(index)
        item = container["items"].pop(item_index)
        obj = copy.deepcopy(item.get("object") or {
            "guid": item["guid"],
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "type": item.get("type", "Card"),
            "tags": copy.deepcopy(item.get("tags", [])),
            "position": {"x": 0.0, "y": 1.0, "z": 0.0},
            "bounds": {
                "center": {"x": 0.0, "y": 1.0, "z": 0.0},
                "size": {"x": 1.0, "y": 0.2, "z": 1.0},
            },
        })
        if position is not None:
            obj["position"] = dict(position)
            bounds = obj.get("bounds") or {}
            if isinstance(bounds.get("center"), dict):
                bounds["center"] = dict(position)
        self.objects[obj["guid"]] = obj
        return {
            "container_guid": container_guid,
            "object": copy.deepcopy(obj),
        }

    def put_object_into_container(self, container_guid, object_guid, index=None):
        self.calls.append(("put_object_into_container", container_guid, object_guid, index))
        obj = copy.deepcopy(self.objects.pop(object_guid))
        container = self.containers[container_guid]
        entry = {
            "guid": obj["guid"],
            "name": obj.get("name", ""),
            "description": obj.get("description", ""),
            "index": len(container["items"]) if index is None else int(index),
            "tags": copy.deepcopy(obj.get("tags", [])),
            "object": obj,
        }
        if index is None:
            container["items"].append(entry)
        else:
            container["items"].insert(int(index), entry)
        return {
            "container_guid": container_guid,
            "object_guid": object_guid,
            "container": {"guid": container_guid, "name": container["name"]},
        }


def tag(*entries):
    return [f"tts_mcp:{entry}" for entry in entries]


def setup_zone(guid, *, name, entity, side_id, x, z, size_x=6.0, size_z=6.0):
    return {
        "guid": guid,
        "name": name,
        "type": "LayoutZone",
        "tags": tag(f"entity={entity}", f"side_id={side_id}"),
        "position": {"x": x, "y": 1.0, "z": z},
        "bounds": {
            "center": {"x": x, "y": 1.0, "z": z},
            "size": {"x": size_x, "y": 2.0, "z": size_z},
        },
    }


def setup_container(guid, *, name, entity, side_id):
    return {
        "guid": guid,
        "name": name,
        "type": "Bag",
        "tags": tag(f"entity={entity}", f"side_id={side_id}"),
        "position": {"x": 0.0, "y": 1.0, "z": 0.0},
        "bounds": {
            "center": {"x": 0.0, "y": 1.0, "z": 0.0},
            "size": {"x": 2.0, "y": 2.0, "z": 2.0},
        },
    }


def roster_card_item(guid, *, side_id, faction_id, operative_type_id, instance_id, role="operative"):
    operative_id = f"{operative_type_id}#{instance_id}"
    tags = tag(
        "entity=roster_card",
        f"side_id={side_id}",
        f"faction_id={faction_id}",
        f"operative_type_id={operative_type_id}",
        f"instance_id={instance_id}",
        f"operative_id={operative_id}",
        f"role={role}",
    ) + ["_roster_card"]
    return {
        "guid": guid,
        "name": operative_id,
        "description": "",
        "index": 0,
        "tags": tags,
        "object": {
            "guid": guid,
            "name": operative_id,
            "description": "",
            "type": "Card",
            "tags": tags,
            "position": {"x": 0.0, "y": 1.0, "z": 0.0},
            "bounds": {
                "center": {"x": 0.0, "y": 1.0, "z": 0.0},
                "size": {"x": 1.0, "y": 0.2, "z": 1.4},
            },
        },
    }


def roster_model_item(guid, *, side_id, faction_id, operative_type_id, instance_id, profile_id="plague_warrior"):
    operative_id = f"{operative_type_id}#{instance_id}"
    tags = tag(
        "entity=operative",
        f"side_id={side_id}",
        f"team={side_id}",
        f"faction_id={faction_id}",
        f"operative_type_id={operative_type_id}",
        f"instance_id={instance_id}",
        f"operative_id={operative_id}",
        f"profile={profile_id}",
        "visibility=public",
    )
    return {
        "guid": guid,
        "name": operative_id,
        "description": "",
        "index": 0,
        "tags": tags,
        "object": {
            "guid": guid,
            "name": operative_id,
            "description": "",
            "type": "Figurine",
            "tags": tags,
            "position": {"x": 0.0, "y": 1.0, "z": 0.0},
            "bounds": {
                "center": {"x": 0.0, "y": 1.0, "z": 0.0},
                "size": {"x": 1.0, "y": 2.0, "z": 1.0},
            },
            "profile": {
                "move": 5,
                "apl": 3,
                "wounds": 14,
                "save": 3,
                "weapons": {
                    "boltgun": {"attacks": 4, "hit": 3, "damage": 3, "range": 8}
                },
            },
        },
    }


def live_card(item, *, x, z):
    obj = copy.deepcopy(item["object"])
    obj["position"] = {"x": x, "y": 1.0, "z": z}
    obj["bounds"]["center"] = {"x": x, "y": 1.0, "z": z}
    return obj


def setup_fixture_with_rosters():
    objects = [
        {"guid": "die-ai", "tags": tag("entity=die", "team=ai"), "position": {"x": -30, "y": 1, "z": 0}},
        {"guid": "die-op", "tags": tag("entity=die", "team=opponent"), "position": {"x": 30, "y": 1, "z": 0}},
        {"guid": "roller", "tags": tag("entity=dice_roller"), "position": {"x": 0, "y": 1, "z": 0}},
        {"guid": "cp", "tags": tag("entity=counter", "counter=cp", "team=ai"), "counter_value": 2},
        {"guid": "vp", "tags": tag("entity=counter", "counter=vp", "team=ai"), "counter_value": 0},
        {"guid": "calibration", "tags": tag("entity=calibration", "axis=xz", "units_per_inch=1")},
        setup_container("deck-ai", name="Faction Decks AI", entity="faction_decks", side_id="ai")
        | {"tags": tag("entity=faction_decks", "side_id=ai") + ["_Faction_Decks"]},
        setup_container("deck-op", name="Faction Decks Opponent", entity="faction_decks", side_id="opponent")
        | {"tags": tag("entity=faction_decks", "side_id=opponent") + ["_Faction_Decks"]},
        setup_container("roster-ai", name="Roster AI", entity="roster", side_id="ai")
        | {"tags": tag("entity=roster", "side_id=ai") + ["_roster"]},
        setup_container("roster-op", name="Roster Opponent", entity="roster", side_id="opponent")
        | {"tags": tag("entity=roster", "side_id=opponent") + ["_roster"]},
        setup_zone("roster-list-ai", name="Roster List AI", entity="roster_list_zone", side_id="ai", x=-18, z=-12),
        setup_zone("roster-list-op", name="Roster List Opponent", entity="roster_list_zone", side_id="opponent", x=18, z=-12),
        setup_zone("deployed-ai", name="Deployed Zone AI", entity="deployed_zone", side_id="ai", x=-18, z=-4),
        setup_zone("deployed-op", name="Deployed Zone Opponent", entity="deployed_zone", side_id="opponent", x=18, z=-4),
        setup_zone("drop-ai", name="Deployment AI", entity="deployment", side_id="ai", x=-18, z=6, size_x=10, size_z=8),
        setup_zone("drop-op", name="Deployment Opponent", entity="deployment", side_id="opponent", x=18, z=6, size_x=10, size_z=8),
    ]
    ai_cards = [
        roster_card_item("card-ai-chosen-1", side_id="ai", faction_id="legionary", operative_type_id="chosen", instance_id="1", role="leader"),
        roster_card_item("card-ai-warrior-1", side_id="ai", faction_id="legionary", operative_type_id="warrior", instance_id="1"),
        roster_card_item("card-ai-warrior-2", side_id="ai", faction_id="legionary", operative_type_id="warrior", instance_id="2"),
        roster_card_item("card-ai-butcher-1", side_id="ai", faction_id="legionary", operative_type_id="butcher", instance_id="1"),
        roster_card_item("card-ai-balefire-1", side_id="ai", faction_id="legionary", operative_type_id="balefire_acolyte", instance_id="1"),
        roster_card_item("card-ai-icon-1", side_id="ai", faction_id="legionary", operative_type_id="icon_bearer", instance_id="1"),
        roster_card_item("card-ai-butcher-2", side_id="ai", faction_id="legionary", operative_type_id="butcher", instance_id="2"),
    ]
    opponent_cards = [
        roster_card_item("card-op-chosen-1", side_id="opponent", faction_id="legionary", operative_type_id="chosen", instance_id="1", role="leader"),
        roster_card_item("card-op-warrior-1", side_id="opponent", faction_id="legionary", operative_type_id="warrior", instance_id="1"),
        roster_card_item("card-op-warrior-2", side_id="opponent", faction_id="legionary", operative_type_id="warrior", instance_id="2"),
        roster_card_item("card-op-butcher-1", side_id="opponent", faction_id="legionary", operative_type_id="butcher", instance_id="1"),
        roster_card_item("card-op-balefire-1", side_id="opponent", faction_id="legionary", operative_type_id="balefire_acolyte", instance_id="1"),
        roster_card_item("card-op-icon-1", side_id="opponent", faction_id="legionary", operative_type_id="icon_bearer", instance_id="1"),
    ]
    containers = {
        "deck-ai": {"name": "Faction Decks AI", "items": ai_cards},
        "deck-op": {"name": "Faction Decks Opponent", "items": opponent_cards},
        "roster-ai": {
            "name": "Roster AI",
            "items": [
                roster_model_item("model-ai-chosen-1", side_id="ai", faction_id="legionary", operative_type_id="chosen", instance_id="1"),
                roster_model_item("model-ai-warrior-1", side_id="ai", faction_id="legionary", operative_type_id="warrior", instance_id="1"),
                roster_model_item("model-ai-warrior-2", side_id="ai", faction_id="legionary", operative_type_id="warrior", instance_id="2"),
                roster_model_item("model-ai-butcher-1", side_id="ai", faction_id="legionary", operative_type_id="butcher", instance_id="1"),
                roster_model_item("model-ai-balefire-1", side_id="ai", faction_id="legionary", operative_type_id="balefire_acolyte", instance_id="1"),
                roster_model_item("model-ai-icon-1", side_id="ai", faction_id="legionary", operative_type_id="icon_bearer", instance_id="1"),
            ],
        },
        "roster-op": {
            "name": "Roster Opponent",
            "items": [
                roster_model_item("model-op-chosen-1", side_id="opponent", faction_id="legionary", operative_type_id="chosen", instance_id="1"),
                roster_model_item("model-op-warrior-1", side_id="opponent", faction_id="legionary", operative_type_id="warrior", instance_id="1"),
                roster_model_item("model-op-warrior-2", side_id="opponent", faction_id="legionary", operative_type_id="warrior", instance_id="2"),
                roster_model_item("model-op-butcher-1", side_id="opponent", faction_id="legionary", operative_type_id="butcher", instance_id="1"),
                roster_model_item("model-op-balefire-1", side_id="opponent", faction_id="legionary", operative_type_id="balefire_acolyte", instance_id="1"),
                roster_model_item("model-op-icon-1", side_id="opponent", faction_id="legionary", operative_type_id="icon_bearer", instance_id="1"),
            ],
        },
    }
    return objects, containers


def operative(guid, *, team, operative_id, profile, x, z, visible=True):
    return {
        "guid": guid,
        "name": operative_id,
        "description": "",
        "type": "Figurine",
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


def mission_objective(guid, *, name, x, z, size=1.0):
    return {
        "guid": guid,
        "name": name,
        "type": "LayoutZone",
        "tags": tag("entity=objective"),
        "position": {"x": x, "y": 1.0, "z": z},
        "bounds": {
            "center": {"x": x, "y": 1.0, "z": z},
            "size": {"x": size, "y": 1.0, "z": size},
        },
    }


def mission_terrain(guid, *, name, x, z, size_x, size_z):
    return {
        "guid": guid,
        "name": name,
        "type": "LayoutZone",
        "tags": tag("entity=terrain", "blocks_los=true"),
        "position": {"x": x, "y": 1.0, "z": z},
        "bounds": {
            "center": {"x": x, "y": 1.0, "z": z},
            "size": {"x": size_x, "y": 2.0, "z": size_z},
        },
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


def native_generic_setup_objects():
    return [
        {
            "guid": "die-blue",
            "name": "Blue D6",
            "type": "Die",
            "tags": ["_dice_blue", "Blue"],
            "position": {"x": -30.0, "y": 1.0, "z": 0.0},
        },
        {
            "guid": "die-red",
            "name": "Red D6",
            "type": "Die",
            "tags": ["_dice_red", "Red"],
            "position": {"x": 30.0, "y": 1.0, "z": 0.0},
        },
        {
            "guid": "roller-blue",
            "name": "Blue Dice Roller",
            "type": "DiceRoller",
            "tags": ["_blue_dice_roller", "Blue"],
            "position": {"x": 0.0, "y": 1.0, "z": 0.0},
        },
        {
            "guid": "cp",
            "name": "CP",
            "tags": ["counter", "Blue"],
            "counter_value": 2,
        },
        {
            "guid": "vp",
            "name": "VP",
            "tags": ["counter", "Blue"],
            "counter_value": 0,
        },
        {
            "guid": "calibration",
            "name": "Calibration",
            "tags": ["calibration"],
            "position": {"x": 0.0, "y": 1.0, "z": 0.0},
        },
        setup_container("deck-ai", name="Faction Decks Blue", entity="faction_decks", side_id="blue")
        | {"tags": ["_faction_decks", "Blue"]},
        setup_container("deck-op", name="Faction Decks Red", entity="faction_decks", side_id="red")
        | {"tags": ["_faction_decks", "Red"]},
        setup_container("roster-ai", name="Roster Blue", entity="roster", side_id="blue")
        | {"tags": ["_roster", "Blue"]},
        setup_container("roster-op", name="Roster Red", entity="roster", side_id="red")
        | {"tags": ["_roster", "Red"]},
        setup_zone("roster-list-ai", name="Roster List Blue", entity="roster_list_zone", side_id="blue", x=-18, z=-12)
        | {"tags": ["Roster List", "Blue"]},
        setup_zone("roster-list-op", name="Roster List Red", entity="roster_list_zone", side_id="red", x=18, z=-12)
        | {"tags": ["Roster List", "Red"]},
        setup_zone("deployed-ai", name="Deployed Zone Blue", entity="deployed_zone", side_id="blue", x=-18, z=-4)
        | {"tags": ["Deployed Zone", "Blue"]},
        setup_zone("deployed-op", name="Deployed Zone Red", entity="deployed_zone", side_id="red", x=18, z=-4)
        | {"tags": ["Deployed Zone", "Red"]},
        setup_zone("deploy-ai", name="Blue Deployment", entity="deployment", side_id="blue", x=-18, z=6, size_x=10, size_z=8)
        | {"tags": ["_deployment_zone_blue", "Blue"]},
        setup_zone("deploy-op", name="Red Deployment", entity="deployment", side_id="red", x=18, z=6, size_x=10, size_z=8)
        | {"tags": ["_deployment_zone_red", "Red"]},
    ]


def save_131_roster_card(guid, name, index=1):
    return {
        "guid": guid,
        "name": name,
        "type": "Card",
        "tags": ["Roster Card"],
        "position": {"x": -18.0 + index, "y": 1.0, "z": -18.0},
        "bounds": {
            "center": {"x": -18.0 + index, "y": 1.0, "z": -18.0},
            "size": {"x": 1.0, "y": 0.2, "z": 1.4},
        },
        "layout_index": index,
    }


class KillTeamRuntimeTests(unittest.TestCase):
    def _runtime_with_roster_setup(self):
        objects, containers = setup_fixture_with_rosters()
        bridge = FakeKillTeamBridge(objects, containers=containers, rolls=[[6], [2]])
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(
                ai_team="ai",
                ai_dice_count=1,
                opponent_dice_count=1,
            ),
        )
        return runtime, bridge

    def test_setup_discovers_side_scoped_roster_objects_and_waits_for_initiative(self):
        runtime, _bridge = self._runtime_with_roster_setup()

        result = runtime.setup()
        observation = runtime.observe()

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["setup"]["mode"], "roster_cards")
        self.assertEqual(result["setup"]["stage"], "roster_selection")
        self.assertEqual(result["setup"]["initiative_side"], "ai")
        self.assertEqual(sorted(result["setup"]["sides"].keys()), ["ai", "opponent"])
        self.assertEqual(result["setup"]["sides"]["ai"]["roster_list_zone_guid"], "roster-list-ai")
        self.assertEqual(observation["setup"]["stage"], "roster_selection")
        self.assertEqual(observation["setup"]["current_side"], "ai")
        self.assertEqual(observation["operatives"], {})

    def test_setup_defaults_to_ai_first_without_rolling_initiative(self):
        runtime, bridge = self._runtime_with_roster_setup()
        runtime.setup()

        observation = runtime.observe()

        self.assertEqual(observation["setup"]["stage"], "roster_selection")
        self.assertEqual(observation["setup"]["initiative_side"], "ai")
        self.assertEqual(observation["setup"]["current_side"], "ai")
        with self.assertRaisesRegex(KillTeamRuleError, "initiative has already been determined"):
            runtime.roll_initiative()

    def test_generic_setup_queries_scene_tags_without_placeholder_target_guid(self):
        objects, containers = setup_fixture_with_rosters()
        bridge = FakeKillTeamBridge(objects, containers=containers, rolls=[[6], [2]])
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(
                ai_team="ai",
                ai_dice_count=1,
                opponent_dice_count=1,
            ),
        )

        result = runtime.setup()

        self.assertEqual(result["status"], "ready")
        self.assertTrue(bridge.list_calls)
        first_call = bridge.list_calls[0]
        self.assertEqual(first_call["required_guids"], [])
        from tts_mcp.runtime.killteam_runtime import _GENERIC_SETUP_QUERY_TAGS

        self.assertEqual(first_call["query_tags"], list(_GENERIC_SETUP_QUERY_TAGS))

    def test_auto_setup_starts_model_deployment_and_switches_after_floor_batch(self):
        runtime, bridge = self._runtime_with_roster_setup()

        started = runtime.setup(auto_start=True)
        setup = started["setup"]

        self.assertEqual(setup["mode"], "model_deployment")
        self.assertEqual(setup["stage"], "deployment")
        self.assertEqual(setup["current_side"], "ai")
        self.assertEqual(setup["current_batch_target"], 2)
        self.assertEqual(setup["next_action"]["type"], "deploy_ai_operative")
        self.assertEqual(setup["next_action"]["model_guid"], "model-ai-chosen-1")

        runtime.start_setup_deployment("chosen#1")
        runtime.deploy_setup_operative(
            "model-ai-chosen-1",
            setup["next_action"]["recommended_position"],
        )
        runtime.start_setup_deployment("balefire_acolyte#1")
        second = runtime.deploy_setup_operative(
            "model-ai-balefire-1",
            runtime.observe()["setup"]["next_action"]["recommended_position"],
        )

        self.assertEqual(second["status"], "deployed")
        self.assertEqual(runtime.observe()["setup"]["current_side"], "opponent")
        self.assertEqual(runtime.observe()["setup"]["current_batch_target"], 2)
        self.assertTrue(any(call[0] == "take_from_container" for call in bridge.calls))

        bridge.take_from_container(
            "roster-op",
            item_guid="model-op-chosen-1",
            position={"x": 16.0, "y": 1.0, "z": 6.0},
            smooth=False,
        )
        bridge.take_from_container(
            "roster-op",
            item_guid="model-op-warrior-1",
            position={"x": 18.0, "y": 1.0, "z": 6.0},
            smooth=False,
        )
        human_batch = runtime.reconcile_setup_step("opponent")

        self.assertEqual(human_batch["deployed_count"], 2)
        self.assertEqual(runtime.observe()["setup"]["current_side"], "ai")

        with self.assertRaisesRegex(KillTeamRuleError, "AI models must be deployed"):
            runtime.reconcile_setup_step("ai")

    def test_setup_exposes_ai_selection_and_deployment_order(self):
        runtime, _bridge = self._runtime_with_roster_setup()
        runtime.setup()

        observation = runtime.observe()
        ai_plan = observation["setup"]["ai_plan"]

        self.assertEqual(
            [entry["operative_id"] for entry in ai_plan["selection_order"]],
            [
                "chosen#1",
                "balefire_acolyte#1",
                "icon_bearer#1",
                "butcher#1",
                "warrior#1",
                "warrior#2",
            ],
        )
        self.assertEqual(
            [entry["card_guid"] for entry in ai_plan["selection_order"]],
            [
                "card-ai-chosen-1",
                "card-ai-balefire-1",
                "card-ai-icon-1",
                "card-ai-butcher-1",
                "card-ai-warrior-1",
                "card-ai-warrior-2",
            ],
        )
        self.assertEqual(
            [entry["model_guid"] for entry in ai_plan["deployment_order"]],
            [
                "model-ai-chosen-1",
                "model-ai-balefire-1",
                "model-ai-icon-1",
                "model-ai-butcher-1",
                "model-ai-warrior-1",
                "model-ai-warrior-2",
            ],
        )
        self.assertEqual(ai_plan["next_selection"]["card_guid"], "card-ai-chosen-1")
        self.assertEqual(ai_plan["next_deployment"]["model_guid"], "model-ai-chosen-1")

    def test_setup_prefers_safe_objective_access_in_tactical_deployment(self):
        objects, containers = setup_fixture_with_rosters()
        objects.append(mission_objective("objective-1", name="Primary Objective", x=-14.0, z=9.0, size=1.0))
        bridge = FakeKillTeamBridge(objects, containers=containers, rolls=[[6], [2]])
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(
                ai_team="ai",
                ai_dice_count=1,
                opponent_dice_count=1,
            ),
        )

        runtime.setup()
        for contained_guid in (
            "card-ai-chosen-1",
            "card-ai-warrior-1",
            "card-ai-warrior-2",
            "card-ai-butcher-1",
            "card-ai-balefire-1",
            "card-ai-icon-1",
        ):
            runtime.select_roster_card(contained_guid)
        for index, contained_guid in enumerate((
            "card-op-chosen-1",
            "card-op-warrior-1",
            "card-op-warrior-2",
            "card-op-butcher-1",
            "card-op-balefire-1",
            "card-op-icon-1",
        )):
            bridge.objects[contained_guid] = live_card(
                next(item for item in bridge.containers["deck-op"]["items"] if item["guid"] == contained_guid),
                x=18.0 + (index % 3),
                z=-12.0 + (index // 3),
            )
            bridge.containers["deck-op"]["items"] = [
                item for item in bridge.containers["deck-op"]["items"] if item["guid"] != contained_guid
            ]

        locked = runtime.lock_rosters()
        recommended = locked["setup"]["ai_plan"]["next_deployment"]["recommended_position"]

        self.assertIn("most cover", locked["setup"]["ai_plan"]["policy"])
        self.assertIsNotNone(recommended)
        self.assertGreater(recommended["x"], -17.5)
        self.assertGreater(recommended["z"], 7.0)

    def test_roll_initiative_is_not_needed_for_ai_first_setup(self):
        objects, containers = setup_fixture_with_rosters()
        bridge = FakeKillTeamBridge(objects, containers=containers, rolls=[[4], [4]])
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(ai_team="ai", ai_dice_count=1, opponent_dice_count=1),
        )
        runtime.setup()

        self.assertEqual(runtime.observe()["setup"]["initiative_side"], "ai")
        with self.assertRaisesRegex(KillTeamRuleError, "initiative has already been determined"):
            runtime.roll_initiative()

    def test_select_roster_card_places_ai_card_and_rejects_illegal_duplicate(self):
        runtime, bridge = self._runtime_with_roster_setup()
        runtime.setup()

        first = runtime.select_roster_card("card-ai-chosen-1")
        runtime.select_roster_card("card-ai-butcher-1")

        self.assertEqual(first["status"], "selected")
        self.assertEqual(first["operative_id"], "chosen#1")
        self.assertIn("card-ai-chosen-1", bridge.objects)

        with self.assertRaisesRegex(KillTeamRuleError, "duplicate limit"):
            runtime.select_roster_card("card-ai-butcher-2")

    def test_lock_rosters_validates_lists_and_starts_initiative_deployment(self):
        runtime, bridge = self._runtime_with_roster_setup()
        runtime.setup()
        for contained_guid in (
            "card-ai-chosen-1",
            "card-ai-warrior-1",
            "card-ai-warrior-2",
            "card-ai-butcher-1",
            "card-ai-balefire-1",
            "card-ai-icon-1",
        ):
            runtime.select_roster_card(contained_guid)

        for index, contained_guid in enumerate((
            "card-op-chosen-1",
            "card-op-warrior-1",
            "card-op-warrior-2",
            "card-op-butcher-1",
            "card-op-balefire-1",
            "card-op-icon-1",
        )):
            bridge.objects[contained_guid] = live_card(
                next(item for item in bridge.containers["deck-op"]["items"] if item["guid"] == contained_guid),
                x=18.0 + (index % 3),
                z=-12.0 + (index // 3),
            )
            bridge.containers["deck-op"]["items"] = [
                item for item in bridge.containers["deck-op"]["items"] if item["guid"] != contained_guid
            ]

        locked = runtime.lock_rosters()
        observation = runtime.observe()

        self.assertEqual(locked["status"], "locked")
        self.assertEqual(locked["setup"]["stage"], "deployment")
        self.assertEqual(locked["setup"]["current_side"], "ai")
        self.assertEqual(locked["setup"]["current_batch_target"], 2)
        self.assertEqual(
            locked["setup"]["ai_plan"]["next_deployment"]["model_guid"],
            "model-ai-chosen-1",
        )
        recommended = locked["setup"]["ai_plan"]["next_deployment"]["recommended_position"]
        self.assertIsNotNone(recommended)
        self.assertGreaterEqual(recommended["x"], -23.0)
        self.assertLessEqual(recommended["x"], -13.0)
        self.assertGreaterEqual(recommended["z"], 2.0)
        self.assertLessEqual(recommended["z"], 10.0)
        self.assertEqual(observation["setup"]["sides"]["ai"]["selected_count"], 6)
        self.assertEqual(observation["setup"]["sides"]["opponent"]["selected_count"], 6)

    def test_deploy_setup_operative_advances_batch_and_switches_side(self):
        runtime, bridge = self._runtime_with_roster_setup()
        runtime.setup()
        for contained_guid in (
            "card-ai-chosen-1",
            "card-ai-warrior-1",
            "card-ai-warrior-2",
            "card-ai-butcher-1",
            "card-ai-balefire-1",
            "card-ai-icon-1",
        ):
            runtime.select_roster_card(contained_guid)
        for index, contained_guid in enumerate((
            "card-op-chosen-1",
            "card-op-warrior-1",
            "card-op-warrior-2",
            "card-op-butcher-1",
            "card-op-balefire-1",
            "card-op-icon-1",
        )):
            bridge.objects[contained_guid] = live_card(
                next(item for item in bridge.containers["deck-op"]["items"] if item["guid"] == contained_guid),
                x=18.0 + (index % 3),
                z=-12.0 + (index // 3),
            )
            bridge.containers["deck-op"]["items"] = [
                item for item in bridge.containers["deck-op"]["items"] if item["guid"] != contained_guid
            ]
        runtime.lock_rosters()

        runtime.start_setup_deployment("chosen#1")
        first = runtime.deploy_setup_operative("model-ai-chosen-1", {"x": -20.0, "y": 1.0, "z": 6.0})
        runtime.start_setup_deployment("warrior#1")
        second = runtime.deploy_setup_operative("model-ai-warrior-1", {"x": -17.5, "y": 1.0, "z": 6.0})
        observation = runtime.observe()

        self.assertEqual(first["status"], "deployed")
        self.assertEqual(first["guid"], "model-ai-chosen-1")
        self.assertEqual(first["model_guid"], "model-ai-chosen-1")
        self.assertEqual(second["status"], "deployed")
        self.assertEqual(second["guid"], "model-ai-warrior-1")
        self.assertEqual(second["model_guid"], "model-ai-warrior-1")
        self.assertEqual(observation["operatives"]["ai:chosen#1"]["order"], "conceal")
        self.assertEqual(observation["operatives"]["ai:warrior#1"]["order"], "conceal")
        self.assertEqual(observation["setup"]["current_side"], "opponent")
        self.assertEqual(observation["setup"]["current_batch_target"], 2)
        self.assertEqual(observation["setup"]["current_batch_progress"], 0)

    def test_reconcile_setup_step_validates_human_side_one_operative_at_a_time(self):
        runtime, bridge = self._runtime_with_roster_setup()
        runtime.setup()
        for contained_guid in (
            "card-ai-chosen-1",
            "card-ai-warrior-1",
            "card-ai-warrior-2",
            "card-ai-butcher-1",
            "card-ai-balefire-1",
            "card-ai-icon-1",
        ):
            runtime.select_roster_card(contained_guid)
        for index, contained_guid in enumerate((
            "card-op-chosen-1",
            "card-op-warrior-1",
            "card-op-warrior-2",
            "card-op-butcher-1",
            "card-op-balefire-1",
            "card-op-icon-1",
        )):
            bridge.objects[contained_guid] = live_card(
                next(item for item in bridge.containers["deck-op"]["items"] if item["guid"] == contained_guid),
                x=18.0 + (index % 3),
                z=-12.0 + (index // 3),
            )
            bridge.containers["deck-op"]["items"] = [
                item for item in bridge.containers["deck-op"]["items"] if item["guid"] != contained_guid
            ]
        runtime.lock_rosters()
        runtime.start_setup_deployment("chosen#1")
        runtime.deploy_setup_operative("model-ai-chosen-1", {"x": -20.0, "y": 1.0, "z": 6.0})
        runtime.start_setup_deployment("warrior#1")
        runtime.deploy_setup_operative("model-ai-warrior-1", {"x": -17.5, "y": 1.0, "z": 6.0})

        bridge.move_object("card-op-chosen-1", {"x": 18.0, "y": 1.0, "z": -4.0})
        bridge.take_from_container(
            "roster-op",
            item_guid="model-op-chosen-1",
            position={"x": 18.0, "y": 1.0, "z": 6.0},
            smooth=False,
        )

        reconciled = runtime.reconcile_setup_step("opponent")
        observation = runtime.observe()

        self.assertEqual(reconciled["status"], "deployed")
        self.assertEqual(reconciled["operative_id"], "chosen#1")
        self.assertEqual(observation["setup"]["current_side"], "opponent")
        self.assertEqual(observation["setup"]["current_batch_progress"], 1)

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

    def test_live_bridge_uses_zero_argument_setup_roster_cards(self):
        calls = []
        bridge = TTSKillTeamBridge(
            lambda action, args: calls.append((action, args)) or {"objects": []}
        )

        bridge.get_setup_roster_cards("aefe3b")

        self.assertEqual(calls, [("killteam_setup_roster_cards", {})])

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

    def test_plan_setup_board_reads_layout_cards_and_generates_exact_slots(self):
        bridge = FakeKillTeamBridge(
            save_131_native_objects(),
            setup_roster_cards={
                "aefe3b": [save_131_roster_card("card-warrior", "Plague Marine Warrior")]
            },
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )

        plan = runtime.plan_setup_board()

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["roster_zone_guid"], "aefe3b")
        self.assertEqual(plan["cards"][0]["guid"], "card-warrior")
        self.assertEqual(plan["placements"][0]["model_guid"], "96fe20")
        self.assertEqual(plan["placements"][0]["target_position"], {
            "x": -32.25,
            "y": 1.0,
            "z": -10.25,
        })
        self.assertEqual(plan["deployment_zone"]["bounds"], {
            "min_x": -33.0,
            "max_x": -3.0,
            "min_z": -11.0,
            "max_z": -5.0,
        })
        self.assertIn(("get_setup_roster_cards", "aefe3b"), bridge.calls)

    def test_execute_setup_board_unlocks_renames_and_moves_frozen_plan(self):
        objects = save_131_native_objects()
        first = next(item for item in objects if item["guid"] == "96fe20")
        first["position"] = {"x": 20.0, "y": 1.0, "z": -42.0}
        first["bounds"]["center"] = {"x": 20.0, "y": 1.0, "z": -42.0}
        first["locked"] = True
        second = copy.deepcopy(first)
        second["guid"] = "warrior-2"
        second["position"] = {"x": 22.0, "y": 1.0, "z": -40.0}
        second["bounds"]["center"] = {"x": 22.0, "y": 1.0, "z": -40.0}
        second["locked"] = False
        objects.append(second)
        bridge = FakeKillTeamBridge(
            objects,
            setup_roster_cards={
                "aefe3b": [
                    save_131_roster_card("card-warrior-1", "Plague Marine Warrior", 1),
                    save_131_roster_card("card-warrior-2", "Plague Marine Warrior", 2),
                ],
            },
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )
        plan = runtime.plan_setup_board()

        result = runtime.execute_setup_board(plan["plan_id"])

        self.assertEqual(result["status"], "executed")
        self.assertEqual(bridge.objects["96fe20"]["name"], "Plague Marine Warrior 1")
        self.assertEqual(bridge.objects["warrior-2"]["name"], "Plague Marine Warrior 2")
        self.assertFalse(bridge.objects["96fe20"]["locked"])
        self.assertIn(("set_object_lock", "96fe20", False), bridge.calls)
        self.assertIn(("set_object_name", "96fe20", "Plague Marine Warrior 1"), bridge.calls)
        self.assertIn(("set_object_name", "warrior-2", "Plague Marine Warrior 2"), bridge.calls)
        self.assertEqual(bridge.objects["96fe20"]["position"], plan["placements"][0]["target_position"])
        self.assertEqual(bridge.objects["warrior-2"]["position"], plan["placements"][1]["target_position"])
        self.assertFalse(any(call == ("set_object_lock", "96fe20", True) for call in bridge.calls))

    def test_plan_setup_board_fails_when_geometry_blocks_all_slots(self):
        objects = save_131_native_objects()
        objects.append({
            "guid": "huge-wall",
            "name": "Huge Wall",
            "tags": ["KT_MISSION_TERRAIN"],
            "position": {"x": -18.0, "y": 1.0, "z": -8.0},
            "bounds": {
                "center": {"x": -18.0, "y": 1.0, "z": -8.0},
                "size": {"x": 40.0, "y": 2.0, "z": 10.0},
            },
        })
        bridge = FakeKillTeamBridge(
            objects,
            setup_roster_cards={
                "aefe3b": [save_131_roster_card("card-warrior", "Plague Marine Warrior")]
            },
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )

        with self.assertRaisesRegex(KillTeamSetupError, "no legal setup slot"):
            runtime.plan_setup_board()

        self.assertFalse(any(call[0] == "move_object" for call in bridge.calls))

    def test_execute_setup_board_rejects_stale_plan(self):
        bridge = FakeKillTeamBridge(
            save_131_native_objects(),
            setup_roster_cards={
                "aefe3b": [save_131_roster_card("card-warrior", "Plague Marine Warrior")]
            },
        )
        runtime = KillTeamRuntime(
            bridge,
            KillTeamConfig(fixture_profile=SAVE_131_FIXTURE_PROFILE.name),
        )
        plan = runtime.plan_setup_board()
        bridge.objects["96fe20"]["position"]["x"] += 1.0
        bridge.objects["96fe20"]["bounds"]["center"]["x"] += 1.0

        result = runtime.execute_setup_board(plan["plan_id"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_phase"], "preflight")
        self.assertIn("stale", result["error"])
        self.assertFalse(any(call[0] == "move_object" for call in bridge.calls))

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

        from tts_mcp.runtime.killteam_runtime import _GENERIC_SETUP_QUERY_TAGS

        self.assertEqual(bridge.list_calls, [{
            "max_results": 1000,
            "compact": True,
            "required_guids": [],
            "query_tags": list(_GENERIC_SETUP_QUERY_TAGS),
        }])

    def test_setup_falls_back_to_a_raw_generic_scan_when_the_canonical_generic_scan_is_empty(self):
        from tts_mcp.runtime.killteam_runtime import _GENERIC_SETUP_QUERY_TAGS

        class NativeFallbackBridge(FakeKillTeamBridge):
            def list_objects(self, **kwargs):
                self.list_calls.append(dict(kwargs))
                if kwargs.get("query_tags") == list(_GENERIC_SETUP_QUERY_TAGS):
                    return {"objects": [], "snap_points": []}
                if kwargs.get("raw"):
                    return {
                        "objects": [copy.deepcopy(item) for item in self.objects.values()],
                        "snap_points": copy.deepcopy(self.snap_points),
                    }
                return {
                    "objects": [copy.deepcopy(item) for item in self.objects.values()],
                    "snap_points": copy.deepcopy(self.snap_points),
                }

        bridge = NativeFallbackBridge(native_generic_setup_objects())
        runtime = KillTeamRuntime(bridge)

        result = runtime.setup()
        observation = runtime.observe()

        self.assertEqual(result["status"], "ready")
        self.assertGreaterEqual(len(bridge.list_calls), 2)
        self.assertEqual(bridge.list_calls[0]["query_tags"], list(_GENERIC_SETUP_QUERY_TAGS))
        self.assertEqual(bridge.list_calls[1], {
            "max_results": 1000,
            "compact": True,
            "raw": True,
        })
        self.assertEqual(sorted(result["setup"]["sides"].keys()), ["ai", "opponent"])
        self.assertEqual(result["roller_guid"], "roller-blue")
        self.assertEqual(observation["counters"]["cp"]["guid"], "cp")
        self.assertEqual(observation["counters"]["vp"]["guid"], "vp")

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
            "max_results": 1000,
            "compact": True,
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
            "ai-1",
            [{"x": 1.0, "y": 1.0, "z": 0.0}, {"x": 2.0, "y": 1.0, "z": 0.0}],
        )
        runtime.activate_operative("plague-warrior-01")
        result = runtime.shoot("plague-warrior-01", "target-01", "boltgun")

        self.assertEqual(placement["status"], "verified")
        self.assertEqual(placement["guid"], "ai-1")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["attack_roll"], [5, 4, 2, 1])
        self.assertEqual(result["defense_roll"], [2, 1, 4])
        self.assertEqual(result["unblocked_hits"], 1)
        self.assertEqual(result["damage"], 3)
        self.assertTrue(result["los_evidence"]["visible"])
        self.assertEqual(runtime.observe()["operatives"]["target-01"]["wounds"], 7)
        self.assertEqual(bridge.objects["ai-1"]["position"]["x"], 2.0)

    def test_place_operative_rejects_semantic_operative_id_instead_of_guid(self):
        bridge = FakeKillTeamBridge(fixture_objects())
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        with self.assertRaisesRegex(KillTeamRuleError, "unknown operative plague-warrior-01"):
            runtime.place_operative(
                "plague-warrior-01",
                [{"x": 1.0, "y": 1.0, "z": 0.0}],
            )

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

    def test_plan_objective_move_prefers_the_nearest_safe_contest(self):
        objects = fixture_objects()
        moved_enemy = next(item for item in objects if item["guid"] == "96fe20")
        moved_enemy["position"] = {"x": 8.0, "y": 1.0, "z": 0.0}
        moved_enemy["bounds"]["center"] = {"x": 8.0, "y": 1.0, "z": 0.0}
        objects.append(mission_objective("objective-1", name="Central Objective", x=4.0, z=0.0, size=1.0))
        bridge = FakeKillTeamBridge(objects)
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        result = runtime.plan_objective_move("plague-warrior-01")

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["mode"], "contest")
        self.assertEqual(result["objective"]["guid"], "objective-1")
        self.assertTrue(result["selection"]["contestable"])
        self.assertEqual(result["target_position"], {"x": 2.5, "y": 1.0, "z": 0.0})
        self.assertEqual(result["move_command"], "MOVE[ai-1,2.5,1.0,0.0]")

    def test_plan_objective_move_falls_back_to_safe_staging_when_nothing_can_be_contested(self):
        objects = [item for item in fixture_objects() if item["guid"] != "96fe20"]
        objects.append(mission_objective("objective-1", name="Far Objective", x=20.0, z=0.0, size=1.0))
        bridge = FakeKillTeamBridge(objects)
        runtime = KillTeamRuntime(bridge)
        runtime.setup()

        result = runtime.plan_objective_move("plague-warrior-01")

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["mode"], "staging")
        self.assertEqual(result["objective"]["guid"], "objective-1")
        self.assertFalse(result["selection"]["contestable"])
        self.assertEqual(result["target_position"], {"x": 5.0, "y": 1.0, "z": 0.0})
        self.assertEqual(result["move_command"], "MOVE[ai-1,5.0,1.0,0.0]")

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
                "ai-1",
                [{"x": 1.0, "y": 1.0, "z": 0.0}],
                action_id="move-001",
            )
        with self.assertRaisesRegex(KillTeamUncertainCommit, "read-only recovery"):
            runtime.place_operative(
                "ai-1",
                [{"x": 1.0, "y": 1.0, "z": 0.0}],
                action_id="move-001",
            )


if __name__ == "__main__":
    unittest.main()
