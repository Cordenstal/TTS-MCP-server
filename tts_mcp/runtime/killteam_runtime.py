"""Deep Kill Team game-rule module for the first ranged-activation slice.

The module owns the rules-level interface.  A bridge adapter supplies tagged
TTS observations and bounded physical operations; tests can supply a fake
adapter with the same small interface.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


class KillTeamError(RuntimeError):
    """Base error for setup, rules, visibility, and bridge failures."""


class KillTeamSetupError(KillTeamError):
    """The table cannot be made safe for the Kill Team slice."""


class KillTeamRuleError(KillTeamError):
    """A requested semantic action is not legal in the current state."""


class KillTeamUncertainCommit(KillTeamError):
    """A TTS operation may have committed and must not be retried."""


class KillTeamBridge(Protocol):
    def list_objects(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, guid: str) -> dict[str, Any]: ...

    def get_snap_points(self, guid: str) -> dict[str, Any]: ...

    def inspect_container(self, guid: str) -> dict[str, Any]: ...

    def get_zone_objects(self, guid: str) -> dict[str, Any]: ...

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]: ...

    def take_from_container(
        self,
        container_guid: str,
        *,
        item_guid: str | None = None,
        index: int | None = None,
        position: dict[str, float] | None = None,
        flip: bool = False,
        smooth: bool = False,
    ) -> dict[str, Any]: ...

    def put_object_into_container(
        self,
        container_guid: str,
        object_guid: str,
        *,
        index: int | None = None,
    ) -> dict[str, Any]: ...

    def roll_dice(
        self,
        *,
        team: str,
        dice_guids: list[str],
        roller_guid: str,
        purpose: str,
        die_tag: str = "",
    ) -> dict[str, Any]: ...

    def probe_line_of_sight(
        self,
        observer_guid: str,
        target_guid: str,
        *,
        eye_local: dict[str, float] | None = None,
        debug: bool = False,
    ) -> dict[str, Any]: ...

    def get_roster(self, container_guid: str) -> dict[str, Any]: ...

    def get_setup_roster_cards(self, zone_guid: str) -> dict[str, Any]: ...

    def set_object_name(self, guid: str, name: str) -> dict[str, Any]: ...

    def set_object_lock(self, guid: str, locked: bool) -> dict[str, Any]: ...

    def set_counter_value(self, guid: str, value: int) -> dict[str, Any]: ...

    def spawn_builtin(
        self,
        *,
        object_type: str,
        position: dict[str, float],
        rotation: dict[str, float] | None = None,
        scale: dict[str, float] | None = None,
        name: str = "",
        locked: bool = False,
    ) -> dict[str, Any]: ...

    def observe_defense_roll(
        self,
        *,
        station_guid: str,
        expected_count: int,
    ) -> dict[str, Any]: ...

    def apply_damage(
        self,
        guid: str,
        *,
        damage: int,
        expected_wounds: int,
    ) -> dict[str, Any]: ...


class TTSKillTeamBridge:
    """Small adapter from the generic synchronous TTS request seam."""

    def __init__(self, request: Any) -> None:
        self._request = request

    @staticmethod
    def _is_legacy_list_objects_rejection(exc: Exception) -> bool:
        text = str(exc)
        return "Unknown placement MCP action: killteam_list_objects" in text

    def list_objects(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.pop("raw", False):
            payload: dict[str, Any] = {
                "max_results": kwargs.get("max_results", 1000),
                "compact": bool(kwargs.get("compact", False)),
            }
            if "name_contains" in kwargs:
                payload["name_contains"] = kwargs["name_contains"]
            if "tag" in kwargs:
                payload["tag"] = kwargs["tag"]
            try:
                return self._request("list_objects", payload)
            except Exception as exc:
                if not self._is_legacy_list_objects_rejection(exc):
                    raise
                return self._request("setup_list_objects", payload)
        query_names = list(kwargs.get("query_names") or [])
        query_tags = list(kwargs.get("query_tags") or [])
        required_guids = list(kwargs.get("required_guids") or [])
        snap_point_tags = list(kwargs.get("snap_point_tags") or [])
        if (
            query_names == ["Plague Marine Warrior"]
            and query_tags == ["_deployment_zone_blue"]
            and not required_guids
            and not snap_point_tags
        ):
            return self._request("killteam_deployment_test_objects", {})
        if (
            query_tags == list(SAVE_131_FIXTURE_PROFILE.query_tags)
            and required_guids == list(SAVE_131_FIXTURE_PROFILE.required_guids)
            and snap_point_tags == [SAVE_131_FIXTURE_PROFILE.start_snap_tag]
        ):
            # TTS can reject a multi-field External Editor message before Lua
            # receives it. Keep the fixed fixture collection entirely inside
            # the zero-argument Lua action, the same reliable boundary used
            # for deployment name discovery.
            return self._request("killteam_save_131_setup_objects", {})
        payload = {
            "max_results": kwargs.get("max_results", 1000),
            "query_tags_json": json.dumps(query_tags, separators=(",", ":")),
            "required_guids_json": json.dumps(required_guids, separators=(",", ":")),
            "snap_point_tags_json": json.dumps(snap_point_tags, separators=(",", ":")),
        }
        try:
            return self._request("killteam_list_objects", payload)
        except Exception as exc:
            if not self._is_legacy_list_objects_rejection(exc):
                raise
            fallback = {
                "max_results": payload["max_results"],
                "compact": bool(kwargs.get("compact", True)),
            }
            if len(query_names) == 1:
                fallback["name_contains"] = query_names[0]
            elif len(query_tags) == 1:
                fallback["tag"] = query_tags[0]
            return self._request("setup_list_objects", fallback)

    def get_object(self, guid: str) -> dict[str, Any]:
        return self._request("get_object", {"guid": guid})

    def get_snap_points(self, guid: str) -> dict[str, Any]:
        return self._request("get_snap_points", {"guid": guid})

    def inspect_container(self, guid: str) -> dict[str, Any]:
        return self._request("inspect_container", {"guid": guid})

    def get_zone_objects(self, guid: str) -> dict[str, Any]:
        return self._request("get_zone_objects", {"guid": guid, "ignore_tags": False})

    def get_setup_roster_cards(self, zone_guid: str) -> dict[str, Any]:
        if zone_guid.strip().lower() == SAVE_131_FIXTURE_PROFILE.setup_roster_zone_guid:
            return self._request("killteam_setup_roster_cards", {})
        return self._request("get_zone_objects", {"guid": zone_guid, "ignore_tags": False})

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]:
        return self._request(
            "move_object",
            {"guid": guid, "position": position, "smooth": False, "collide": False, "fast": True},
        )

    def take_from_container(
        self,
        container_guid: str,
        *,
        item_guid: str | None = None,
        index: int | None = None,
        position: dict[str, float] | None = None,
        flip: bool = False,
        smooth: bool = False,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "container_guid": container_guid,
            "flip": bool(flip),
            "smooth": bool(smooth),
        }
        if item_guid:
            args["item_guid"] = item_guid
        elif index is not None:
            args["index"] = int(index)
        else:
            raise ValueError("item_guid or index is required")
        if position is not None:
            args["position"] = copy.deepcopy(position)
        return self._request("take_from_container", args)

    def put_object_into_container(
        self,
        container_guid: str,
        object_guid: str,
        *,
        index: int | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "container_guid": container_guid,
            "object_guid": object_guid,
        }
        if index is not None:
            args["index"] = int(index)
        return self._request("put_object_into_container", args)

    def roll_dice(
        self,
        *,
        team: str,
        dice_guids: list[str],
        roller_guid: str,
        purpose: str,
        die_tag: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "killteam_roll_dice",
            {
                "team": team,
                "dice_guids_json": json.dumps(
                    list(dice_guids),
                    separators=(",", ":"),
                ),
                "roller_guid": roller_guid,
                "purpose": purpose,
                "die_tag": die_tag,
            },
        )

    def probe_line_of_sight(
        self,
        observer_guid: str,
        target_guid: str,
        *,
        eye_local: dict[str, float] | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        eye = eye_local or {"x": 0.0, "y": 1.0, "z": 0.0}
        return self._request(
            "killteam_probe_los",
            {
                "observer_guid": observer_guid,
                "target_guid": target_guid,
                "eye_x": float(eye.get("x", 0.0)),
                "eye_y": float(eye.get("y", 1.0)),
                "eye_z": float(eye.get("z", 0.0)),
                "debug": bool(debug),
            },
        )

    def get_roster(self, container_guid: str) -> dict[str, Any]:
        return self._request("killteam_get_roster", {"guid": container_guid})

    def set_object_name(self, guid: str, name: str) -> dict[str, Any]:
        return self._request("set_object_name", {"guid": guid, "name": name})

    def set_object_lock(self, guid: str, locked: bool) -> dict[str, Any]:
        return self._request("set_object_lock", {"guid": guid, "locked": bool(locked)})

    def set_counter_value(self, guid: str, value: int) -> dict[str, Any]:
        return self._request("set_counter_value", {"guid": guid, "value": int(value)})

    def spawn_builtin(
        self,
        *,
        object_type: str,
        position: dict[str, float],
        rotation: dict[str, float] | None = None,
        scale: dict[str, float] | None = None,
        name: str = "",
        locked: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "object_type": object_type,
            "position": copy.deepcopy(position),
            "locked": bool(locked),
        }
        if rotation is not None:
            payload["rotation"] = copy.deepcopy(rotation)
        if scale is not None:
            payload["scale"] = copy.deepcopy(scale)
        if name:
            payload["name"] = name
        return self._request("spawn_builtin", payload)

    def observe_defense_roll(
        self,
        *,
        station_guid: str,
        expected_count: int,
    ) -> dict[str, Any]:
        return self._request(
            "killteam_observe_defense_roll",
            {
                "station_guid": station_guid,
                "expected_count": int(expected_count),
            },
        )

    def apply_damage(
        self,
        guid: str,
        *,
        damage: int,
        expected_wounds: int,
    ) -> dict[str, Any]:
        return self._request(
            "killteam_apply_damage",
            {
                "guid": guid,
                "damage": int(damage),
                "expected_wounds": int(expected_wounds),
            },
        )


@dataclass(frozen=True)
class KillTeamFixtureProfile:
    """Versioned adapter from one native TTS fixture to canonical game roles."""

    name: str
    query_tags: tuple[str, ...]
    required_guids: tuple[str, ...]
    start_snap_tag: str
    ai_faction_tags: tuple[str, ...]
    ai_dice_tag: str
    ai_roller_tag: str
    defense_station_guid: str
    roster_container_guid: str
    setup_roster_zone_guid: str
    counter_guids: tuple[tuple[str, str], ...]


SAVE_131_FIXTURE_PROFILE = KillTeamFixtureProfile(
    name="setup_operatives_save_131",
    query_tags=(
        "Operative",
        "_dice_blue",
        "_blue_dice_roller",
        "combat_zone",
        "_deployment_zone_blue",
        "KT_MISSION_TERRAIN",
        "KT_MISSION_OBJECTIVE",
    ),
    required_guids=(
        "f1adc9",
        "e5adb7",
        "2cc38b",
        "d9b193",
        "7ff953",
        "53befd",
        "74bea2",
    ),
    start_snap_tag="_start_test_spot",
    ai_faction_tags=("LEGIONARY", "Chaos"),
    ai_dice_tag="_dice_blue",
    ai_roller_tag="_blue_dice_roller",
    defense_station_guid="f1adc9",
    roster_container_guid="e5adb7",
    setup_roster_zone_guid="aefe3b",
    counter_guids=(
        ("cp", "2cc38b"),
        ("kill_vp", "d9b193"),
        ("tac_vp", "7ff953"),
        ("crit_vp", "53befd"),
    ),
)

_FIXTURE_PROFILES = {SAVE_131_FIXTURE_PROFILE.name: SAVE_131_FIXTURE_PROFILE}


@dataclass(frozen=True)
class KillTeamConfig:
    ai_team: str = "ai"
    units_per_inch: float = 1.0
    ai_dice_count: int = 1
    opponent_dice_count: int = 1
    roster_container_guid: str = "e5adb7"
    target_guid: str = "96fe20"
    fixture_profile: str = ""
    initiative_side: str = ""


@dataclass(frozen=True)
class KillTeamSetupFactionProfile:
    faction_id: str
    exact_team_size: int
    leader_type_ids: frozenset[str]
    unlimited_type_ids: frozenset[str] = frozenset()
    per_type_limits: dict[str, int] | None = None
    default_limit: int = 1


_GENERIC_SETUP_QUERY_TAGS = (
    "tts_mcp:entity=operative",
    "tts_mcp:entity=die",
    "tts_mcp:entity=dice_roller",
    "tts_mcp:entity=counter",
    "tts_mcp:entity=calibration",
    "tts_mcp:entity=terrain",
    "tts_mcp:entity=deployment",
    "tts_mcp:entity=faction_decks",
    "tts_mcp:entity=roster",
    "tts_mcp:entity=roster_list_zone",
    "tts_mcp:entity=deployed_zone",
    "tts_mcp:entity=roster_card",
)

_GENERIC_NATIVE_SETUP_QUERY_TAGS = (
    "Blue",
    "Red",
    "Operative",
    "_dice_blue",
    "_dice_red",
    "_blue_dice_roller",
    "_red_dice_roller",
    "dice_roller",
    "combat_zone",
    "_deployment_zone_blue",
    "_deployment_zone_red",
    "KT_MISSION_TERRAIN",
    "KT_MISSION_OBJECTIVE",
    "_faction_decks",
    "_roster",
    "_roster_card",
    "Roster List",
    "Deployed Zone",
    "counter",
    "calibration",
)

_SETUP_FACTION_PROFILES = {
    "legionary": KillTeamSetupFactionProfile(
        faction_id="legionary",
        exact_team_size=6,
        leader_type_ids=frozenset({"chosen", "aspiring_champion"}),
        unlimited_type_ids=frozenset({"warrior"}),
    ),
    "legionaries": KillTeamSetupFactionProfile(
        faction_id="legionary",
        exact_team_size=6,
        leader_type_ids=frozenset({"chosen", "aspiring_champion"}),
        unlimited_type_ids=frozenset({"warrior"}),
    ),
    "novitiate": KillTeamSetupFactionProfile(
        faction_id="novitiate",
        exact_team_size=10,
        leader_type_ids=frozenset({"superior"}),
        unlimited_type_ids=frozenset({"militant"}),
        per_type_limits={"purgatus": 2},
    ),
    "novitiates": KillTeamSetupFactionProfile(
        faction_id="novitiate",
        exact_team_size=10,
        leader_type_ids=frozenset({"superior"}),
        unlimited_type_ids=frozenset({"militant"}),
        per_type_limits={"purgatus": 2},
    ),
}


def _live_object_guid(value: Any) -> str | None:
    """Return a usable TTS GUID, never TTS's stale-reference sentinel."""
    guid = str(value or "").strip()
    if not guid or guid == "-1":
        return None
    return guid


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _tag_metadata(tags: Any) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw in tags or []:
        value = str(raw).strip()
        if not value.lower().startswith("tts_mcp:"):
            continue
        entry = value[len("tts_mcp:"):]
        key, separator, item = entry.partition("=")
        if separator:
            metadata[key.strip().lower()] = item.strip()
        elif key.strip():
            metadata[key.strip().lower()] = "true"
    return metadata


def _metadata(obj: dict[str, Any]) -> dict[str, str]:
    result = _tag_metadata(obj.get("tags"))
    nested = obj.get("meta")
    if isinstance(nested, dict):
        result.update({str(key).lower(): str(value) for key, value in nested.items()})
    return result


def _is_terrain_surface(obj: dict[str, Any]) -> bool:
    metadata = _metadata(obj)
    if _norm(metadata.get("entity")) == "terrain":
        return True
    if _bool(metadata.get("blocks_los")):
        entity = _norm(metadata.get("entity"))
        if entity not in {"objective", "operative", "deployment", "deployed_zone", "roster", "counter", "die", "calibration"}:
            return True
    tags = {str(tag).strip().casefold() for tag in obj.get("tags", [])}
    if "kt_mission_terrain" in tags:
        return True
    return False


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _whole_number(value: Any, field: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise KillTeamSetupError(f"{field} must be an integer") from exc


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise KillTeamSetupError(f"{field} must be numeric") from exc


def _position(obj: dict[str, Any]) -> dict[str, float]:
    raw = obj.get("position") or {}
    return {axis: _number(raw.get(axis, 0), f"position.{axis}") for axis in ("x", "y", "z")}


def _bounds_box(obj: dict[str, Any]) -> dict[str, Any] | None:
    raw = obj.get("bounds") or {}
    center = raw.get("center") or obj.get("position") or {}
    size = raw.get("size") or {}
    try:
        cx = float(center["x"])
        cy = float(center["y"])
        cz = float(center["z"])
        sx = abs(float(size.get("x", 0)))
        sy = abs(float(size.get("y", 0)))
        sz = abs(float(size.get("z", 0)))
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "rect": (cx - sx / 2, cx + sx / 2, cz - sz / 2, cz + sz / 2),
        "min_y": cy - sy / 2,
        "max_y": cy + sy / 2,
        "center": {"x": cx, "y": cy, "z": cz},
        "size": {"x": sx, "y": sy, "z": sz},
    }


def _clean_setup_name(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\[[0-9A-Fa-f]{6}\]", "", text)
    text = text.replace("[-]", "")
    text = re.sub(r"\{\s*\d+\s*/\s*\d+\s*\}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _setup_base_name(value: Any) -> str:
    text = _clean_setup_name(value)
    text = re.sub(r"\broster\s+card\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+#?\d+\s*$", "", text).strip()
    return re.sub(r"\s+", " ", text)


def _setup_numbered_name(base: str, index: int) -> str:
    return f"{base} {index}"


def _inflated_rect(
    rect: tuple[float, float, float, float],
    padding: float,
) -> tuple[float, float, float, float]:
    return rect[0] - padding, rect[1] + padding, rect[2] - padding, rect[3] + padding


def _rect_dict(rect: tuple[float, float, float, float]) -> dict[str, float]:
    return {"min_x": rect[0], "max_x": rect[1], "min_z": rect[2], "max_z": rect[3]}


def _rect_tuple(value: tuple[float, float, float, float] | dict[str, float]) -> tuple[float, float, float, float]:
    if isinstance(value, dict):
        return (
            float(value["min_x"]),
            float(value["max_x"]),
            float(value["min_z"]),
            float(value["max_z"]),
        )
    return value


def parse_profile_description(description: str) -> dict[str, Any]:
    """Parse the compact profile format used by the supplied TTS save."""
    text = str(description or "")
    text = re.sub(r"\[[0-9A-Fa-f]{6}\]", "", text)
    text = text.replace("[-]", "").replace("[", "").replace("]", "")

    def stat(labels: tuple[str, ...], default: int | None = None) -> int | None:
        alternatives = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"\b(?:{alternatives})\s+(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else default

    profile: dict[str, Any] = {
        "move": stat(("M", "MOVE")),
        "apl": stat(("APL",)),
        "save": stat(("SV", "SAVE")),
        "wounds": stat(("W", "WOUNDS")),
        "weapons": {},
    }
    weapon_pattern = re.compile(
        r"(?:^|\n)\s*[RM]\s+([A-Za-z][A-Za-z0-9' -]*)\s*\n\s*"
        r"ATK\s+(\d+).*?HIT\s+(\d+)\+.*?DMG\s+(\d+)\s*/\s*(\d+)([^\n]*)",
        re.IGNORECASE,
    )
    for match in weapon_pattern.finditer(text):
        weapon_name = re.sub(r"\s+", " ", match.group(1).strip()).lower()
        weapon_line = match.group(0)
        range_match = re.search(
            r"(?:Range|Rng)\s+\(?(\d+(?:\.\d+)?)",
            weapon_line,
            re.IGNORECASE,
        )
        profile["weapons"][weapon_name] = {
            "attacks": int(match.group(2)),
            "hit": int(match.group(3)),
            "damage": int(match.group(4)),
            "critical_damage": int(match.group(5)),
            "range": float(range_match.group(1)) if range_match else None,
        }
    # Some saved descriptions wrap the weapon statistics in extra formatting
    # brackets. Keep a line-oriented fallback so a profile remains readable
    # even when the formatter changes its line breaks.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        name_match = re.search(r"\b[RM]\s+([A-Za-z][A-Za-z0-9' -]*)", line)
        if not name_match:
            continue
        candidate = "\n".join(lines[index + 1:index + 4])
        attack = re.search(
            r"ATK\s+(\d+).*?HIT\s+(\d+)\+.*?DMG\s+(\d+)\s*/\s*(\d+)",
            candidate,
            re.IGNORECASE | re.DOTALL,
        )
        if not attack:
            continue
        weapon_name = re.sub(r"\s+", " ", name_match.group(1).strip()).lower()
        range_match = re.search(
            r"(?:Range|Rng)\s+\(?(\d+(?:\.\d+)?)",
            candidate,
            re.IGNORECASE,
        )
        profile["weapons"][weapon_name] = {
            "attacks": int(attack.group(1)),
            "hit": int(attack.group(2)),
            "damage": int(attack.group(3)),
            "critical_damage": int(attack.group(4)),
            "range": float(range_match.group(1)) if range_match else None,
        }
    return profile


def _profile(obj: dict[str, Any]) -> dict[str, Any]:
    value = obj.get("profile")
    if isinstance(value, dict):
        result = copy.deepcopy(value)
    else:
        result = parse_profile_description(str(obj.get("description") or ""))
    required = ("move", "apl", "save", "wounds")
    if any(result.get(field) is None for field in required):
        raise KillTeamSetupError(f"operative {obj.get('guid', '')} has an incomplete profile")
    result.setdefault("defense_dice", 3)
    result.setdefault("weapons", {})
    return result


def _bounds(obj: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = obj.get("bounds") or {}
    center = raw.get("center") or obj.get("position") or {}
    size = raw.get("size") or {}
    try:
        cx, cz = float(center["x"]), float(center["z"])
        sx, sz = abs(float(size.get("x", 0))), abs(float(size.get("z", 0)))
    except (KeyError, TypeError, ValueError):
        return None
    return cx - sx / 2, cx + sx / 2, cz - sz / 2, cz + sz / 2


def _rect_contains_rect(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    outer = _rect_tuple(outer)
    inner = _rect_tuple(inner)
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] <= outer[1] + tolerance
        and inner[2] >= outer[2] - tolerance
        and inner[3] <= outer[3] + tolerance
    )


def _rects_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    first = _rect_tuple(first)
    second = _rect_tuple(second)
    return not (
        first[1] <= second[0] + tolerance
        or second[1] <= first[0] + tolerance
        or first[3] <= second[2] + tolerance
        or second[3] <= first[2] + tolerance
    )


def _y_spans_overlap(
    first: tuple[float, float],
    second: tuple[float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    return not (
        first[1] <= second[0] + tolerance
        or second[1] <= first[0] + tolerance
    )


def _stable_revision_id(payload: Any) -> int:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return int(hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12], 16)


def _segment_intersects_rect(
    start: dict[str, float],
    end: dict[str, float],
    rect: tuple[float, float, float, float],
) -> bool:
    """Return whether the horizontal segment crosses an axis-aligned box."""
    min_x, max_x, min_z, max_z = rect
    dx = end["x"] - start["x"]
    dz = end["z"] - start["z"]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, start["x"] - min_x), (dx, max_x - start["x"]), (-dz, start["z"] - min_z), (dz, max_z - start["z"])):
        if abs(p) < 1e-9:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            if ratio > t1:
                return False
            t0 = max(t0, ratio)
        else:
            if ratio < t0:
                return False
            t1 = min(t1, ratio)
    return t0 <= t1


def _rect_center(rect: tuple[float, float, float, float]) -> dict[str, float]:
    return {
        "x": (rect[0] + rect[1]) / 2,
        "z": (rect[2] + rect[3]) / 2,
    }


def _resolve_ranged_successes(
    attack_faces: list[int],
    defense_faces: list[int],
    *,
    hit: int,
    save: int,
    normal_damage: int,
    critical_damage: int,
) -> dict[str, int]:
    """Allocate Kill Team saves to minimize the defender's incoming damage."""
    critical_hits = sum(face == 6 for face in attack_faces)
    normal_hits = sum(hit <= face < 6 for face in attack_faces)
    critical_saves = sum(face == 6 for face in defense_faces)
    normal_saves = sum(save <= face < 6 for face in defense_faces)
    best: tuple[int, int, int] | None = None
    for critical_on_critical in range(min(critical_hits, critical_saves) + 1):
        remaining_critical_saves = critical_saves - critical_on_critical
        for critical_on_normal in range(min(normal_hits, remaining_critical_saves) + 1):
            unblocked_critical = critical_hits - critical_on_critical
            unblocked_normal = normal_hits - critical_on_normal
            for normal_pairs_on_critical in range(
                min(unblocked_critical, normal_saves // 2) + 1
            ):
                remaining_normal_saves = normal_saves - 2 * normal_pairs_on_critical
                final_critical = unblocked_critical - normal_pairs_on_critical
                final_normal = max(0, unblocked_normal - remaining_normal_saves)
                damage = (
                    final_critical * critical_damage
                    + final_normal * normal_damage
                )
                candidate = (damage, final_critical, final_normal)
                if best is None or candidate < best:
                    best = candidate
    assert best is not None
    return {
        "critical_hits": critical_hits,
        "normal_hits": normal_hits,
        "critical_saves": critical_saves,
        "normal_saves": normal_saves,
        "unblocked_critical_hits": best[1],
        "unblocked_normal_hits": best[2],
        "damage": best[0],
    }


class KillTeamRuntime:
    """Deep game-rule interface for setup, movement, and one ranged attack."""

    def __init__(self, bridge: KillTeamBridge, config: KillTeamConfig | None = None) -> None:
        self.bridge = bridge
        self.config = config or KillTeamConfig()
        self._fixture_profile = _FIXTURE_PROFILES.get(self.config.fixture_profile)
        if self.config.fixture_profile and self._fixture_profile is None:
            raise KillTeamSetupError(f"unknown Kill Team fixture profile {self.config.fixture_profile}")
        self._objects: dict[str, dict[str, Any]] = {}
        self._snap_points: list[dict[str, Any]] = []
        self._state: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []
        self._action_results: dict[str, dict[str, Any]] = {}
        self._uncertain_action_ids: set[str] = set()
        self._listing_truncated = False
        self._setup_board_plans: dict[str, dict[str, Any]] = {}

    def _list_objects(self) -> list[dict[str, Any]]:
        # Kill Team needs identity, tags, transforms, bounds, counters, and
        # die values—all present in the compact bridge response. Full object
        # summaries touch optional TTS properties and can dereference a stale
        # object while the table is settling.
        required_guids: list[str] = []
        query_tags: list[str] = []
        snap_point_tags: list[str] = []
        if self._fixture_profile is not None:
            required_guids.extend(self._fixture_profile.required_guids)
            query_tags.extend(self._fixture_profile.query_tags)
            snap_point_tags.append(self._fixture_profile.start_snap_tag)
        else:
            query_tags.extend(_GENERIC_SETUP_QUERY_TAGS)
        list_kwargs: dict[str, Any] = {
            "max_results": 1000,
            "compact": True,
            "required_guids": required_guids,
        }
        if query_tags:
            list_kwargs["query_tags"] = query_tags
        if snap_point_tags:
            list_kwargs["snap_point_tags"] = snap_point_tags
        result = self.bridge.list_objects(
            **list_kwargs,
        )
        self._listing_truncated = bool(result.get("truncated")) if isinstance(result, dict) else True
        objects = result.get("objects", []) if isinstance(result, dict) else []
        snap_points = result.get("snap_points", []) if isinstance(result, dict) else []
        if (
            self._fixture_profile is None
            and not objects
            and query_tags == list(_GENERIC_SETUP_QUERY_TAGS)
        ):
            fallback_kwargs = {
                "max_results": 1000,
                "compact": True,
                "raw": True,
            }
            result = self.bridge.list_objects(**fallback_kwargs)
            self._listing_truncated = bool(result.get("truncated")) if isinstance(result, dict) else True
            objects = result.get("objects", []) if isinstance(result, dict) else []
            snap_points = result.get("snap_points", []) if isinstance(result, dict) else []
        if not isinstance(objects, list):
            raise KillTeamSetupError("TTS object listing was not a list")
        if not isinstance(snap_points, list):
            raise KillTeamSetupError("TTS snap point listing was not a list")
        self._snap_points = [
            copy.deepcopy(point) for point in snap_points if isinstance(point, dict)
        ]
        return [
            copy.deepcopy(obj)
            for obj in objects
            if isinstance(obj, dict) and _live_object_guid(obj.get("guid")) is not None
        ]

    @staticmethod
    def _has_native_tag(obj: dict[str, Any], tag: str) -> bool:
        expected = tag.casefold()
        return any(str(value).strip().casefold() == expected for value in obj.get("tags", []))

    @staticmethod
    def _setup_generic_text(obj: dict[str, Any]) -> str:
        parts = [
            str(obj.get("name") or ""),
            str(obj.get("description") or ""),
            " ".join(str(tag) for tag in obj.get("tags", [])),
        ]
        return " ".join(part for part in parts if part).casefold()

    def _setup_generic_side_id(self, obj: dict[str, Any]) -> str:
        words = set(re.findall(r"[a-z0-9]+", self._setup_generic_text(obj)))
        if words & {"blue", "ai"}:
            return self.config.ai_team
        if words & {"red", "opponent"}:
            return "opponent"
        return ""

    def _normalize_fixture_objects(
        self,
        objects: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Project Save 131's native tags and stable anchors into canonical roles."""
        profile = self._fixture_profile
        if profile is None:
            normalized = copy.deepcopy(objects)
            for obj in normalized:
                tags = {str(tag).strip().casefold() for tag in obj.get("tags", [])}
                name = str(obj.get("name") or "").casefold()
                meta = dict(obj.get("meta") or {})
                side_id = self._setup_generic_side_id(obj)
                if side_id:
                    meta.setdefault("side_id", side_id)
                    meta.setdefault("team", side_id)
                if "_faction_decks" in tags:
                    meta.setdefault("entity", "faction_decks")
                if "_roster" in tags:
                    meta.setdefault("entity", "roster")
                if "_roster_card" in tags:
                    meta.setdefault("entity", "roster_card")
                if "_dice_blue" in tags or "_dice_red" in tags:
                    meta.setdefault("entity", "die")
                    if side_id:
                        meta.setdefault("team", side_id)
                if "_blue_dice_roller" in tags or "_red_dice_roller" in tags or "dice roller" in name:
                    meta.setdefault("entity", "dice_roller")
                    if side_id:
                        meta.setdefault("team", side_id)
                if "roster list" in name or "roster cards" in name:
                    meta.setdefault("entity", "roster_list_zone")
                if "deployed zone" in name:
                    meta.setdefault("entity", "deployed_zone")
                if "_deployment_zone_blue" in tags or "_deployment_zone_red" in tags:
                    meta.setdefault("entity", "deployment")
                if "operative" in tags or "operative" in name:
                    meta.setdefault("entity", "operative")
                    if side_id:
                        meta.setdefault("team", side_id)
                if "combat_zone" in tags:
                    meta.setdefault("entity", "combat_zone")
                if "kt_mission_terrain" in tags:
                    meta.setdefault("entity", "terrain")
                    meta.setdefault("blocks_los", "true")
                if "kt_mission_objective" in tags:
                    meta.setdefault("entity", "objective")
                if "counter" in tags:
                    meta.setdefault("entity", "counter")
                    if "cp" in name:
                        meta.setdefault("counter", "cp")
                    elif "vp" in name:
                        meta.setdefault("counter", "vp")
                if "calibration" in tags:
                    meta.setdefault("entity", "calibration")
                obj["meta"] = meta
            return normalized

        normalized = copy.deepcopy(objects)
        by_guid = {str(obj.get("guid", "")).lower(): obj for obj in normalized}
        ai_tags = {tag.casefold() for tag in profile.ai_faction_tags}
        ai_index = 0
        opponent_index = 0
        for obj in normalized:
            tags = {str(tag).strip().casefold() for tag in obj.get("tags", [])}
            meta = dict(obj.get("meta") or {})
            if "operative" in tags:
                is_ai = bool(tags & ai_tags) or "plague marine" in str(obj.get("name", "")).casefold()
                if is_ai:
                    ai_index += 1
                    role = re.sub(
                        r"[^a-z0-9]+",
                        "-",
                        str(obj.get("name") or "operative").casefold(),
                    ).strip("-")
                    role = role.removeprefix("plague-marine-") or "operative"
                    operative_id = f"plague-{role}-{ai_index:02d}"
                    team = self.config.ai_team
                    profile_id = "plague_warrior" if "warrior" in role else role.replace("-", "_")
                else:
                    opponent_index += 1
                    operative_id = f"visible-target-{opponent_index:02d}"
                    team = "opponent"
                    profile_id = "target"
                meta.update({
                    "entity": "operative",
                    "team": team,
                    "operative_id": operative_id,
                    "profile": profile_id,
                    "visibility": "public",
                })
            if profile.ai_dice_tag.casefold() in tags:
                meta.update({"entity": "die", "team": self.config.ai_team})
            if profile.ai_roller_tag.casefold() in tags:
                meta.update({"entity": "dice_roller", "team": self.config.ai_team})
            if "kt_mission_terrain" in tags:
                meta.update({"entity": "terrain", "blocks_los": "true"})
            if "kt_mission_objective" in tags:
                meta.update({"entity": "objective"})
            if "combat_zone" in tags:
                meta.update({"entity": "combat_zone"})
            if "_deployment_zone_blue" in tags:
                meta.update({"entity": "deployment", "team": self.config.ai_team})
            obj["meta"] = meta

        anchored_roles = {
            profile.defense_station_guid: {"entity": "defense_station", "team": "opponent"},
            profile.roster_container_guid: {"entity": "roster", "team": self.config.ai_team},
        }
        anchored_roles.update({
            guid: {"entity": "counter", "counter": counter, "team": self.config.ai_team}
            for counter, guid in profile.counter_guids
        })
        for guid, role in anchored_roles.items():
            obj = by_guid.get(guid.lower())
            if obj is None:
                raise KillTeamSetupError(f"required Save 131 anchor is missing: {guid}")
            obj.setdefault("meta", {}).update(role)
        return normalized

    def _is_visible(self, obj: dict[str, Any], metadata: dict[str, str] | None = None) -> bool:
        metadata = metadata or _metadata(obj)
        if metadata.get("team", "").lower() == self.config.ai_team.lower():
            return True
        if metadata.get("visibility", "").lower() in {"hidden", "private", "concealed", "opponent_hidden"}:
            return False
        return obj.get("visible", True) is not False

    def _refresh(self) -> None:
        objects = self._normalize_fixture_objects(self._list_objects())
        self._objects = {str(obj["guid"]): obj for obj in objects}
        if self._state is None:
            return
        for record in self._state["operatives"].values():
            obj = self._objects.get(record["guid"])
            if obj is not None:
                record["position"] = _position(obj)
                for field in ("name", "description", "type", "tags", "bounds"):
                    if field in obj:
                        record[field] = copy.deepcopy(obj[field])
        self._state["map_revision"] = self._scene_revision(self._objects.values())

    def _scene_revision(
        self,
        objects: Any,
        *,
        exclude_guids: set[str] | None = None,
    ) -> int:
        excluded = {str(guid).strip().lower() for guid in (exclude_guids or set()) if str(guid).strip()}
        items: list[dict[str, Any]] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            guid = str(obj.get("guid") or "").strip()
            if not guid or guid.lower() in excluded:
                continue
            metadata = _metadata(obj)
            entity = _norm(metadata.get("entity"))
            box = _bounds_box(obj)
            if box is None:
                continue
            entry = {
                "guid": guid,
                "entity": entity,
                "bounds": _rect_dict(box["rect"]),
                "min_y": box["min_y"],
                "max_y": box["max_y"],
            }
            if entity in {"operative", "objective"}:
                entry["team"] = _norm(metadata.get("team"))
                entry["visible"] = self._is_visible(obj, metadata)
            elif entity == "terrain" or _is_terrain_surface(obj):
                entry["visible"] = self._is_visible(obj, metadata)
            else:
                continue
            items.append(entry)
        items.sort(key=lambda item: (str(item["entity"]), str(item["guid"])))
        return _stable_revision_id(items)

    def _setup_board_context_revision(
        self,
        snapshot: dict[str, Any],
        *,
        exclude_guids: set[str] | None = None,
    ) -> int:
        excluded = {str(guid).strip().lower() for guid in (exclude_guids or set()) if str(guid).strip()}
        payload = {
            "deployment": {
                "guid": str(snapshot["deployment"].get("guid") or ""),
                "bounds": copy.deepcopy(snapshot["deployment_bounds"]),
                "floor_y": snapshot["deployment_floor_y"],
                "top_y": snapshot["deployment_top_y"],
            },
            "support_surfaces": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "bounds": copy.deepcopy(item["bounds"]),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                }
                for item in sorted(snapshot["support_surfaces"], key=lambda item: (str(item["guid"]), str(item["name"])))
                if str(item["guid"]).strip().lower() not in excluded
            ],
            "blockers": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "entity": item["entity"],
                    "team": item.get("team", ""),
                    "bounds": copy.deepcopy(item["bounds"]),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                }
                for item in sorted(snapshot["blockers"], key=lambda item: (str(item["entity"]), str(item["guid"])))
                if str(item["guid"]).strip().lower() not in excluded
            ],
            "friendly_occupancy": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "bounds": copy.deepcopy(item["bounds"]),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                }
                for item in sorted(snapshot["friendly_occupancy"], key=lambda item: str(item["guid"]))
                if str(item["guid"]).strip().lower() not in excluded
            ],
            "enemy_occupancy": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "bounds": copy.deepcopy(item["bounds"]),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                }
                for item in sorted(snapshot["enemy_occupancy"], key=lambda item: str(item["guid"]))
                if str(item["guid"]).strip().lower() not in excluded
            ],
        }
        return _stable_revision_id(payload)

    def _setup_board_snapshot(self, roster_zone_guid: str) -> dict[str, Any]:
        profile = self._fixture_profile
        if profile is None or profile.name != SAVE_131_FIXTURE_PROFILE.name:
            raise KillTeamSetupError("setup board planning requires the Save 131 fixture profile")
        roster_zone_guid = roster_zone_guid.strip().lower() or profile.setup_roster_zone_guid
        if roster_zone_guid != profile.setup_roster_zone_guid:
            raise KillTeamSetupError("Save 131 setup board planning uses fixed roster zone aefe3b")

        objects = self._normalize_fixture_objects(self._list_objects())
        self._objects = {str(obj["guid"]): obj for obj in objects}
        try:
            raw_cards = self.bridge.get_setup_roster_cards(roster_zone_guid)
        except Exception as exc:
            raise KillTeamSetupError("Deployed Zone roster cards could not be inspected") from exc
        card_objects = raw_cards.get("objects", []) if isinstance(raw_cards, dict) else []
        if not isinstance(card_objects, list):
            raise KillTeamSetupError("Deployed Zone roster card response was invalid")
        cards: list[dict[str, Any]] = []
        for index, obj in enumerate(card_objects, start=1):
            if not isinstance(obj, dict):
                continue
            object_type = str(obj.get("type") or "")
            if "card" not in object_type.casefold():
                raise KillTeamSetupError(
                    f"Deployed Zone item {obj.get('guid', '<unknown>')} is not a roster card"
                )
            base_name = _setup_base_name(obj.get("name"))
            if not base_name:
                raise KillTeamSetupError(f"Deployed Zone card {obj.get('guid', '<unknown>')} has no mappable name")
            cards.append({
                "guid": str(obj.get("guid") or ""),
                "name": _clean_setup_name(obj.get("name")),
                "base_name": base_name,
                "layout_index": int(obj.get("layout_index", index) or index),
                "tags": copy.deepcopy(obj.get("tags", [])),
            })
        if not cards:
            raise KillTeamSetupError("Deployed Zone aefe3b contains no roster cards")

        deployments = [
            obj for obj in objects
            if _norm(_metadata(obj).get("entity")) == "deployment"
            and _norm(_metadata(obj).get("team")) == self.config.ai_team
        ]
        if len(deployments) != 1:
            raise KillTeamSetupError(f"expected one Blue deployment zone; found {len(deployments)}")
        deployment = deployments[0]
        deployment_box = _bounds_box(deployment)
        if deployment_box is None:
            raise KillTeamSetupError("Blue deployment zone is missing bounds")
        deployment_bounds = deployment_box["rect"]
        deployment_floor_y = deployment_box["min_y"]
        deployment_top_y = deployment_box["max_y"]
        combat_zones = [
            obj for obj in objects
            if _norm(_metadata(obj).get("entity")) == "combat_zone"
        ]
        combat_center = None
        if combat_zones:
            combat_center = _position(combat_zones[0])

        models: list[dict[str, Any]] = []
        ai_tags = {tag.casefold() for tag in profile.ai_faction_tags}
        for obj in objects:
            metadata = _metadata(obj)
            if metadata.get("entity") != "operative" or _norm(metadata.get("team")) != self.config.ai_team:
                continue
            tags = {str(tag).strip().casefold() for tag in obj.get("tags", [])}
            object_type = str(obj.get("type") or "").casefold()
            if object_type and object_type != "figurine":
                continue
            if "operative" not in tags or not ai_tags.issubset(tags):
                continue
            bounds = _bounds_box(obj)
            if bounds is None:
                raise KillTeamSetupError(f"model {obj.get('guid', '<unknown>')} is missing bounds")
            models.append({
                "guid": str(obj.get("guid") or ""),
                "name": _clean_setup_name(obj.get("name")),
                "position": _position(obj),
                "bounds": copy.deepcopy(obj.get("bounds")),
                "bounds_rect": _rect_dict(bounds["rect"]),
                "min_y": bounds["min_y"],
                "max_y": bounds["max_y"],
                "height": bounds["max_y"] - bounds["min_y"],
                "locked": bool(obj.get("locked", False)),
                "object": copy.deepcopy(obj),
            })
        if not models:
            raise KillTeamSetupError("no live AI operative models were found")

        support_surfaces: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        friendly_occupancy: list[dict[str, Any]] = []
        enemy_occupancy: list[dict[str, Any]] = []
        for obj in objects:
            entity = _norm(_metadata(obj).get("entity"))
            box = _bounds_box(obj)
            if box is None:
                continue
            metadata = _metadata(obj)
            occupancy_item = {
                "guid": str(obj.get("guid") or ""),
                "name": str(obj.get("name") or ""),
                "entity": entity,
                "team": _norm(metadata.get("team")),
                "bounds": _rect_dict(box["rect"]),
                "min_y": box["min_y"],
                "max_y": box["max_y"],
                "height": box["max_y"] - box["min_y"],
                "visible": self._is_visible(obj, metadata),
            }
            if _is_terrain_surface(obj):
                support_surfaces.append(copy.deepcopy(occupancy_item))
                continue
            if entity not in {"objective", "operative"}:
                continue
            blockers.append(copy.deepcopy(occupancy_item))
            if entity == "operative":
                if occupancy_item["team"] == self.config.ai_team:
                    friendly_occupancy.append(copy.deepcopy(occupancy_item))
                elif occupancy_item["visible"]:
                    enemy_occupancy.append(copy.deepcopy(occupancy_item))
            elif occupancy_item["visible"]:
                enemy_occupancy.append(copy.deepcopy(occupancy_item))
        support_surfaces.sort(key=lambda item: str(item["guid"]))
        blockers.sort(key=lambda item: (str(item["entity"]), str(item["guid"])))
        friendly_occupancy.sort(key=lambda item: str(item["guid"]))
        enemy_occupancy.sort(key=lambda item: str(item["guid"]))
        return {
            "objects": objects,
            "cards": cards,
            "models": models,
            "deployment": deployment,
            "map_revision": self._scene_revision(objects),
            "deployment_bounds": deployment_bounds,
            "deployment_floor_y": deployment_floor_y,
            "deployment_top_y": deployment_top_y,
            "combat_center": combat_center,
            "support_surfaces": support_surfaces,
            "blockers": blockers,
            "friendly_occupancy": friendly_occupancy,
            "enemy_occupancy": enemy_occupancy,
            "roster_order_source": str(raw_cards.get("order_source", "layout_zone.getObjects")) if isinstance(raw_cards, dict) else "layout_zone.getObjects",
        }

    def _setup_board_targets(self, snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        cards = list(snapshot["cards"])
        models = list(snapshot["models"])
        models_by_base: dict[str, list[dict[str, Any]]] = {}
        for model in models:
            models_by_base.setdefault(_setup_base_name(model.get("name")), []).append(model)
        card_counts: dict[str, int] = {}
        for card in cards:
            card_counts[card["base_name"]] = card_counts.get(card["base_name"], 0) + 1

        targets: list[dict[str, Any]] = []
        renames: list[dict[str, Any]] = []
        used_guids: set[str] = set()
        for base_name, count in card_counts.items():
            candidates = models_by_base.get(base_name, [])
            if len(candidates) != count:
                raise KillTeamSetupError(
                    f"roster card base {base_name!r} maps to {len(candidates)} live models, expected {count}"
                )
            candidates.sort(key=lambda obj: (_position(obj)["z"], _position(obj)["x"]))
            for index, model in enumerate(candidates, start=1):
                guid = str(model["guid"])
                used_guids.add(guid)
                final_name = _setup_numbered_name(base_name, index) if count > 1 else _clean_setup_name(model.get("name"))
                if _clean_setup_name(model.get("name")) != final_name:
                    renames.append({
                        "guid": guid,
                        "from": _clean_setup_name(model.get("name")),
                        "to": final_name,
                        "base_name": base_name,
                        "index": index,
                    })
        occurrence: dict[str, int] = {}
        by_base_sorted: dict[str, list[dict[str, Any]]] = {}
        for base_name, candidates in models_by_base.items():
            candidates = [obj for obj in candidates if str(obj.get("guid")) in used_guids]
            candidates.sort(key=lambda obj: (_position(obj)["z"], _position(obj)["x"]))
            by_base_sorted[base_name] = candidates
        for card in cards:
            base_name = card["base_name"]
            occurrence[base_name] = occurrence.get(base_name, 0) + 1
            model = by_base_sorted[base_name][occurrence[base_name] - 1]
            model_count = card_counts[base_name]
            final_name = (
                _setup_numbered_name(base_name, occurrence[base_name])
                if model_count > 1 else _clean_setup_name(model.get("name"))
            )
            targets.append({
                "card": copy.deepcopy(card),
                "model": model,
                "model_name": final_name,
                "base_name": base_name,
                "duplicate_index": occurrence[base_name],
                "duplicate_count": model_count,
            })
        return targets, renames

    def _setup_board_projected_rect(
        self,
        model: dict[str, Any],
        position: dict[str, float],
    ) -> tuple[float, float, float, float]:
        raw = model.get("bounds") or {}
        size = raw.get("size") or {}
        try:
            sx, sz = abs(float(size.get("x", 0))), abs(float(size.get("z", 0)))
        except (TypeError, ValueError) as exc:
            raise KillTeamSetupError("model bounds size is invalid") from exc
        if sx <= 0 or sz <= 0:
            bounds = _bounds(model)
            if bounds is None:
                raise KillTeamSetupError("model is missing usable bounds")
            sx, sz = bounds[1] - bounds[0], bounds[3] - bounds[2]
        return (
            float(position["x"]) - sx / 2,
            float(position["x"]) + sx / 2,
            float(position["z"]) - sz / 2,
            float(position["z"]) + sz / 2,
        )

    def _setup_board_model_height(self, model: dict[str, Any]) -> float:
        height = model.get("height")
        if height is not None:
            try:
                return max(0.0, float(height))
            except (TypeError, ValueError):
                pass
        raw = model.get("bounds") or {}
        size = raw.get("size") or {}
        try:
            return max(0.0, abs(float(size.get("y", 0))))
        except (TypeError, ValueError):
            bounds = _bounds_box(model.get("object") or model)
            if bounds is None:
                raise KillTeamSetupError("model is missing usable height")
            return max(0.0, bounds["max_y"] - bounds["min_y"])

    def _setup_board_slot_support(
        self,
        snapshot: dict[str, Any],
        rect: tuple[float, float, float, float],
    ) -> dict[str, Any]:
        support_height = float(snapshot["deployment_floor_y"])
        support_sources: list[dict[str, Any]] = []
        for support in snapshot["support_surfaces"]:
            if not _rects_overlap(rect, support["bounds"]):
                continue
            top_y = float(support["max_y"])
            if top_y > support_height + 1e-6:
                support_height = top_y
                support_sources = [copy.deepcopy(support)]
            elif abs(top_y - support_height) <= 1e-6:
                support_sources.append(copy.deepcopy(support))
        support_sources.sort(key=lambda item: str(item["guid"]))
        return {
            "support_height": support_height,
            "support_sources": support_sources,
        }

    def _setup_board_slot_context(
        self,
        snapshot: dict[str, Any],
        model: dict[str, Any],
        position: dict[str, float],
        *,
        clearance: float,
        target_guids: set[str],
        placed_guids: set[str],
        current_guid: str | None = None,
    ) -> dict[str, Any]:
        rect = self._setup_board_projected_rect(model, position)
        support = self._setup_board_slot_support(snapshot, rect)
        model_height = self._setup_board_model_height(model)
        support_height = float(support["support_height"])
        candidate_span = (support_height, support_height + model_height)
        blockers = self._setup_board_slot_blockers(
            snapshot,
            rect=rect,
            target_guids=target_guids,
            placed_guids=placed_guids,
            current_guid=current_guid,
            candidate_span=candidate_span,
        )
        ok, evidence = self._setup_board_rect_legality(
            rect,
            deployment_bounds=snapshot["deployment_bounds"],
            clearance=clearance,
            blockers=blockers,
            candidate_span=candidate_span,
        )
        projected_position = {
            "x": round(float(position["x"]), 6),
            "y": round(support_height + model_height / 2, 6),
            "z": round(float(position["z"]), 6),
        }
        return {
            "ok": ok,
            "evidence": evidence,
            "projected_position": projected_position,
            "projected_rect": rect,
            "support_height": support_height,
            "support_sources": support["support_sources"],
            "blockers": blockers,
            "candidate_span": candidate_span,
            "model_height": model_height,
        }

    def _setup_board_supported_position(
        self,
        snapshot: dict[str, Any],
        model: dict[str, Any],
        position: dict[str, float],
    ) -> dict[str, float]:
        support = self._setup_board_slot_support(snapshot, self._setup_board_projected_rect(model, position))
        model_height = self._setup_board_model_height(model)
        return {
            "x": round(float(position["x"]), 6),
            "y": round(float(support["support_height"]) + model_height / 2, 6),
            "z": round(float(position["z"]), 6),
        }

    def _terrain_support_surfaces(self, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        support_surfaces: list[dict[str, Any]] = []
        for obj in objects:
            if not _is_terrain_surface(obj):
                continue
            box = _bounds_box(obj)
            if box is None:
                continue
            support_surfaces.append({
                "guid": str(obj.get("guid") or ""),
                "name": str(obj.get("name") or ""),
                "bounds": _rect_dict(box["rect"]),
                "min_y": box["min_y"],
                "max_y": box["max_y"],
            })
        support_surfaces.sort(key=lambda item: str(item["guid"]))
        return support_surfaces

    def _setup_board_slot_blockers(
        self,
        snapshot: dict[str, Any],
        *,
        rect: tuple[float, float, float, float],
        target_guids: set[str],
        placed_guids: set[str],
        candidate_span: tuple[float, float],
        current_guid: str | None = None,
    ) -> list[dict[str, Any]]:
        blockers = []
        for blocker in snapshot["blockers"]:
            guid = blocker["guid"]
            if guid == current_guid:
                continue
            if guid in target_guids and guid not in placed_guids:
                continue
            if not _rects_overlap(rect, blocker["bounds"]):
                continue
            blocker_span = (float(blocker["min_y"]), float(blocker["max_y"]))
            if not _y_spans_overlap(candidate_span, blocker_span):
                continue
            blockers.append(blocker)
        return blockers

    def _setup_board_rect_legality(
        self,
        rect: tuple[float, float, float, float],
        *,
        deployment_bounds: tuple[float, float, float, float],
        clearance: float,
        blockers: list[dict[str, Any]],
        candidate_span: tuple[float, float] | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        inflated = _inflated_rect(rect, clearance)
        hits = []
        if not _rect_contains_rect(deployment_bounds, inflated):
            hits.append({"kind": "deployment_bounds", "bounds": _rect_dict(deployment_bounds)})
        for blocker in blockers:
            blocker_bounds = blocker["bounds"]
            if _rects_overlap(inflated, blocker_bounds):
                if candidate_span is not None:
                    blocker_span = (
                        float(blocker.get("min_y", 0.0)),
                        float(blocker.get("max_y", 0.0)),
                    )
                    if not _y_spans_overlap(candidate_span, blocker_span):
                        continue
                hits.append({
                    "kind": "blocker",
                    "guid": blocker["guid"],
                    "name": blocker["name"],
                    "entity": blocker["entity"],
                    "bounds": _rect_dict(_rect_tuple(blocker_bounds)),
                })
        return not hits, hits

    def _setup_board_generate_slots(
        self,
        snapshot: dict[str, Any],
        targets: list[dict[str, Any]],
        *,
        clearance: float,
    ) -> list[dict[str, Any]]:
        deployment_bounds = snapshot["deployment_bounds"]
        target_guids = {str(item["model"]["guid"]) for item in targets}
        assigned_rects: list[dict[str, Any]] = []
        placements: list[dict[str, Any]] = []
        tested: list[dict[str, Any]] = []
        for target in targets:
            model = target["model"]
            current = _position(model)
            raw_size = (model.get("bounds") or {}).get("size") or {}
            size_x = abs(float(raw_size.get("x", 1) or 1))
            size_z = abs(float(raw_size.get("z", 1) or 1))
            x = deployment_bounds[0] + size_x / 2 + clearance
            z = deployment_bounds[2] + size_z / 2 + clearance
            step_x = max(0.1, size_x + 2 * clearance)
            step_z = max(0.1, size_z + 2 * clearance)
            found: dict[str, float] | None = None
            chosen_context: dict[str, Any] | None = None
            while z <= deployment_bounds[3] - size_z / 2 - clearance + 1e-6 and found is None:
                x = deployment_bounds[0] + size_x / 2 + clearance
                while x <= deployment_bounds[1] - size_x / 2 - clearance + 1e-6:
                    position = {"x": round(x, 6), "y": current["y"], "z": round(z, 6)}
                    context = self._setup_board_slot_context(
                        snapshot,
                        model,
                        position,
                        clearance=clearance,
                        target_guids=target_guids,
                        placed_guids=set(),
                        current_guid=str(model["guid"]),
                    )
                    rect = context["projected_rect"]
                    blockers = context["blockers"] + [
                        {
                            "guid": item["guid"],
                            "name": item["name"],
                            "entity": "planned_model",
                            "bounds": item["rect"],
                            "min_y": item["min_y"],
                            "max_y": item["max_y"],
                            "team": self.config.ai_team,
                            "visible": True,
                        }
                        for item in assigned_rects
                    ]
                    ok, evidence = self._setup_board_rect_legality(
                        rect,
                        deployment_bounds=deployment_bounds,
                        clearance=clearance,
                        blockers=blockers,
                        candidate_span=context["candidate_span"],
                    )
                    tested.append({
                        "guid": str(model["guid"]),
                        "position": copy.deepcopy(position),
                        "support_height": context["support_height"],
                        "support_sources": [
                            {
                                "guid": item["guid"],
                                "name": item["name"],
                                "max_y": item["max_y"],
                            }
                            for item in context["support_sources"]
                        ],
                        "ok": ok,
                        "blockers": evidence[:5],
                    })
                    if ok:
                        found = context["projected_position"]
                        chosen_context = context
                        assigned_rects.append({
                            "guid": str(model["guid"]),
                            "name": target["model_name"],
                            "rect": _inflated_rect(rect, clearance),
                            "min_y": context["candidate_span"][0],
                            "max_y": context["candidate_span"][1],
                        })
                        break
                    x += step_x
                z += step_z
            if found is None:
                raise KillTeamSetupError(
                    "no legal setup slot for "
                    f"{target['model_name']}; tested={tested[-20:]}; "
                    f"zone_bounds={_rect_dict(deployment_bounds)}; "
                    f"footprint={{'x': {size_x}, 'z': {size_z}, 'clearance': {clearance}}}; "
                    f"assigned={assigned_rects}"
                )
            assert chosen_context is not None
            placements.append({
                "card_guid": target["card"]["guid"],
                "card_name": target["card"]["name"],
                "card_layout_index": target["card"]["layout_index"],
                "model_guid": str(model["guid"]),
                "model_name": target["model_name"],
                "base_name": target["base_name"],
                "duplicate_index": target["duplicate_index"],
                "duplicate_count": target["duplicate_count"],
                "original_name": _clean_setup_name(model.get("name")),
                "original_locked": bool(model.get("locked", False)),
                "original_position": _position(model),
                "original_bounds_size": copy.deepcopy((model.get("bounds") or {}).get("size") or {}),
                "target_position": found,
                "support_height": chosen_context["support_height"],
                "support_sources": [
                    {
                        "guid": item["guid"],
                        "name": item["name"],
                        "max_y": item["max_y"],
                    }
                    for item in chosen_context["support_sources"]
                ],
                "target_rect": _rect_dict(chosen_context["projected_rect"]),
            })
        return placements

    def _validate_setup_board_plan_current(self, plan: dict[str, Any]) -> dict[str, Any]:
        snapshot = self._setup_board_snapshot(str(plan["roster_zone_guid"]))
        if snapshot["map_revision"] != plan["map_revision"]:
            raise KillTeamRuleError("setup board plan is stale: map revision changed")
        target_guids = {str(item["model_guid"]) for item in plan["placements"]}
        current_context_revision = self._setup_board_context_revision(snapshot, exclude_guids=target_guids)
        if current_context_revision != plan["placement_context_revision"]:
            raise KillTeamRuleError("setup board plan is stale: placement context changed")
        cards = snapshot["cards"]
        expected_cards = plan["cards"]
        if [
            (card["guid"], card["name"], card["base_name"])
            for card in cards
        ] != [
            (card["guid"], card["name"], card["base_name"])
            for card in expected_cards
        ]:
            raise KillTeamRuleError("setup board plan is stale: roster card order changed")
        by_guid = {str(obj["guid"]): obj for obj in snapshot["models"]}
        for placement in plan["placements"]:
            live = by_guid.get(str(placement["model_guid"]))
            if live is None:
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} is missing")
            if _clean_setup_name(live.get("name")) != placement["original_name"]:
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} name changed")
            if bool(live.get("locked", False)) != bool(placement["original_locked"]):
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} lock state changed")
            live_box = _bounds_box(live)
            if live_box is None:
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} bounds changed")
            live_size = live_box["size"]
            original_size = placement.get("original_bounds_size") or {}
            if any(
                abs(float(live_size[axis]) - float(original_size.get(axis, 0))) > 0.01
                for axis in ("x", "y", "z")
            ):
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} bounds changed")
            live_position = _position(live)
            original_position = placement["original_position"]
            if any(abs(live_position[axis] - float(original_position[axis])) > 0.01 for axis in ("x", "y", "z")):
                raise KillTeamRuleError(f"setup board plan is stale: model {placement['model_guid']} moved")
        if _rect_dict(snapshot["deployment_bounds"]) != plan["deployment_zone"]["bounds"]:
            raise KillTeamRuleError("setup board plan is stale: deployment zone bounds changed")
        return snapshot

    def plan_setup_board(
        self,
        *,
        roster_zone_guid: str = "",
        clearance: float = 0.25,
    ) -> dict[str, Any]:
        clearance = float(clearance)
        if clearance < 0:
            raise KillTeamSetupError("setup board clearance must be non-negative")
        profile = self._fixture_profile
        if profile is None:
            raise KillTeamSetupError("setup board planning requires the Save 131 fixture profile")
        roster_zone_guid = roster_zone_guid.strip().lower() or profile.setup_roster_zone_guid
        snapshot = self._setup_board_snapshot(roster_zone_guid)
        targets, renames = self._setup_board_targets(snapshot)
        placements = self._setup_board_generate_slots(snapshot, targets, clearance=clearance)
        plan_id = uuid.uuid4().hex[:12]
        target_guids = {str(item["model"]["guid"]) for item in targets}
        plan = {
            "status": "planned",
            "schema_version": 1,
            "plan_id": plan_id,
            "fixture_profile": profile.name,
            "roster_zone_guid": roster_zone_guid,
            "roster_order_source": snapshot["roster_order_source"],
            "clearance": clearance,
            "revision": len(self._setup_board_plans) + 1,
            "map_revision": snapshot["map_revision"],
            "placement_context_revision": self._setup_board_context_revision(
                snapshot,
                exclude_guids=target_guids,
            ),
            "cards": copy.deepcopy(snapshot["cards"]),
            "deployment_zone": {
                "guid": str(snapshot["deployment"].get("guid")),
                "name": str(snapshot["deployment"].get("name") or ""),
                "bounds": _rect_dict(snapshot["deployment_bounds"]),
                "position": _position(snapshot["deployment"]),
                "floor_y": snapshot["deployment_floor_y"],
                "top_y": snapshot["deployment_top_y"],
            },
            "combat_center": copy.deepcopy(snapshot["combat_center"]),
            "renames": renames,
            "models_to_unlock": [
                {
                    "guid": item["model_guid"],
                    "name": item["original_name"],
                }
                for item in placements if item["original_locked"]
            ],
            "placements": placements,
            "blockers": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "entity": item["entity"],
                    "bounds": _rect_dict(_rect_tuple(item["bounds"])),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                    "team": item.get("team", ""),
                }
                for item in snapshot["blockers"]
            ],
            "support_surfaces": [
                {
                    "guid": item["guid"],
                    "name": item["name"],
                    "bounds": _rect_dict(_rect_tuple(item["bounds"])),
                    "min_y": item["min_y"],
                    "max_y": item["max_y"],
                }
                for item in snapshot["support_surfaces"]
            ],
            "executed": False,
        }
        self._setup_board_plans[plan_id] = copy.deepcopy(plan)
        return copy.deepcopy(plan)

    def execute_setup_board(self, plan_id: str) -> dict[str, Any]:
        plan_id = str(plan_id or "").strip()
        if not plan_id:
            raise KillTeamRuleError("setup board plan_id is required")
        plan = self._setup_board_plans.get(plan_id)
        if plan is None:
            raise KillTeamRuleError(f"unknown or expired setup board plan {plan_id}")
        if plan.get("executed"):
            raise KillTeamRuleError(f"setup board plan {plan_id} has already executed")
        completed: list[dict[str, Any]] = []

        def fail(phase: str, placement: dict[str, Any] | None, exc: Exception) -> dict[str, Any]:
            return {
                "status": "failed",
                "plan_id": plan_id,
                "failed_phase": phase,
                "failed_model": copy.deepcopy(placement) if placement else None,
                "error": str(exc),
                "completed": completed,
                "stopped": True,
            }

        try:
            snapshot = self._validate_setup_board_plan_current(plan)
        except Exception as exc:
            return fail("preflight", None, exc)

        target_guids = {str(item["model_guid"]) for item in plan["placements"]}
        try:
            for unlock in plan["models_to_unlock"]:
                guid = str(unlock["guid"])
                projected = self.bridge.set_object_lock(guid, False)
                if bool(projected.get("locked", False)):
                    raise KillTeamRuleError(f"model {guid} did not unlock")
            for rename in plan["renames"]:
                projected = self.bridge.set_object_name(str(rename["guid"]), str(rename["to"]))
                if _clean_setup_name(projected.get("name")) != str(rename["to"]):
                    raise KillTeamRuleError(f"model {rename['guid']} rename did not verify")
            snapshot = self._setup_board_snapshot(str(plan["roster_zone_guid"]))
            if self._setup_board_context_revision(snapshot, exclude_guids=target_guids) != plan["placement_context_revision"]:
                raise KillTeamRuleError("setup board plan is stale: placement context changed")
            live_by_guid = {str(obj["guid"]): obj for obj in snapshot["models"]}
            for placement in plan["placements"]:
                live = live_by_guid.get(str(placement["model_guid"]))
                if live is None:
                    raise KillTeamRuleError(f"model {placement['model_guid']} is missing after rename")
                if _clean_setup_name(live.get("name")) != placement["model_name"]:
                    raise KillTeamRuleError(f"model {placement['model_guid']} identity did not verify after rename")
                live_box = _bounds_box(live)
                if live_box is None:
                    raise KillTeamRuleError(f"model {placement['model_guid']} bounds are unavailable after rename")
                live_size = live_box["size"]
                original_size = placement.get("original_bounds_size") or {}
                if any(
                    abs(float(live_size[axis]) - float(original_size.get(axis, 0))) > 0.01
                    for axis in ("x", "y", "z")
                ):
                    raise KillTeamRuleError(f"model {placement['model_guid']} bounds changed after rename")
        except Exception as exc:
            return fail("prepare", None, exc)

        placed_guids: set[str] = set()
        for placement in plan["placements"]:
            try:
                live = next(
                    obj for obj in snapshot["models"]
                    if str(obj["guid"]) == str(placement["model_guid"])
                )
                live_box = _bounds_box(live)
                if live_box is None:
                    raise KillTeamRuleError(f"model {placement['model_guid']} bounds are unavailable during execution")
                live_height = live_box["max_y"] - live_box["min_y"]
                candidate_span = (
                    float(placement["support_height"]),
                    float(placement["support_height"]) + live_height,
                )
                rect = self._setup_board_projected_rect(live, placement["target_position"])
                blockers = self._setup_board_slot_blockers(
                    snapshot,
                    rect=rect,
                    target_guids=target_guids,
                    placed_guids=placed_guids,
                    current_guid=str(placement["model_guid"]),
                    candidate_span=candidate_span,
                )
                ok, evidence = self._setup_board_rect_legality(
                    rect,
                    deployment_bounds=(
                        plan["deployment_zone"]["bounds"]["min_x"],
                        plan["deployment_zone"]["bounds"]["max_x"],
                        plan["deployment_zone"]["bounds"]["min_z"],
                        plan["deployment_zone"]["bounds"]["max_z"],
                    ),
                    clearance=float(plan["clearance"]),
                    blockers=blockers,
                    candidate_span=candidate_span,
                )
                if not ok:
                    raise KillTeamRuleError(f"frozen setup coordinate is blocked: {evidence[:5]}")
                projected = self.bridge.move_object(
                    str(placement["model_guid"]),
                    copy.deepcopy(placement["target_position"]),
                )
                actual = _position(projected if isinstance(projected, dict) else self.bridge.get_object(str(placement["model_guid"])))
                if any(abs(actual[axis] - float(placement["target_position"][axis])) > 0.05 for axis in ("x", "y", "z")):
                    raise KillTeamUncertainCommit("setup model move did not verify")
                completed.append({
                    "model_guid": placement["model_guid"],
                    "model_name": placement["model_name"],
                    "position": actual,
                })
                placed_guids.add(str(placement["model_guid"]))
                snapshot = self._setup_board_snapshot(str(plan["roster_zone_guid"]))
            except Exception as exc:
                return fail("move", placement, exc)
        plan["executed"] = True
        self._setup_board_plans[plan_id] = plan
        return {
            "status": "executed",
            "plan_id": plan_id,
            "completed": completed,
            "renames": copy.deepcopy(plan["renames"]),
            "unlocked": copy.deepcopy(plan["models_to_unlock"]),
            "stopped": False,
        }

    def _require_state(self) -> dict[str, Any]:
        if self._state is None:
            raise KillTeamSetupError("Kill Team setup has not completed")
        return self._state

    def _visible_operatives(self) -> dict[str, dict[str, Any]]:
        state = self._require_state()
        visible: dict[str, dict[str, Any]] = {}
        for operative_id, record in state["operatives"].items():
            obj = self._objects.get(record["guid"], {})
            if record["team"] == self.config.ai_team or self._is_visible(obj, _metadata(obj)):
                visible[operative_id] = copy.deepcopy(record)
        return visible

    def _setup_profile_for_faction(self, faction_id: str) -> KillTeamSetupFactionProfile:
        profile = _SETUP_FACTION_PROFILES.get(_norm(faction_id))
        if profile is None:
            raise KillTeamSetupError(f"unsupported setup faction {faction_id}")
        return profile

    def _setup_side_id(
        self,
        metadata: dict[str, str],
        obj: dict[str, Any] | None = None,
        fallback_side_id: str | None = None,
    ) -> str:
        side_id = _norm(metadata.get("side_id") or metadata.get("team"))
        if not side_id and fallback_side_id is not None:
            side_id = _norm(fallback_side_id)
        if not side_id and obj is not None:
            side_id = self._setup_generic_side_id(obj)
        if not side_id:
            raise KillTeamSetupError("setup object is missing side_id metadata")
        return side_id

    def _setup_identity(self, metadata: dict[str, str], *, entity_label: str) -> dict[str, str]:
        operative_type_id = _norm(metadata.get("operative_type_id"))
        instance_id = str(metadata.get("instance_id") or "").strip()
        faction_id = _norm(metadata.get("faction_id"))
        operative_id = str(metadata.get("operative_id") or "").strip()
        if not operative_type_id or not instance_id or not faction_id:
            raise KillTeamSetupError(
                f"{entity_label} requires operative_type_id, instance_id, and faction_id metadata"
            )
        if not operative_id:
            operative_id = f"{operative_type_id}#{instance_id}"
        return {
            "operative_id": operative_id,
            "operative_type_id": operative_type_id,
            "instance_id": instance_id,
            "faction_id": faction_id,
            "role": _norm(metadata.get("role")),
            "card_kind": _norm(metadata.get("card_kind")) or "operative",
        }

    @staticmethod
    def _setup_card_kind(metadata: dict[str, str]) -> str:
        card_kind = _norm(metadata.get("card_kind"))
        if card_kind:
            return card_kind
        if _norm(metadata.get("entity")) == "roster_card":
            return "operative"
        return ""

    def _setup_card_from_object(
        self,
        obj: dict[str, Any],
        side_id: str | None = None,
    ) -> dict[str, Any]:
        metadata = _metadata(obj)
        if _norm(metadata.get("entity")) != "roster_card":
            raise KillTeamSetupError("setup card object is missing roster_card metadata")
        identity = self._setup_identity(metadata, entity_label="roster card")
        identity.update({
            "guid": str(obj.get("guid") or ""),
            "side_id": self._setup_side_id(metadata, obj, side_id),
            "name": str(obj.get("name") or identity["operative_id"]),
            "tags": copy.deepcopy(obj.get("tags", [])),
            "card_kind": self._setup_card_kind(metadata),
        })
        return identity

    def _setup_card_from_container_item(
        self,
        item: dict[str, Any],
        side_id: str | None = None,
    ) -> dict[str, Any]:
        metadata = _tag_metadata(item.get("tags"))
        if _norm(metadata.get("entity")) != "roster_card":
            raise KillTeamSetupError("contained setup card is missing roster_card metadata")
        identity = self._setup_identity(metadata, entity_label="contained roster card")
        identity.update({
            "guid": str(item.get("guid") or ""),
            "side_id": self._setup_side_id(metadata, item, side_id),
            "name": str(item.get("name") or identity["operative_id"]),
            "tags": copy.deepcopy(item.get("tags", [])),
            "card_kind": self._setup_card_kind(metadata),
        })
        return identity

    def _setup_model_from_container_item(
        self,
        item: dict[str, Any],
        side_id: str | None = None,
    ) -> dict[str, Any]:
        metadata = _tag_metadata(item.get("tags"))
        if _norm(metadata.get("entity")) != "operative":
            raise KillTeamSetupError("contained setup model is missing operative metadata")
        identity = self._setup_identity(metadata, entity_label="contained operative")
        embedded_object = item.get("object")
        if not isinstance(embedded_object, dict):
            embedded_object = None
        identity.update({
            "guid": str(item.get("guid") or ""),
            "side_id": self._setup_side_id(metadata, embedded_object or item, side_id),
            "name": str(item.get("name") or identity["operative_id"]),
            "tags": copy.deepcopy(item.get("tags", [])),
            "type": str((embedded_object or {}).get("type") or "Figurine"),
            "position": copy.deepcopy((embedded_object or {}).get("position")) if embedded_object is not None else None,
            "bounds": copy.deepcopy((embedded_object or {}).get("bounds")) if embedded_object is not None else None,
            "object": copy.deepcopy(embedded_object) if embedded_object is not None else None,
        })
        return identity

    def _setup_selected_cards(
        self,
        zone_guid: str,
        side_id: str | None = None,
        card_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            zone = self.bridge.get_zone_objects(zone_guid)
        except Exception as exc:
            raise KillTeamSetupError(f"setup zone {zone_guid} could not be inspected") from exc
        objects = zone.get("objects", []) if isinstance(zone, dict) else []
        if not isinstance(objects, list):
            raise KillTeamSetupError(f"setup zone {zone_guid} returned invalid contents")
        cards = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            metadata = _metadata(obj)
            if _norm(metadata.get("entity")) != "roster_card":
                continue
            card = self._setup_card_from_object(obj, side_id)
            if card_kind is not None and _norm(card.get("card_kind")) != _norm(card_kind):
                continue
            cards.append(card)
        return cards

    def _setup_container_items(self, container_guid: str) -> list[dict[str, Any]]:
        try:
            container = self.bridge.inspect_container(container_guid)
        except Exception as exc:
            raise KillTeamSetupError(f"setup container {container_guid} could not be inspected") from exc
        items = container.get("items", []) if isinstance(container, dict) else []
        if not isinstance(items, list):
            raise KillTeamSetupError(f"setup container {container_guid} returned invalid contents")
        return [copy.deepcopy(item) for item in items if isinstance(item, dict)]

    def _setup_zone_bounds(self, zone_guid: str) -> tuple[float, float, float, float]:
        zone = self._objects.get(zone_guid)
        bounds = _bounds(zone or {})
        if zone is None or bounds is None:
            raise KillTeamSetupError(f"setup zone {zone_guid} is missing bounds")
        return bounds

    def _setup_zone_center(self, zone_guid: str) -> dict[str, float]:
        zone = self._objects.get(zone_guid) or {}
        center = (zone.get("bounds") or {}).get("center") or zone.get("position") or {}
        return {axis: _number(center.get(axis, 0), f"{zone_guid}.{axis}") for axis in ("x", "y", "z")}

    def _initiative_token_anchor(self, side_id: str) -> dict[str, float]:
        """Return a visible anchor for the initiative token for the given side."""
        state = self._require_state()
        normalized_side = _norm(side_id)
        setup_state = state.get("setup")
        candidate_guids: list[str] = []
        if isinstance(setup_state, dict):
            side = setup_state.get("sides", {}).get(normalized_side)
            if isinstance(side, dict):
                for key in ("deployed_zone_guid", "deployment_zone_guid", "roster_list_zone_guid"):
                    guid = str(side.get(key) or "").strip()
                    if guid:
                        candidate_guids.append(guid)
        for key in ("deployment_zone_guid", "combat_zone_guid"):
            guid = str(state.get(key) or "").strip()
            if guid:
                candidate_guids.append(guid)
        for guid in candidate_guids:
            if guid in self._objects:
                try:
                    anchor = self._setup_zone_center(guid)
                except KillTeamSetupError:
                    continue
                return anchor
        for record in self._visible_operatives().values():
            if _norm(record.get("team")) == normalized_side:
                position = copy.deepcopy(record.get("position") or {})
                if position:
                    return {axis: _number(position.get(axis, 0), f"initiative.{axis}") for axis in ("x", "y", "z")}
        return {"x": 0.0, "y": 1.0, "z": 0.0}

    def _initiative_token_position(self, side_id: str) -> dict[str, float]:
        anchor = self._initiative_token_anchor(side_id)
        return {
            "x": float(anchor["x"]),
            "y": float(anchor["y"]) + 0.75,
            "z": float(anchor["z"]),
        }

    def _initiative_token_name(self, side_id: str) -> str:
        side_label = str(side_id or "").strip() or "unknown"
        return f"Initiative: {side_label.title()}"

    def _move_initiative_token(self, side_id: str, *, action_id: str | None = None) -> dict[str, Any]:
        state = self._require_state()
        target = self._initiative_token_position(side_id)
        token_guid = _live_object_guid(state.get("initiative_token_guid"))
        token_name = self._initiative_token_name(side_id)
        if token_guid and token_guid in self._objects:
            try:
                moved = self.bridge.move_object(token_guid, target)
                projected = self.bridge.get_object(token_guid)
            except Exception as exc:
                self._mark_uncertain(action_id)
                raise KillTeamUncertainCommit("initiative token movement is uncertain") from exc
            actual = _position(projected)
            if any(abs(actual[axis] - target[axis]) > 0.05 for axis in ("x", "y", "z")):
                self._mark_uncertain(action_id)
                raise KillTeamUncertainCommit("initiative token did not verify at the requested position")
            state["initiative_token_side"] = _norm(side_id)
            state["turn_owner"] = _norm(side_id)
            return {
                "guid": token_guid,
                "name": str(projected.get("name") or token_name),
                "position": actual,
                "object": projected,
                "result": moved,
            }
        try:
            spawned = self.bridge.spawn_builtin(
                object_type="BlockSquare",
                position=target,
                rotation={"x": 0.0, "y": 0.0, "z": 0.0},
                scale={"x": 0.75, "y": 0.15, "z": 0.75},
                name=token_name,
                locked=True,
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative token spawn is uncertain") from exc
        spawned_object = spawned.get("object") if isinstance(spawned, dict) and isinstance(spawned.get("object"), dict) else None
        token_guid = _live_object_guid(spawned_object.get("guid") if spawned_object is not None else spawned.get("guid") if isinstance(spawned, dict) else None)
        if not token_guid:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative token spawn did not return a stable GUID")
        try:
            projected = self.bridge.get_object(token_guid)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative token spawn committed but the readback failed") from exc
        actual = _position(projected)
        if any(abs(actual[axis] - target[axis]) > 0.05 for axis in ("x", "y", "z")):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative token did not verify at the requested position")
        actual_name = str(projected.get("name") or "")
        if actual_name != token_name:
            try:
                projected = self.bridge.set_object_name(token_guid, token_name)
                projected = self.bridge.get_object(token_guid)
            except Exception as exc:
                self._mark_uncertain(action_id)
                raise KillTeamUncertainCommit("initiative token name verification failed") from exc
            actual_name = str(projected.get("name") or "")
            if actual_name != token_name:
                self._mark_uncertain(action_id)
                raise KillTeamUncertainCommit("initiative token did not verify its name")
        state["initiative_token_guid"] = token_guid
        state["initiative_token_side"] = _norm(side_id)
        state["turn_owner"] = _norm(side_id)
        return {
            "guid": token_guid,
            "name": actual_name or token_name,
            "position": actual,
            "object": projected,
            "result": spawned,
        }

    def _validate_partial_setup_cards(
        self,
        cards: list[dict[str, Any]],
    ) -> tuple[KillTeamSetupFactionProfile, str]:
        if not cards:
            raise KillTeamSetupError("at least one roster card is required")
        faction_ids = {_norm(card["faction_id"]) for card in cards}
        if len(faction_ids) != 1:
            raise KillTeamRuleError("selected roster cards must share one faction")
        faction_id = next(iter(faction_ids))
        profile = self._setup_profile_for_faction(faction_id)
        if len(cards) > profile.exact_team_size:
            raise KillTeamRuleError("selected roster card count exceeds the faction team size")
        counts: dict[str, int] = {}
        leader_count = 0
        seen_operatives: set[str] = set()
        for card in cards:
            operative_id = card["operative_id"]
            if operative_id in seen_operatives:
                raise KillTeamRuleError(f"duplicate selected operative {operative_id}")
            seen_operatives.add(operative_id)
            type_id = _norm(card["operative_type_id"])
            counts[type_id] = counts.get(type_id, 0) + 1
            if type_id in profile.leader_type_ids:
                leader_count += 1
            limit = None
            if type_id in profile.unlimited_type_ids:
                limit = profile.exact_team_size
            elif profile.per_type_limits and type_id in profile.per_type_limits:
                limit = int(profile.per_type_limits[type_id])
            else:
                limit = int(profile.default_limit)
            if counts[type_id] > limit:
                raise KillTeamRuleError(
                    f"duplicate limit exceeded for {type_id}"
                )
        if leader_count > 1:
            raise KillTeamRuleError("selected roster cards exceed the faction leader limit")
        return profile, faction_id

    def _validate_locked_setup_cards(
        self,
        cards: list[dict[str, Any]],
    ) -> tuple[KillTeamSetupFactionProfile, str]:
        profile, faction_id = self._validate_partial_setup_cards(cards)
        if len(cards) != profile.exact_team_size:
            raise KillTeamRuleError(
                f"roster list requires exactly {profile.exact_team_size} operatives"
            )
        leader_count = sum(
            1 for card in cards if _norm(card["operative_type_id"]) in profile.leader_type_ids
        )
        if leader_count != 1:
            raise KillTeamRuleError("roster list requires exactly one leader")
        return profile, faction_id

    def _setup_side_objects(self) -> dict[str, dict[str, str]]:
        sides: dict[str, dict[str, str]] = {}
        required_entities = {
            "faction_decks",
            "roster",
            "roster_list_zone",
            "deployed_zone",
            "deployment",
        }
        for guid, obj in self._objects.items():
            metadata = _metadata(obj)
            entity = _norm(metadata.get("entity"))
            if entity not in required_entities:
                continue
            side_id = self._setup_side_id(metadata, obj)
            sides.setdefault(side_id, {})
            if entity in sides[side_id]:
                raise KillTeamSetupError(f"setup side {side_id} has duplicate {entity} objects")
            sides[side_id][entity] = guid
        if not sides:
            return {}
        for side_id, mapping in sides.items():
            missing = sorted(required_entities - mapping.keys())
            if missing:
                raise KillTeamSetupError(
                    f"setup side {side_id} is missing {', '.join(missing)}"
                )
        if self.config.ai_team.lower() not in sides:
            raise KillTeamSetupError("the AI setup side is missing required tagged objects")
        if len(sides) < 2:
            raise KillTeamSetupError("Kill Team setup requires two tagged sides")
        return sides

    def _setup_mode_enabled(self, side_objects: dict[str, dict[str, str]]) -> bool:
        return bool(side_objects)

    def _setup_clean_start(self, side_objects: dict[str, dict[str, str]]) -> None:
        for side_id, mapping in side_objects.items():
            roster_cards = self._setup_selected_cards(mapping["roster_list_zone"], side_id)
            deployed_cards = self._setup_selected_cards(mapping["deployed_zone"], side_id)
            if roster_cards:
                raise KillTeamSetupError(f"Roster List for {side_id} must start empty")
            if deployed_cards:
                raise KillTeamSetupError(f"Deployed Zone for {side_id} must start empty")
        live_setup_operatives = [
            guid
            for guid, obj in self._objects.items()
            if _norm(_metadata(obj).get("entity")) == "operative"
            and _norm(_metadata(obj).get("side_id") or _metadata(obj).get("team")) in side_objects
        ]
        if live_setup_operatives:
            raise KillTeamSetupError("setup requires all selected operatives to remain in roster containers")

    @staticmethod
    def _setup_batch_size(selected_count: int) -> int:
        """Kill Team alternates setup in one-third batches, rounded up."""
        return max(1, math.ceil(max(0, int(selected_count)) / 3))

    def _setup_start_from_roster_models(self, setup_state: dict[str, Any]) -> None:
        """Start deployment directly from the tagged model containers."""
        for side_id, side in setup_state["sides"].items():
            models = [
                self._setup_model_from_container_item(item, side_id)
                for item in self._setup_container_items(side["roster_container_guid"])
            ]
            models = [model for model in models if _norm(model["side_id"]) == side_id]
            if not models:
                raise KillTeamSetupError(f"roster container for {side_id} contains no operative models")
            if side_id == self.config.ai_team:
                models.sort(key=self._setup_ai_order_key)
            profile = self._setup_profile_for_faction(models[0]["faction_id"])
            if len(models) < profile.exact_team_size:
                raise KillTeamSetupError(
                    f"roster container for {side_id} has {len(models)} models; "
                    f"{profile.exact_team_size} are required"
                )
            selected_models = models[:profile.exact_team_size]
            self._validate_locked_setup_cards(selected_models)
            side["locked"] = True
            side["faction_id"] = profile.faction_id
            side["selected_operatives"] = {
                model["operative_id"]: copy.deepcopy(model)
                for model in selected_models
            }
            side["deployed_operatives"] = {}
            side["batch_size"] = self._setup_batch_size(len(selected_models))
        setup_state["mode"] = "model_deployment"
        setup_state["stage"] = "deployment"
        setup_state["current_side"] = setup_state["initiative_side"]
        first_side = setup_state["sides"][setup_state["current_side"]]
        setup_state["current_batch_target"] = min(
            int(first_side["batch_size"]),
            len(first_side["selected_operatives"]),
        )
        setup_state["current_batch_progress"] = 0

    def _setup_snapshot(self, state: dict[str, Any]) -> dict[str, Any] | None:
        setup_state = state.get("setup")
        if not isinstance(setup_state, dict):
            return None
        result = {
            "mode": setup_state["mode"],
            "stage": setup_state["stage"],
            "initiative_side": setup_state["initiative_side"],
            "current_side": setup_state.get("current_side"),
            "current_batch_target": setup_state.get("current_batch_target", 0),
            "current_batch_progress": setup_state.get("current_batch_progress", 0),
            "pending_side": setup_state.get("pending_side"),
            "pending_operative_id": setup_state.get("pending_operative_id"),
            "pending_model_guid": setup_state.get("pending_model_guid"),
            "sides": {},
        }
        for side_id, side in setup_state["sides"].items():
            selected = side.get("selected_operatives", {})
            selected_cards = self._setup_selected_cards(side["roster_list_zone_guid"], side_id)
            selected_card_counts: dict[str, int] = {}
            for card in selected_cards:
                kind = _norm(card.get("card_kind")) or "unknown"
                selected_card_counts[kind] = selected_card_counts.get(kind, 0) + 1
            deployed = side.get("deployed_operatives", {})
            result["sides"][side_id] = {
                "faction_decks_guid": side["faction_decks_guid"],
                "roster_container_guid": side["roster_container_guid"],
                "roster_list_zone_guid": side["roster_list_zone_guid"],
                "deployed_zone_guid": side["deployed_zone_guid"],
                "deployment_zone_guid": side["deployment_zone_guid"],
                "locked": bool(side.get("locked")),
                "faction_id": side.get("faction_id", ""),
                "selected_count": len(selected),
                "selected_setup_count": max(0, len(selected_cards) - len(selected)),
                "selected_card_counts": selected_card_counts,
                "deployed_count": len(deployed),
                "remaining_count": max(0, len(selected) - len(deployed)),
                "batch_size": int(side.get("batch_size", 0)),
            }
        ai_plan = self._setup_ai_plan(state)
        if ai_plan is not None:
            result["ai_plan"] = ai_plan
            if setup_state["stage"] == "roster_selection" and ai_plan.get("next_selection"):
                next_selection = copy.deepcopy(ai_plan["next_selection"])
                next_type = "select_roster_card" if _norm(next_selection.get("card_kind")) == "operative" else "select_setup_card"
                result["next_action"] = {
                    "type": next_type,
                    "side_id": self.config.ai_team,
                    **next_selection,
                }
            elif setup_state["stage"] == "deployment":
                if setup_state.get("current_side") == self.config.ai_team and ai_plan.get("next_deployment"):
                    result["next_action"] = {
                        "type": "deploy_ai_operative",
                        "side_id": self.config.ai_team,
                        "batch_target": int(setup_state.get("current_batch_target", 0)),
                        "batch_progress": int(setup_state.get("current_batch_progress", 0)),
                        **copy.deepcopy(ai_plan["next_deployment"]),
                    }
                elif setup_state.get("current_side"):
                    result["next_action"] = {
                        "type": "await_human_deployment",
                        "side_id": setup_state["current_side"],
                        "batch_target": int(setup_state.get("current_batch_target", 0)),
                        "batch_progress": int(setup_state.get("current_batch_progress", 0)),
                    }
        return result

    @staticmethod
    def _setup_ai_role(record: dict[str, Any]) -> tuple[int, str]:
        text = " ".join(
            str(value).casefold()
            for value in (
                record.get("operative_id", ""),
                record.get("profile_id", ""),
                record.get("name", ""),
                record.get("description", ""),
            )
            if str(value).strip()
        )
        if any(token in text for token in ("leader", "chosen", "champion", "sergeant", "commander")):
            return 0, "leader"
        if any(token in text for token in ("balefire", "icon", "gunner", "specialist", "support")):
            return 1, "specialist"
        if any(token in text for token in ("butcher", "heavy", "brute", "tank")):
            return 2, "heavy"
        return 3, "warrior"

    def _setup_ai_order_key(self, record: dict[str, Any]) -> tuple[int, int, int, int, str]:
        priority, _label = self._setup_ai_role(record)
        profile = record.get("profile") if isinstance(record.get("profile"), dict) else {}
        return (
            priority,
            -int(profile.get("apl", 0)),
            -int(profile.get("move", 0)),
            -int(profile.get("wounds", 0)),
            str(record.get("operative_id", "")),
        )

    def _setup_team_play_style(self, records: list[dict[str, Any]]) -> tuple[str, str]:
        tags = {
            _norm(tag)
            for record in records
            for tag in (record.get("tags", []) if isinstance(record.get("tags"), list) else [])
            if _norm(tag)
        }
        faction_ids = {
            _norm(record.get("faction_id"))
            for record in records
            if _norm(record.get("faction_id"))
        }
        profile_ids = {
            _norm(record.get("profile_id"))
            for record in records
            if _norm(record.get("profile_id"))
        }
        haystack = " ".join(sorted({*tags, *faction_ids, *profile_ids}))
        aggressive_markers = (
            "legionary",
            "chaos",
            "plague",
            "nurgle",
            "khorne",
            "world eater",
            "worldeater",
            "ork",
            "tyranid",
            "genestealer",
        )
        conservative_markers = (
            "tau",
            "t'au",
            "t au",
            "pathfinder",
            "breacher",
            "stealth",
            "kroot",
            "vior",
            "fire caste",
            "battlesuit",
            "crisis",
        )
        if any(marker in haystack for marker in aggressive_markers):
            return "aggressive", "faction tags favor pressure, resilience, or melee trading"
        if any(marker in haystack for marker in conservative_markers):
            return "conservative", "faction tags favor cover, range, or skirmishing"
        return "balanced", "faction tags do not strongly bias the team toward aggression or caution"

    def _setup_slot_support_height(
        self,
        *,
        deployment_floor_y: float,
        rect: tuple[float, float, float, float],
        support_surfaces: list[dict[str, Any]],
    ) -> dict[str, Any]:
        support_height = float(deployment_floor_y)
        support_sources: list[dict[str, Any]] = []
        for support in support_surfaces:
            bounds = support.get("bounds")
            if bounds is None or not _rects_overlap(rect, bounds):
                continue
            top_y = float(support.get("max_y", deployment_floor_y))
            if top_y > support_height + 1e-6:
                support_height = top_y
                support_sources = [copy.deepcopy(support)]
            elif abs(top_y - support_height) <= 1e-6:
                support_sources.append(copy.deepcopy(support))
        support_sources.sort(key=lambda item: str(item.get("guid") or ""))
        return {
            "support_height": support_height,
            "support_sources": support_sources,
        }

    def _setup_ranked_recommended_positions(
        self,
        side: dict[str, Any],
        model_item: dict[str, Any],
        *,
        clearance: float = 0.25,
        play_style: str = "balanced",
    ) -> list[dict[str, Any]]:
        deployment_bounds = self._setup_zone_bounds(side["deployment_zone_guid"])
        deployment_zone = self._objects.get(side["deployment_zone_guid"], {})
        deployment_box = _bounds_box(deployment_zone)
        deployment_floor_y = float((deployment_box or {}).get("min_y", _position(deployment_zone)["y"]))
        zone_position = _position(deployment_zone)
        raw_model = model_item.get("object") if isinstance(model_item.get("object"), dict) else model_item
        raw_bounds = raw_model.get("bounds") if isinstance(raw_model, dict) else None
        raw_size = raw_bounds.get("size") if isinstance(raw_bounds, dict) else None
        try:
            size_x = abs(float((raw_size or {}).get("x", 1.0))) or 1.0
            size_z = abs(float((raw_size or {}).get("z", 1.0))) or 1.0
        except (TypeError, ValueError):
            size_x, size_z = 1.0, 1.0
        model_box = _bounds_box(raw_model if isinstance(raw_model, dict) else {})
        model_height = max(
            0.0,
            float((model_box["max_y"] - model_box["min_y"]) if model_box is not None else (raw_size or {}).get("y", 0) or 0.0),
        )

        opponent_centers = []
        for candidate_side_id, candidate_side in self._require_setup_state()["sides"].items():
            if candidate_side_id == side["side_id"]:
                continue
            candidate_zone = self._objects.get(candidate_side["deployment_zone_guid"])
            if candidate_zone is not None:
                opponent_centers.append(_position(candidate_zone))
        opponent_center = opponent_centers[0] if opponent_centers else None

        objectives = [
            {
                "guid": guid,
                "position": _position(obj),
                "bounds": _bounds_box(obj),
            }
            for guid, obj in self._objects.items()
            if _norm(_metadata(obj).get("entity")) == "objective"
            for bounds in [_bounds_box(obj)]
            if bounds is not None
        ]
        visible_enemies = [
            {
                "guid": record["guid"],
                "position": copy.deepcopy(record["position"]),
            }
            for record in self._visible_operatives().values()
            if _norm(record["team"]) != _norm(self.config.ai_team) and int(record.get("wounds", 0)) > 0
        ]
        friendly_supports = [
            _position(self._objects[str(deployed.get("guid") or "")])
            for deployed in side.get("deployed_operatives", {}).values()
            if str(deployed.get("guid") or "") in self._objects
        ]

        blockers: list[dict[str, Any]] = []
        support_surfaces: list[dict[str, Any]] = []
        for guid, obj in self._objects.items():
            if guid == side["deployment_zone_guid"]:
                continue
            box = _bounds_box(obj)
            if box is None:
                continue
            metadata = _metadata(obj)
            entity = _norm(metadata.get("entity"))
            item = {
                "guid": guid,
                "name": str(obj.get("name") or ""),
                "entity": entity,
                "team": _norm(metadata.get("team")),
                "bounds": _rect_dict(box["rect"]),
                "min_y": box["min_y"],
                "max_y": box["max_y"],
            }
            if _is_terrain_surface(obj):
                support_surfaces.append(item)
            if _is_terrain_surface(obj) or entity in {"objective", "operative"}:
                blockers.append(item)

        assigned: list[dict[str, Any]] = []
        for deployed in side.get("deployed_operatives", {}).values():
            live = self._objects.get(str(deployed.get("guid") or ""))
            box = _bounds_box(live or {}) if live is not None else None
            if box is not None:
                assigned.append({
                    "guid": str(deployed.get("guid") or ""),
                    "bounds": _rect_dict(box["rect"]),
                    "min_y": box["min_y"],
                    "max_y": box["max_y"],
                })

        step_x = max(0.25, size_x + 2 * clearance)
        step_z = max(0.25, size_z + 2 * clearance)
        candidates: list[dict[str, Any]] = []
        x = deployment_bounds[0] + size_x / 2 + clearance
        while x <= deployment_bounds[1] - size_x / 2 - clearance + 1e-6:
            z = deployment_bounds[2] + size_z / 2 + clearance
            while z <= deployment_bounds[3] - size_z / 2 - clearance + 1e-6:
                rect = (
                    x - size_x / 2,
                    x + size_x / 2,
                    z - size_z / 2,
                    z + size_z / 2,
                )
                inflated = _inflated_rect(rect, clearance)
                support = self._setup_slot_support_height(
                    deployment_floor_y=deployment_floor_y,
                    rect=rect,
                    support_surfaces=support_surfaces,
                )
                support_height = float(support["support_height"])
                candidate_span = (support_height, support_height + model_height)
                legal_blockers = []
                for blocker in [*blockers, *assigned]:
                    if not _rects_overlap(inflated, blocker["bounds"]):
                        continue
                    blocker_span = (float(blocker["min_y"]), float(blocker["max_y"]))
                    if not _y_spans_overlap(candidate_span, blocker_span):
                        continue
                    legal_blockers.append(blocker)
                if not _rect_contains_rect(deployment_bounds, inflated) or legal_blockers:
                    z += step_z
                    continue

                exposure = 0
                cover_score = 0
                for enemy in visible_enemies:
                    blocked_by = 0
                    for blocker in blockers:
                        blocker_bounds = blocker["bounds"]
                        if _segment_intersects_rect(
                            {"x": x, "y": support_height, "z": z},
                            enemy["position"],
                            _rect_tuple(blocker_bounds),
                        ):
                            blocked_by += 1
                    if blocked_by == 0:
                        exposure += 1
                    cover_score += blocked_by

                if objectives:
                    objective_distance = min(
                        math.hypot(x - objective["position"]["x"], z - objective["position"]["z"])
                        for objective in objectives
                    )
                elif opponent_center is not None:
                    objective_distance = math.hypot(x - opponent_center["x"], z - opponent_center["z"])
                else:
                    objective_distance = 0.0

                if visible_enemies:
                    threat_distance = min(
                        math.hypot(x - enemy["position"]["x"], z - enemy["position"]["z"])
                        for enemy in visible_enemies
                    )
                elif opponent_center is not None:
                    threat_distance = math.hypot(x - opponent_center["x"], z - opponent_center["z"])
                else:
                    threat_distance = 0.0

                if friendly_supports:
                    friendly_spacing = min(
                        math.hypot(x - friend["x"], z - friend["z"])
                        for friend in friendly_supports
                    )
                else:
                    friendly_spacing = 0.0
                path_distance = math.hypot(x - zone_position["x"], z - zone_position["z"])
                style = _norm(play_style)
                if style == "aggressive":
                    score = (
                        objective_distance,
                        threat_distance,
                        -cover_score,
                        exposure,
                        -friendly_spacing,
                        path_distance,
                        x,
                        z,
                    )
                    style_reason = "pressure first, then threat lanes, cover, and spacing"
                elif style == "conservative":
                    score = (
                        exposure,
                        -cover_score,
                        -threat_distance,
                        objective_distance,
                        -friendly_spacing,
                        path_distance,
                        x,
                        z,
                    )
                    style_reason = "cover and threat avoidance first, then objectives and spacing"
                else:
                    score = (
                        exposure,
                        -cover_score,
                        objective_distance,
                        -friendly_spacing,
                        -threat_distance,
                        path_distance,
                        x,
                        z,
                    )
                    style_reason = "safe staging first, then objectives, spacing, and threat distance"
                candidates.append({
                    "position": {
                        "x": round(x, 6),
                        "y": round(support_height + model_height / 2, 6),
                        "z": round(z, 6),
                    },
                    "support_height": support_height,
                    "support_sources": copy.deepcopy(support["support_sources"]),
                    "score": score,
                    "score_key": list(score),
                    "style": style,
                    "style_reason": style_reason,
                    "metrics": {
                        "cover_score": cover_score,
                        "exposure": exposure,
                        "objective_distance": objective_distance,
                        "friendly_spacing": friendly_spacing,
                        "threat_distance": threat_distance,
                        "path_distance": path_distance,
                    },
                })
                z += step_z
            x += step_x
        candidates.sort(key=lambda item: (item["score"], item["position"]["x"], item["position"]["z"]))
        return candidates

    def _setup_recommended_position(
        self,
        side: dict[str, Any],
        model_item: dict[str, Any],
        *,
        clearance: float = 0.25,
        play_style: str = "balanced",
    ) -> dict[str, float] | None:
        """Return a tactical legal slot without moving the model."""
        candidates = self._setup_ranked_recommended_positions(
            side,
            model_item,
            clearance=clearance,
            play_style=play_style,
        )
        if not candidates:
            return None
        return copy.deepcopy(candidates[0]["position"])

    def _setup_ai_plan(self, state: dict[str, Any]) -> dict[str, Any] | None:
        setup_state = state.get("setup")
        if not isinstance(setup_state, dict):
            return None
        ai_team = _norm(self.config.ai_team)
        side = setup_state["sides"].get(ai_team)
        if not isinstance(side, dict):
            return None

        try:
            deck_cards = [
                self._setup_card_from_container_item(item, ai_team)
                for item in self._setup_container_items(side["faction_decks_guid"])
            ]
        except KillTeamSetupError:
            deck_cards = []
        try:
            roster_models = [
                self._setup_model_from_container_item(item, ai_team)
                for item in self._setup_container_items(side["roster_container_guid"])
            ]
        except KillTeamSetupError:
            roster_models = []

        deck_by_id = {
            card["operative_id"]: card
            for card in deck_cards
            if _norm(card["side_id"]) == ai_team
        }
        models_by_id = {
            model["operative_id"]: model
            for model in roster_models
            if _norm(model["side_id"]) == ai_team
        }
        ai_records = {
            record["operative_id"]: record
            for record in state["operatives"].values()
            if _norm(record["team"]) == ai_team
        }
        if not ai_records:
            for card in deck_cards:
                if _norm(card["side_id"]) == ai_team:
                    ai_records.setdefault(card["operative_id"], card)
            for model in roster_models:
                if _norm(model["side_id"]) == ai_team:
                    ai_records.setdefault(model["operative_id"], model)

        selected = side.get("selected_operatives", {})
        deployed = side.get("deployed_operatives", {})
        selected_cards = self._setup_selected_cards(side["roster_list_zone_guid"], ai_team)
        selected_by_kind: dict[str, int] = {}
        for card in selected_cards:
            kind = _norm(card.get("card_kind")) or "unknown"
            selected_by_kind[kind] = selected_by_kind.get(kind, 0) + 1

        operative_candidates = sorted(
            [
                card
                for card in deck_by_id.values()
                if _norm(card.get("card_kind")) == "operative"
            ],
            key=self._setup_ai_order_key,
        )
        legal_operative_cards: list[dict[str, Any]] = []
        for card in operative_candidates:
            try:
                self._validate_partial_setup_cards([*legal_operative_cards, card])
            except (KillTeamRuleError, KillTeamSetupError):
                continue
            legal_operative_cards.append(card)
        legal_operative_ids = {
            card["operative_id"]
            for card in legal_operative_cards
        }
        setup_candidates = sorted(
            [
                card
                for card in deck_by_id.values()
                if _norm(card.get("card_kind")) != "operative"
            ],
            key=lambda card: (
                str(_norm(card.get("card_kind")) or "setup"),
                str(card.get("name", "")),
                str(card.get("operative_id", "")),
            ),
        )
        selection_candidates = [*legal_operative_cards, *setup_candidates]
        selection_limits = {
            "operative": self._setup_profile_for_faction(next(iter(deck_by_id.values()))["faction_id"]).exact_team_size if deck_by_id else 0,
            "equipment": 4,
            "ploy": 1,
            "tac_op": 1,
            "primary_op": 1,
        }
        selection_order = []
        next_selection = None
        for card in selection_candidates:
            kind = _norm(card.get("card_kind")) or "operative"
            limit = selection_limits.get(kind, 1 if kind != "operative" else selection_limits["operative"])
            selected_count = selected_by_kind.get(kind, 0)
            legal = kind != "operative" or card["operative_id"] in legal_operative_ids
            entry = {
                "operative_id": card["operative_id"],
                "card_kind": kind,
                "card_guid": card["guid"],
                "card_name": card.get("name", ""),
                "name": card.get("name", ""),
                "profile_id": card.get("profile_id", ""),
                "priority": self._setup_ai_role(card)[0] if kind == "operative" else 4,
                "priority_label": self._setup_ai_role(card)[1] if kind == "operative" else kind,
                "selected": card["operative_id"] in selected,
                "legal": legal,
                "selection_limit": int(limit),
            }
            selection_order.append(entry)
            if next_selection is None and legal and not entry["selected"] and selected_count < int(limit):
                next_selection = copy.deepcopy(entry)
        selection_ids = [card["operative_id"] for card in legal_operative_cards]
        deployment_candidates = [
            models_by_id[operative_id]
            for operative_id in selection_ids
            if operative_id in models_by_id and operative_id not in deployed
        ]
        if not deployment_candidates:
            deployment_candidates = [
                model
                for model in sorted(models_by_id.values(), key=self._setup_ai_order_key)
                if model["operative_id"] not in deployed
            ]
        play_style, play_style_reason = self._setup_team_play_style(deployment_candidates or list(models_by_id.values()))
        deployment_ids = [record["operative_id"] for record in deployment_candidates]
        deployment_order = []
        next_deployment = None
        for operative_id in deployment_ids:
            model = models_by_id.get(operative_id)
            if model is None:
                continue
            priority, label = self._setup_ai_role(model)
            entry = {
                "operative_id": operative_id,
                "model_guid": model["guid"],
                "model_name": model.get("name", ""),
                "name": model.get("name", ""),
                "profile_id": model.get("profile_id", ""),
                "priority": priority,
                "priority_label": label,
                "deployed": operative_id in deployed,
            }
            try:
                model_item = self._setup_operative_model_item(side, operative_id, ai_team)
                ranked_positions = self._setup_ranked_recommended_positions(
                    side,
                    model_item,
                    play_style=play_style,
                )
                if ranked_positions:
                    entry["recommended_position"] = copy.deepcopy(ranked_positions[0]["position"])
                    entry["recommended_position_evidence"] = {
                        "play_style": play_style,
                        "play_style_reason": play_style_reason,
                        "candidate_count": len(ranked_positions),
                        "ranked_positions": [
                            {
                                "position": copy.deepcopy(candidate["position"]),
                                "support_height": candidate["support_height"],
                                "support_sources": copy.deepcopy(candidate["support_sources"]),
                                "score_key": list(candidate["score_key"]),
                                "style": candidate["style"],
                                "style_reason": candidate["style_reason"],
                                "metrics": copy.deepcopy(candidate["metrics"]),
                            }
                            for candidate in ranked_positions[:3]
                        ],
                    }
                else:
                    entry["recommended_position"] = None
                    entry["recommended_position_evidence"] = {
                        "play_style": play_style,
                        "play_style_reason": play_style_reason,
                        "candidate_count": 0,
                        "ranked_positions": [],
                    }
            except (KillTeamSetupError, KillTeamRuleError):
                entry["recommended_position"] = None
                entry["recommended_position_evidence"] = None
            deployment_order.append(entry)
            if next_deployment is None and not entry["deployed"]:
                next_deployment = copy.deepcopy(entry)

        return {
            "play_style": play_style,
            "play_style_reason": play_style_reason,
            "policy": (
                "Use the listed AI selection order for roster cards and the listed AI deployment order for models. "
                + (
                    "This team style is aggressive: prefer objective pressure and attack lanes first, then cover and spacing."
                    if play_style == "aggressive"
                    else "This team style is conservative: prefer cover and ranged engagement first, then objective access."
                    if play_style == "conservative"
                    else "This team style is balanced: prefer safe legal slots, then objective access, then attack lanes."
                )
            ),
            "selection_order": selection_order,
            "selected_card_counts": selected_by_kind,
            "deployment_order": deployment_order,
            "next_selection": next_selection,
            "next_deployment": next_deployment,
        }

    def setup(self, *, auto_start: bool = False) -> dict[str, Any]:
        objects = self._normalize_fixture_objects(self._list_objects())
        self._objects = {str(obj["guid"]): obj for obj in objects}
        metadata = {guid: _metadata(obj) for guid, obj in self._objects.items()}
        side_objects = self._setup_side_objects() if self._fixture_profile is None else {}
        setup_mode_enabled = self._setup_mode_enabled(side_objects)
        if setup_mode_enabled:
            initiative_side = _norm(self.config.initiative_side)
            if initiative_side and initiative_side not in side_objects:
                raise KillTeamSetupError("initiative_side does not match a tagged setup side")
            self._setup_clean_start(side_objects)

        rollers = [guid for guid, meta in metadata.items() if meta.get("entity") == "dice_roller"]
        if len(rollers) != 1:
            raise KillTeamSetupError("exactly one dice roller is required")
        dice_by_team: dict[str, list[str]] = {}
        for guid, meta in metadata.items():
            if meta.get("entity") == "die":
                team = meta.get("team", "").lower()
                if team:
                    dice_by_team.setdefault(team, []).append(guid)
        required_ai_dice = 4 if self._fixture_profile is not None else self.config.ai_dice_count
        if len(dice_by_team.get(self.config.ai_team, [])) < required_ai_dice:
            raise KillTeamSetupError("the AI dice pool is incomplete")
        if (
            self._fixture_profile is None
            and len(dice_by_team.get("opponent", [])) < self.config.opponent_dice_count
        ):
            raise KillTeamSetupError("the opponent dice pool is incomplete")

        operatives: dict[str, dict[str, Any]] = {}
        for guid, obj in self._objects.items():
            meta = metadata[guid]
            if meta.get("entity") != "operative":
                continue
            operative_id = meta.get("operative_id", "").strip()
            team = meta.get("team", "").strip().lower()
            if not operative_id or not team:
                raise KillTeamSetupError(f"operative {guid} needs operative_id and team tags")
            if operative_id in operatives:
                raise KillTeamSetupError(f"duplicate operative_id {operative_id}")
            profile = _profile(obj)
            operatives[operative_id] = {
                "operative_id": operative_id,
                "guid": guid,
                "team": team,
                "name": obj.get("name"),
                "description": obj.get("description", ""),
                "type": obj.get("type"),
                "tags": copy.deepcopy(obj.get("tags", [])),
                "bounds": copy.deepcopy(obj.get("bounds")),
                "profile_id": meta.get("profile", ""),
                "position": _position(obj),
                "max_wounds": int(profile["wounds"]),
                "wounds": int(profile["wounds"]),
                "ap": 0,
                "save": int(profile["save"]),
                "defense_dice": int(profile.get("defense_dice", 3)),
                "profile": profile,
                "statuses": [],
                "order": "",
            }

        ai_ids = sorted(record["operative_id"] for record in operatives.values() if record["team"] == self.config.ai_team)
        if not ai_ids and not setup_mode_enabled:
            raise KillTeamSetupError("at least one AI operative is required")
        visible_opponents = [
            record["operative_id"]
            for record in operatives.values()
            if record["team"] != self.config.ai_team and self._is_visible(self._objects[record["guid"]], metadata[record["guid"]])
        ]
        counter_guids: dict[str, list[str]] = {}
        for guid, meta in metadata.items():
            if meta.get("entity") == "counter" and meta.get("counter"):
                counter_guids.setdefault(meta["counter"].lower(), []).append(guid)
        duplicate_counters = {
            counter: guids for counter, guids in counter_guids.items() if len(guids) != 1
        }
        if duplicate_counters:
            raise KillTeamSetupError(f"counter metadata is duplicated: {duplicate_counters}")
        counters = {counter: guids[0] for counter, guids in counter_guids.items()}
        if self._fixture_profile is None:
            if "cp" not in counters or "vp" not in counters:
                raise KillTeamSetupError("CP and VP counters are required")
            calibration_guids = [
                guid for guid, meta in metadata.items() if meta.get("entity") == "calibration"
            ]
            if len(calibration_guids) != 1:
                raise KillTeamSetupError("exactly one calibration marker is required")
            calibration = metadata[calibration_guids[0]]
            units_per_inch = float(
                calibration.get("units_per_inch", self.config.units_per_inch)
            )
        else:
            required_counters = {counter for counter, _guid in self._fixture_profile.counter_guids}
            missing_counters = sorted(required_counters - counters.keys())
            if missing_counters:
                raise KillTeamSetupError(
                    f"Save 131 counters are missing: {', '.join(missing_counters)}"
                )
            units_per_inch = float(self.config.units_per_inch)
        if units_per_inch <= 0:
            raise KillTeamSetupError("units_per_inch must be positive")
        terrain = []
        for guid, meta in metadata.items():
            if meta.get("entity") == "terrain" or _is_terrain_surface(self._objects[guid]):
                terrain.append({"guid": guid, "blocks_los": _bool(meta.get("blocks_los")), "bounds": _bounds(self._objects[guid])})

        defense_station_guid = None
        start_test_spot = None
        combat_zone_guid = None
        deployment_zone_guid = None
        deployment_subject = None
        visible_target = None
        if self._fixture_profile is not None:
            defense_station_guid = self._fixture_profile.defense_station_guid
            matching_snap_points = [
                point
                for point in self._snap_points
                if any(
                    str(tag).strip().casefold()
                    == self._fixture_profile.start_snap_tag.casefold()
                    for tag in point.get("tags", [])
                )
            ]
            if len(matching_snap_points) != 1:
                raise KillTeamSetupError(
                    "exactly one global _start_test_spot snap point is required"
                )
            start_test_spot = copy.deepcopy(matching_snap_points[0])
            start_test_spot["position"] = _position(start_test_spot)

            combat_zones = [
                (guid, obj)
                for guid, obj in self._objects.items()
                if metadata[guid].get("entity") == "combat_zone"
            ]
            if len(combat_zones) != 1 or _bounds(combat_zones[0][1]) is None:
                raise KillTeamSetupError("exactly one bounded combat zone is required")
            combat_zone_guid, combat_zone = combat_zones[0]
            combat_bounds = _bounds(combat_zone)
            assert combat_bounds is not None

            deployment_zones = [
                (guid, obj)
                for guid, obj in self._objects.items()
                if metadata[guid].get("entity") == "deployment"
            ]
            if len(deployment_zones) != 1 or _bounds(deployment_zones[0][1]) is None:
                raise KillTeamSetupError(
                    "exactly one bounded _deployment_zone_blue is required"
                )
            deployment_zone_guid = deployment_zones[0][0]

            def inside_combat_zone(record: dict[str, Any]) -> bool:
                x, z = record["position"]["x"], record["position"]["z"]
                return (
                    combat_bounds[0] <= x <= combat_bounds[1]
                    and combat_bounds[2] <= z <= combat_bounds[3]
                )

            deployment_candidates = [
                record
                for record in operatives.values()
                if record["team"] == self.config.ai_team and not inside_combat_zone(record)
            ]
            target_candidates = [
                record
                for record in operatives.values()
                if record["team"] != self.config.ai_team
                and inside_combat_zone(record)
                and self._is_visible(self._objects[record["guid"]], metadata[record["guid"]])
            ]
            if len(deployment_candidates) != 1:
                raise KillTeamSetupError(
                    "Save 131 must expose exactly one staged AI deployment subject"
                )
            if len(target_candidates) != 1:
                raise KillTeamSetupError(
                    "Save 131 must expose exactly one visible enemy in the combat zone"
                )
            deployment_subject = copy.deepcopy(deployment_candidates[0])
            visible_target = copy.deepcopy(target_candidates[0])

        setup_state = None
        if setup_mode_enabled:
            initiative_side = _norm(self.config.initiative_side) or self.config.ai_team
            setup_state = {
                "mode": "roster_cards",
                "stage": "roster_selection",
                "initiative_side": initiative_side,
                "current_side": initiative_side,
                "current_batch_target": 0,
                "current_batch_progress": 0,
                "pending_side": None,
                "pending_operative_id": None,
                "pending_model_guid": None,
                "sides": {
                    side_id: {
                        "side_id": side_id,
                        "faction_decks_guid": mapping["faction_decks"],
                        "roster_container_guid": mapping["roster"],
                        "roster_list_zone_guid": mapping["roster_list_zone"],
                        "deployed_zone_guid": mapping["deployed_zone"],
                        "deployment_zone_guid": mapping["deployment"],
                        "locked": False,
                        "faction_id": "",
                        "selected_operatives": {},
                        "deployed_operatives": {},
                        "batch_size": 0,
                    }
                    for side_id, mapping in side_objects.items()
                },
            }
        tactical_initiative_side = _norm(self.config.initiative_side) or self.config.ai_team

        self._state = {
            "schema_version": 1,
            "status": "ready",
            "revision": 0,
            "observation_id": 0,
            "map_revision": 0,
            "phase": "setup",
            "turning_point": 1,
            "active_operative_id": None,
            "initiative_side": tactical_initiative_side,
            "initiative_token_guid": None,
            "initiative_token_side": tactical_initiative_side,
            "turn_owner": tactical_initiative_side,
            "turn_status": "waiting",
            "turn_sequence": 0,
            "turn_history": [],
            "operatives": operatives,
            "terrain": terrain,
            "roller_guid": rollers[0],
            "defense_station_guid": defense_station_guid,
            "combat_zone_guid": combat_zone_guid,
            "deployment_zone_guid": deployment_zone_guid,
            "start_test_spot": start_test_spot,
            "deployment_subject_id": (
                deployment_subject["operative_id"] if deployment_subject else None
            ),
            "visible_target_id": visible_target["operative_id"] if visible_target else None,
            "dice_by_team": dice_by_team,
            "counter_guids": counters,
            "units_per_inch": units_per_inch,
            "events": self._events,
            "setup": setup_state,
            "markers": [],
        }
        self._state["map_revision"] = self._scene_revision(self._objects.values())
        if setup_state is not None and auto_start:
            self._setup_start_from_roster_models(setup_state)
            self._state["revision"] += 1
            self._record("setup.model_deployment_started", {
                "initiative_side": setup_state["initiative_side"],
                "batch_target": setup_state["current_batch_target"],
            })
        self._record("setup.completed", {"ai_operatives": ai_ids, "visible_opponents": visible_opponents})
        result = {
            "status": "ready",
            "schema_version": 1,
            "ai_operatives": ai_ids,
            "ai_models": [copy.deepcopy(operatives[operative_id]) for operative_id in ai_ids],
            "visible_opponents": sorted(visible_opponents),
            "map_revision": self._state["map_revision"],
            "roller_guid": rollers[0],
        }
        if setup_state is not None:
            result["setup"] = self._setup_snapshot(self._state)
        if self._fixture_profile is not None:
            result.update({
                "fixture_profile": self._fixture_profile.name,
                "deployment_subject": deployment_subject,
                "visible_target": visible_target,
                "start_test_spot": start_test_spot,
                "defense_station_guid": defense_station_guid,
                "deployment_zone_guid": deployment_zone_guid,
                "roster_container_guid": self._fixture_profile.roster_container_guid,
            })
        return result

    def observe(self) -> dict[str, Any]:
        state = self._require_state()
        self._refresh()
        state["observation_id"] += 1
        visible = self._visible_operatives()
        counters = {
            counter: {
                "guid": guid,
                "value": self._objects.get(guid, {}).get("counter_value"),
            }
            for counter, guid in state["counter_guids"].items()
        }
        terrain = copy.deepcopy(state["terrain"])
        terrain_truncated = len(terrain) > 200
        result = {
            "schema_version": state["schema_version"],
            "revision": state["revision"],
            "observation_id": state["observation_id"],
            "map_revision": state["map_revision"],
            "phase": state["phase"],
            "turning_point": state.get("turning_point", 1),
            "active_operative_id": state["active_operative_id"],
            "initiative_side": state.get("initiative_side", ""),
            "initiative_token_guid": state.get("initiative_token_guid"),
            "initiative_token_side": state.get("initiative_token_side", ""),
            "turn_owner": state.get("turn_owner", ""),
            "turn_status": state.get("turn_status", ""),
            "turn_sequence": state.get("turn_sequence", 0),
            "operatives": visible,
            "terrain": terrain[:200],
            "dice": {"ai": list(state["dice_by_team"].get(self.config.ai_team, []))},
            "counters": counters,
            "roller_guid": state["roller_guid"],
            "defense_station_guid": state.get("defense_station_guid"),
            "start_test_spot": copy.deepcopy(state.get("start_test_spot")),
            "markers": copy.deepcopy(state.get("markers", [])),
            "truncated": self._listing_truncated or terrain_truncated,
        }
        setup_snapshot = self._setup_snapshot(state)
        if setup_snapshot is not None:
            result["setup"] = setup_snapshot
        return result

    def _require_setup_state(self) -> dict[str, Any]:
        state = self._require_state()
        setup_state = state.get("setup")
        if not isinstance(setup_state, dict):
            raise KillTeamRuleError("semantic roster setup is not active")
        return setup_state

    def _setup_side_state(self, side_id: str) -> dict[str, Any]:
        setup_state = self._require_setup_state()
        side = setup_state["sides"].get(_norm(side_id))
        if not isinstance(side, dict):
            raise KillTeamRuleError(f"unknown setup side {side_id}")
        return side

    @staticmethod
    def _setup_live_operative_id(side_id: str, operative_id: str) -> str:
        return f"{_norm(side_id)}:{operative_id}"

    def _setup_operative_model_item(
        self,
        side: dict[str, Any],
        operative_id: str,
        side_id: str | None = None,
    ) -> dict[str, Any]:
        fallback_side_id = side_id or str(side.get("side_id") or "").strip()
        model_items = [
            self._setup_model_from_container_item(item, fallback_side_id or self.config.ai_team)
            for item in self._setup_container_items(side["roster_container_guid"])
        ]
        matches = [item for item in model_items if item["operative_id"] == operative_id]
        if len(matches) != 1:
            raise KillTeamRuleError(
                f"roster container must contain exactly one undeployed model for {operative_id}"
            )
        return matches[0]

    def _setup_operative_model_item_by_guid(
        self,
        side: dict[str, Any],
        model_guid: str,
        side_id: str | None = None,
    ) -> dict[str, Any]:
        fallback_side_id = side_id or str(side.get("side_id") or "").strip()
        model_items = [
            self._setup_model_from_container_item(item, fallback_side_id or self.config.ai_team)
            for item in self._setup_container_items(side["roster_container_guid"])
        ]
        matches = [item for item in model_items if _norm(item["guid"]) == _norm(model_guid)]
        if len(matches) != 1:
            raise KillTeamRuleError(
                f"roster container must contain exactly one undeployed model with guid {model_guid}"
            )
        return matches[0]

    def _initiative_dice_guid(self, side_id: str) -> str:
        state = self._require_state()
        if side_id == self.config.ai_team:
            team = self.config.ai_team
        elif side_id == "opponent":
            team = "opponent"
        else:
            team = side_id
        dice = list(state["dice_by_team"].get(team, []))
        if not dice:
            raise KillTeamRuleError(f"no initiative die is available for side {side_id}")
        return str(dice[0])

    def _setup_update_turn_after_success(self, setup_state: dict[str, Any], side: dict[str, Any]) -> None:
        state = self._require_state()
        side["pending_operative_id"] = None
        setup_state["pending_side"] = None
        setup_state["pending_operative_id"] = None
        setup_state["pending_model_guid"] = None
        setup_state["current_batch_progress"] += 1

        all_complete = all(
            len(item["deployed_operatives"]) >= len(item["selected_operatives"])
            for item in setup_state["sides"].values()
        )
        if all_complete:
            setup_state["stage"] = "complete"
            setup_state["current_side"] = None
            setup_state["current_batch_target"] = 0
            setup_state["current_batch_progress"] = 0
            state["phase"] = "command"
            state["turn_status"] = "waiting"
            state["turn_owner"] = setup_state.get("initiative_side") or state.get("turn_owner", "")
            return

        side_remaining = len(side["selected_operatives"]) - len(side["deployed_operatives"])
        if setup_state["current_batch_progress"] < setup_state["current_batch_target"] and side_remaining > 0:
            return

        ordered_sides = list(setup_state["sides"].keys())
        current_index = ordered_sides.index(setup_state["current_side"])
        next_side = None
        for offset in range(1, len(ordered_sides) + 1):
            candidate = ordered_sides[(current_index + offset) % len(ordered_sides)]
            candidate_side = setup_state["sides"][candidate]
            remaining = len(candidate_side["selected_operatives"]) - len(candidate_side["deployed_operatives"])
            if remaining > 0:
                next_side = candidate
                break
        if next_side is None:
            setup_state["stage"] = "complete"
            setup_state["current_side"] = None
            setup_state["current_batch_target"] = 0
            setup_state["current_batch_progress"] = 0
            state["phase"] = "command"
            state["turn_status"] = "waiting"
            state["turn_owner"] = setup_state.get("initiative_side") or state.get("turn_owner", "")
            return
        next_state = setup_state["sides"][next_side]
        remaining = len(next_state["selected_operatives"]) - len(next_state["deployed_operatives"])
        setup_state["current_side"] = next_side
        setup_state["current_batch_target"] = min(int(next_state["batch_size"]), remaining)
        setup_state["current_batch_progress"] = 0

    def _operative_record_from_live_object(self, obj: dict[str, Any]) -> dict[str, Any]:
        metadata = _metadata(obj)
        operative_id = str(metadata.get("operative_id") or "").strip()
        team = _norm(metadata.get("team") or metadata.get("side_id"))
        if not operative_id or not team:
            raise KillTeamSetupError("live operative is missing operative_id or team metadata")
        profile = _profile(obj)
        return {
            "operative_id": operative_id,
            "guid": str(obj["guid"]),
            "team": team,
            "name": obj.get("name"),
            "description": obj.get("description", ""),
            "type": obj.get("type"),
            "tags": copy.deepcopy(obj.get("tags", [])),
            "bounds": copy.deepcopy(obj.get("bounds")),
            "profile_id": metadata.get("profile", ""),
            "position": _position(obj),
            "max_wounds": int(profile["wounds"]),
            "wounds": int(profile["wounds"]),
            "ap": 0,
            "save": int(profile["save"]),
            "defense_dice": int(profile.get("defense_dice", 3)),
            "profile": profile,
            "statuses": [],
            "order": "",
        }

    def _deployment_legality(
        self,
        side: dict[str, Any],
        obj: dict[str, Any],
    ) -> None:
        deployment_bounds = self._setup_zone_bounds(side["deployment_zone_guid"])
        model_bounds = _bounds(obj)
        if model_bounds is None:
            raise KillTeamRuleError("deployed model is missing bounds")
        if not _rect_contains_rect(deployment_bounds, model_bounds):
            raise KillTeamRuleError("deployment position is not wholly within the side deployment zone")
        for other_guid, other in self._objects.items():
            if other_guid == str(obj.get("guid")):
                continue
            if _norm(_metadata(other).get("entity")) != "operative":
                continue
            other_bounds = _bounds(other)
            if other_bounds is None:
                continue
            if _rects_overlap(model_bounds, other_bounds):
                raise KillTeamRuleError(f"deployment position overlaps operative {other_guid}")

    def _complete_setup_deployment(
        self,
        side_id: str,
        operative_id: str,
        obj: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._require_state()
        setup_state = self._require_setup_state()
        side = self._setup_side_state(side_id)
        operative = self._operative_record_from_live_object(obj)
        semantic_operative_id = self._setup_live_operative_id(side_id, operative_id)
        operative["operative_id"] = semantic_operative_id
        operative["order"] = "conceal"
        state["operatives"][semantic_operative_id] = operative
        side["deployed_operatives"][operative_id] = {
            "operative_id": operative_id,
            "semantic_operative_id": semantic_operative_id,
            "guid": operative["guid"],
        }
        state["revision"] += 1
        self._setup_update_turn_after_success(setup_state, side)
        self._record(
            "setup.operative_deployed",
            {
                "side_id": side_id,
                "operative_id": operative_id,
                "semantic_operative_id": semantic_operative_id,
                "guid": operative["guid"],
                "model_guid": operative["guid"],
                "position": operative["position"],
            },
        )
        return {
            "status": "deployed",
            "side_id": side_id,
            "operative_id": operative_id,
            "semantic_operative_id": semantic_operative_id,
            "guid": operative["guid"],
            "model_guid": operative["guid"],
            "position": copy.deepcopy(operative["position"]),
            "revision": state["revision"],
        }

    def select_setup_card(
        self,
        contained_guid: str,
        *,
        card_kind: str | None = None,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        setup_state = self._require_setup_state()
        if setup_state["stage"] != "roster_selection":
            raise KillTeamRuleError("roster selection is already locked")
        side = self._setup_side_state(self.config.ai_team)
        deck_items = self._setup_container_items(side["faction_decks_guid"])
        candidate_item = next(
            (item for item in deck_items if _norm(item.get("guid")) == _norm(contained_guid)),
            None,
        )
        if candidate_item is None:
            raise KillTeamRuleError(f"unknown roster card {contained_guid}")
        candidate = self._setup_card_from_container_item(candidate_item, self.config.ai_team)
        if candidate["side_id"] != self.config.ai_team:
            raise KillTeamRuleError("only the AI side can be selected semantically")
        requested_kind = _norm(card_kind)
        if requested_kind and _norm(candidate.get("card_kind")) != requested_kind:
            raise KillTeamRuleError(f"setup card {contained_guid} is not a {requested_kind}")
        current_cards = self._setup_selected_cards(side["roster_list_zone_guid"], self.config.ai_team)
        current_operatives = [
            card for card in current_cards if _norm(card.get("card_kind")) == "operative"
        ]
        if _norm(candidate.get("card_kind")) == "operative":
            self._validate_partial_setup_cards([*current_operatives, candidate])
        target = self._setup_zone_center(side["roster_list_zone_guid"])
        try:
            taken = self.bridge.take_from_container(
                side["faction_decks_guid"],
                item_guid=candidate["guid"],
                position=target,
                smooth=False,
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("roster card selection commit is uncertain") from exc
        taken_object = taken.get("object", {}) if isinstance(taken, dict) else {}
        if not isinstance(taken_object, dict):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("roster card selection returned an invalid object")
        selected = self._setup_card_from_object(taken_object, self.config.ai_team)
        state["revision"] += 1
        self._record(
            "setup.setup_card_selected",
            {
                "side_id": self.config.ai_team,
                "operative_id": selected["operative_id"],
                "guid": selected["guid"],
                "card_kind": selected.get("card_kind", ""),
            },
        )
        result = {
            "status": "selected",
            "side_id": self.config.ai_team,
            "operative_id": selected["operative_id"],
            "guid": selected["guid"],
            "card_kind": selected.get("card_kind", ""),
            "selected_count": len(current_cards) + 1,
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def select_roster_card(
        self,
        contained_guid: str,
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        return self.select_setup_card(contained_guid, card_kind="operative", action_id=action_id)

    def roll_initiative(self, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        setup_state = self._require_setup_state()
        if setup_state["stage"] not in {"initiative", "roster_selection"}:
            raise KillTeamRuleError("initiative can only be determined before roster lock")
        if setup_state["stage"] == "roster_selection" and setup_state["initiative_side"]:
            raise KillTeamRuleError("initiative has already been determined")
        ai_die = self._initiative_dice_guid(self.config.ai_team)
        opponent_side_id = next(
            side_id for side_id in setup_state["sides"].keys() if side_id != self.config.ai_team
        )
        opponent_die = self._initiative_dice_guid(opponent_side_id)
        try:
            ai_roll = self.bridge.roll_dice(
                team=self.config.ai_team,
                dice_guids=[ai_die],
                roller_guid=state["roller_guid"],
                purpose="initiative",
            )
            opponent_roll = self.bridge.roll_dice(
                team="opponent",
                dice_guids=[opponent_die],
                roller_guid=state["roller_guid"],
                purpose="initiative",
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative roll commit is uncertain") from exc
        try:
            ai_faces = [int(face) for face in list(ai_roll.get("faces", []))]
            opponent_faces = [int(face) for face in list(opponent_roll.get("faces", []))]
        except (AttributeError, TypeError, ValueError) as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative roll returned invalid faces") from exc
        if len(ai_faces) != 1 or len(opponent_faces) != 1:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("initiative roll did not return exactly one face per side")
        initiative_side = ""
        if ai_faces[0] > opponent_faces[0]:
            initiative_side = self.config.ai_team
        elif opponent_faces[0] > ai_faces[0]:
            initiative_side = opponent_side_id
        setup_state["initiative_side"] = initiative_side
        setup_state["stage"] = "roster_selection" if initiative_side else "initiative"
        setup_state["current_side"] = initiative_side or None
        state["revision"] += 1
        self._record(
            "setup.initiative_rolled",
            {
                "initiative_side": initiative_side,
                "ai_roll": ai_faces,
                "opponent_roll": opponent_faces,
            },
        )
        result = {
            "status": "resolved" if initiative_side else "tied",
            "initiative_side": initiative_side,
            "ai_roll": ai_faces,
            "opponent_roll": opponent_faces,
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def lock_rosters(self, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        setup_state = self._require_setup_state()
        if setup_state["stage"] != "roster_selection":
            raise KillTeamRuleError("rosters are already locked")
        for side_id, side in setup_state["sides"].items():
            cards = self._setup_selected_cards(side["roster_list_zone_guid"], side_id)
            operative_cards = [
                card for card in cards if _norm(card.get("card_kind")) == "operative"
            ]
            profile, faction_id = self._validate_locked_setup_cards(operative_cards)
            selected = {card["operative_id"]: copy.deepcopy(card) for card in operative_cards}
            for operative_id in selected:
                self._setup_operative_model_item(side, operative_id, side_id)
            side["locked"] = True
            side["faction_id"] = faction_id
            side["selected_operatives"] = selected
            side["deployed_operatives"] = {}
            # Official setup alternates one-third batches, rounded up.
            side["batch_size"] = self._setup_batch_size(len(selected))
        setup_state["stage"] = "deployment"
        setup_state["current_side"] = setup_state["initiative_side"]
        initiative_side = setup_state["sides"][setup_state["current_side"]]
        setup_state["current_batch_target"] = min(
            int(initiative_side["batch_size"]),
            len(initiative_side["selected_operatives"]),
        )
        setup_state["current_batch_progress"] = 0
        state["revision"] += 1
        self._record(
            "setup.rosters_locked",
            {
                "initiative_side": setup_state["initiative_side"],
                "batch_target": setup_state["current_batch_target"],
            },
        )
        result = {
            "status": "locked",
            "revision": state["revision"],
            "setup": self._setup_snapshot(state),
        }
        return self._recorded_result(action_id, result)

    def start_setup_deployment(
        self,
        operative_id: str,
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        setup_state = self._require_setup_state()
        if setup_state["stage"] != "deployment":
            raise KillTeamRuleError("setup deployment is not active")
        if setup_state["current_side"] != self.config.ai_team:
            raise KillTeamRuleError("it is not the AI side's deployment pass")
        if setup_state["pending_operative_id"]:
            raise KillTeamRuleError("another setup operative is already pending deployment")
        side = self._setup_side_state(self.config.ai_team)
        if operative_id in side["deployed_operatives"]:
            raise KillTeamRuleError(f"operative {operative_id} is already deployed")
        if operative_id not in side["selected_operatives"]:
            raise KillTeamRuleError(f"operative {operative_id} is not in the locked roster list")
        model_item = self._setup_operative_model_item(side, operative_id, self.config.ai_team)
        recommended_position = self._setup_recommended_position(side, model_item)
        if setup_state.get("mode") == "model_deployment":
            setup_state["pending_side"] = self.config.ai_team
            setup_state["pending_operative_id"] = operative_id
            setup_state["pending_model_guid"] = model_item["guid"]
            side["pending_operative_id"] = operative_id
            state["revision"] += 1
            self._record("setup.deployment_started", {
                "side_id": self.config.ai_team,
                "operative_id": operative_id,
                "model_guid": model_item["guid"],
                "recommended_position": recommended_position,
            })
            return self._recorded_result(action_id, {
                "status": "pending_model",
                "side_id": self.config.ai_team,
                "operative_id": operative_id,
                "model_guid": model_item["guid"],
                "recommended_position": recommended_position,
                "revision": state["revision"],
            })
        roster_cards = self._setup_selected_cards(side["roster_list_zone_guid"], self.config.ai_team)
        match = next((card for card in roster_cards if card["operative_id"] == operative_id), None)
        if match is None:
            raise KillTeamRuleError(f"operative {operative_id} is not currently in the roster list zone")
        target = self._setup_zone_center(side["deployed_zone_guid"])
        try:
            self.bridge.move_object(match["guid"], target)
            actual = self.bridge.get_object(match["guid"])
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("setup card movement commit is uncertain") from exc
        moved = self._setup_card_from_object(actual, self.config.ai_team)
        setup_state["pending_side"] = self.config.ai_team
        setup_state["pending_operative_id"] = operative_id
        setup_state["pending_model_guid"] = model_item["guid"]
        side["pending_operative_id"] = operative_id
        state["revision"] += 1
        self._record(
            "setup.deployment_started",
            {
                "side_id": self.config.ai_team,
                "operative_id": operative_id,
                "guid": moved["guid"],
                "model_guid": model_item["guid"],
            },
        )
        result = {
            "status": "pending_model",
            "side_id": self.config.ai_team,
            "operative_id": operative_id,
            "guid": moved["guid"],
            "model_guid": model_item["guid"],
            "recommended_position": recommended_position,
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def deploy_setup_operative(
        self,
        model_guid: str,
        position: dict[str, float],
        *,
        action_id: str | None = None,
        verification_tolerance: float = 0.05,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        if verification_tolerance <= 0:
            raise KillTeamRuleError("deployment verification tolerance must be positive")
        state = self._require_state()
        setup_state = self._require_setup_state()
        if setup_state["current_side"] != self.config.ai_team:
            raise KillTeamRuleError("it is not the AI side's deployment pass")
        side = self._setup_side_state(self.config.ai_team)
        target = {axis: _number(position.get(axis, 0), f"position.{axis}") for axis in ("x", "y", "z")}
        model_item = self._setup_operative_model_item_by_guid(side, model_guid, self.config.ai_team)
        operative_id = model_item["operative_id"]
        if setup_state["pending_operative_id"] != operative_id:
            raise KillTeamRuleError(f"model {model_guid} is not the pending deployment")
        pending_model_guid = _norm(str(setup_state.get("pending_model_guid") or ""))
        if pending_model_guid and pending_model_guid != _norm(model_guid):
            raise KillTeamRuleError(f"model {model_guid} is not the pending deployment")
        spawn_target = copy.deepcopy(target)
        spawn_target["y"] = round(float(target["y"]) + 5.0, 6)
        try:
            taken = self.bridge.take_from_container(
                side["roster_container_guid"],
                item_guid=model_item["guid"],
                position=spawn_target,
                smooth=False,
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("setup operative deployment commit is uncertain") from exc
        live = taken.get("object", {}) if isinstance(taken, dict) else {}
        if not isinstance(live, dict):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("setup operative deployment returned an invalid object")
        try:
            live_guid = str(live.get("guid") or "")
            actual = self.bridge.get_object(live_guid)
            objects = self._normalize_fixture_objects(self._list_objects())
            support_surfaces = self._terrain_support_surfaces(objects)
            deployment_zone = self._objects.get(str(side["deployment_zone_guid"]), {})
            deployment_box = _bounds_box(deployment_zone)
            final_target = self._setup_board_supported_position(
                {
                    "deployment_floor_y": deployment_box["min_y"] if deployment_box is not None else target["y"],
                    "support_surfaces": support_surfaces,
                },
                actual,
                {
                    "x": float(target["x"]),
                    "y": float(target["y"]),
                    "z": float(target["z"]),
                },
            )
            if any(abs(_position(actual)[axis] - final_target[axis]) > verification_tolerance for axis in ("x", "y", "z")):
                actual = self.bridge.move_object(live_guid, final_target)
                actual = self.bridge.get_object(live_guid)
            actual_position = _position(actual)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("setup operative deployment readback is invalid") from exc
        if any(abs(actual_position[axis] - final_target[axis]) > verification_tolerance for axis in ("x", "y", "z")):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("setup operative deployment did not verify")
        try:
            self._refresh()
            actual = self._objects[str(live["guid"])]
            self._deployment_legality(side, actual)
        except KillTeamRuleError:
            try:
                self.bridge.put_object_into_container(side["roster_container_guid"], str(live["guid"]))
                self._refresh()
            except Exception as exc:
                self._mark_uncertain(action_id)
                raise KillTeamUncertainCommit("illegal deployment could not be rolled back safely") from exc
            raise
        result = self._complete_setup_deployment(self.config.ai_team, operative_id, actual)
        return self._recorded_result(action_id, result)

    def rollback_pending_deployment(self, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        setup_state = self._require_setup_state()
        side_id = str(setup_state.get("pending_side") or "")
        operative_id = str(setup_state.get("pending_operative_id") or "")
        if not side_id or not operative_id:
            raise KillTeamRuleError("no setup deployment is pending")
        side = self._setup_side_state(side_id)
        if setup_state.get("mode") == "model_deployment":
            # Model deployment does not move a roster card before placement;
            # rollback only clears the pending reservation.
            side["pending_operative_id"] = None
            setup_state["pending_side"] = None
            setup_state["pending_operative_id"] = None
            setup_state["pending_model_guid"] = None
            state["revision"] += 1
            self._record("setup.deployment_rolled_back", {"side_id": side_id, "operative_id": operative_id})
            result = {
                "status": "rolled_back",
                "side_id": side_id,
                "operative_id": operative_id,
                "revision": state["revision"],
            }
            return self._recorded_result(action_id, result)
        deployed_cards = self._setup_selected_cards(side["deployed_zone_guid"], side_id)
        match = next((card for card in deployed_cards if card["operative_id"] == operative_id), None)
        if match is None:
            raise KillTeamRuleError("pending deployment card is not in the deployed zone")
        target = self._setup_zone_center(side["roster_list_zone_guid"])
        try:
            self.bridge.move_object(match["guid"], target)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("pending deployment rollback is uncertain") from exc
        side["pending_operative_id"] = None
        setup_state["pending_side"] = None
        setup_state["pending_operative_id"] = None
        setup_state["pending_model_guid"] = None
        state["revision"] += 1
        self._record("setup.deployment_rolled_back", {"side_id": side_id, "operative_id": operative_id})
        result = {
            "status": "rolled_back",
            "side_id": side_id,
            "operative_id": operative_id,
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def reconcile_setup_step(
        self,
        side_id: str,
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        setup_state = self._require_setup_state()
        side_id = _norm(side_id)
        if setup_state["stage"] != "deployment":
            raise KillTeamRuleError("setup deployment is not active")
        if setup_state["current_side"] != side_id:
            raise KillTeamRuleError(f"it is not {side_id}'s deployment pass")
        if (
            setup_state.get("mode") == "model_deployment"
            and side_id == self.config.ai_team
        ):
            raise KillTeamRuleError(
                "AI models must be deployed through the AI setup deployment action, not reconciliation"
            )
        side = self._setup_side_state(side_id)
        if not side["locked"]:
            raise KillTeamRuleError(f"side {side_id} does not have a locked roster list")
        self._refresh()
        deployed_cards = self._setup_selected_cards(side["deployed_zone_guid"], side_id)
        pending_cards = [
            card for card in deployed_cards if card["operative_id"] not in side["deployed_operatives"]
        ]
        if not pending_cards:
            deployment_bounds = self._setup_zone_bounds(side["deployment_zone_guid"])
            pending_models = []
            for obj in self._objects.values():
                metadata = _metadata(obj)
                if (
                    _norm(metadata.get("entity")) != "operative"
                    or _norm(metadata.get("side_id") or metadata.get("team")) != side_id
                ):
                    continue
                operative_id = str(metadata.get("operative_id") or "").strip()
                if not operative_id or operative_id not in side["selected_operatives"]:
                    continue
                if operative_id in side["deployed_operatives"]:
                    continue
                model_bounds = _bounds(obj)
                if model_bounds is not None and _rect_contains_rect(deployment_bounds, model_bounds):
                    pending_models.append((operative_id, obj))
            if not pending_models:
                return {
                    "status": "waiting_for_model",
                    "side_id": side_id,
                    "batch_target": int(setup_state.get("current_batch_target", 0)),
                    "batch_progress": int(setup_state.get("current_batch_progress", 0)),
                }
            remaining_batch = max(
                0,
                int(setup_state.get("current_batch_target", 0))
                - int(setup_state.get("current_batch_progress", 0)),
            )
            if len(pending_models) > remaining_batch:
                raise KillTeamRuleError(
                    f"human side placed {len(pending_models)} models, but only {remaining_batch} remain in this setup batch"
                )
            pending_models.sort(key=lambda item: (item[1].get("position", {}).get("z", 0), item[1].get("position", {}).get("x", 0), item[0]))
            results = []
            for operative_id, model in pending_models:
                self._deployment_legality(side, model)
                setup_state["pending_side"] = side_id
                setup_state["pending_operative_id"] = operative_id
                setup_state["pending_model_guid"] = str(model.get("guid") or "")
                side["pending_operative_id"] = operative_id
                results.append(self._complete_setup_deployment(side_id, operative_id, model))
            result = copy.deepcopy(results[-1])
            result["deployed_count"] = len(results)
            result["batch_complete"] = setup_state.get("current_side") != side_id
            return self._recorded_result(action_id, result)
        if len(pending_cards) > 1:
            raise KillTeamRuleError("only one setup card may be pending deployment at a time")
        pending = pending_cards[0]
        setup_state["pending_side"] = side_id
        setup_state["pending_operative_id"] = pending["operative_id"]
        side["pending_operative_id"] = pending["operative_id"]
        try:
            setup_state["pending_model_guid"] = self._setup_operative_model_item(side, pending["operative_id"], side_id)["guid"]
        except Exception:
            setup_state["pending_model_guid"] = None
        matching = [
            obj
            for obj in self._objects.values()
            if _norm(_metadata(obj).get("entity")) == "operative"
            and str(_metadata(obj).get("operative_id") or "").strip() == pending["operative_id"]
            and _norm(_metadata(obj).get("side_id") or _metadata(obj).get("team")) == side_id
        ]
        if not matching:
            return {
                "status": "waiting_for_model",
                "side_id": side_id,
                "operative_id": pending["operative_id"],
                "model_guid": setup_state.get("pending_model_guid"),
            }
        if len(matching) != 1:
            raise KillTeamRuleError(f"deployment model identity is ambiguous for {pending['operative_id']}")
        self._deployment_legality(side, matching[0])
        result = self._complete_setup_deployment(side_id, pending["operative_id"], matching[0])
        return self._recorded_result(action_id, result)

    def get_roster(self) -> dict[str, Any]:
        """Return bounded contents of the dedicated AI roster container."""
        self._require_state()
        container_guid = str(self.config.roster_container_guid).strip()
        if not container_guid:
            raise KillTeamSetupError("the AI roster container is not configured")
        try:
            result = self.bridge.get_roster(container_guid)
        except Exception as exc:
            raise KillTeamSetupError("the AI roster container could not be inspected") from exc
        if not isinstance(result, dict):
            raise KillTeamSetupError("the AI roster response was invalid")
        if str(result.get("container_guid", "")).lower() != container_guid.lower():
            raise KillTeamSetupError("the roster response came from an unexpected container")
        items = result.get("items", [])
        if not isinstance(items, list):
            raise KillTeamSetupError("the roster contents were not a list")
        bounded = copy.deepcopy(result)
        bounded["items"] = [item for item in items[:200] if isinstance(item, dict)]
        bounded["truncated"] = bool(result.get("truncated")) or len(items) > 200
        return bounded

    def _record(self, event_type: str, payload: dict[str, Any]) -> None:
        state = self._require_state()
        event = {
            "sequence": len(self._events) + 1,
            "event_type": event_type,
            "state_revision": state["revision"],
            "map_revision": state["map_revision"],
            "payload": copy.deepcopy(payload),
        }
        self._events.append(event)

    def _recorded_result(self, action_id: str | None, result: dict[str, Any]) -> dict[str, Any]:
        if action_id:
            self._action_results[action_id] = copy.deepcopy(result)
        return result

    def _replay_or_reject(self, action_id: str | None) -> dict[str, Any] | None:
        if not action_id:
            return None
        if action_id in self._uncertain_action_ids:
            raise KillTeamUncertainCommit(
                f"action {action_id} has uncertain commit status and requires read-only recovery"
            )
        result = self._action_results.get(action_id)
        return copy.deepcopy(result) if result is not None else None

    def _mark_uncertain(self, action_id: str | None) -> None:
        if action_id:
            self._uncertain_action_ids.add(action_id)

    def _operative(self, operative_id: str, *, visible: bool = True) -> dict[str, Any]:
        state = self._require_state()
        record = state["operatives"].get(operative_id)
        if record is None:
            raise KillTeamRuleError(f"unknown operative {operative_id}")
        if visible and record["team"] != self.config.ai_team and operative_id not in self._visible_operatives():
            raise KillTeamRuleError(f"operative {operative_id} is not visible")
        return record

    def _operative_by_guid(self, guid: str, *, visible: bool = True) -> tuple[str, dict[str, Any]]:
        state = self._require_state()
        ref = _norm(guid)
        for operative_id, candidate in state["operatives"].items():
            if _norm(candidate["guid"]) == ref:
                if visible and candidate["team"] != self.config.ai_team and operative_id not in self._visible_operatives():
                    raise KillTeamRuleError(f"operative {guid} is not visible")
                return operative_id, candidate
        raise KillTeamRuleError(f"unknown operative {guid}")

    def place_operative(
        self,
        guid: str,
        path: list[dict[str, float]],
        *,
        action_id: str | None = None,
        verification_tolerance: float = 0.05,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        if not path:
            raise KillTeamRuleError("placement path is required")
        if verification_tolerance <= 0:
            raise KillTeamRuleError("placement verification tolerance must be positive")
        operative_id, operative = self._operative_by_guid(guid, visible=False)
        if operative["team"] != self.config.ai_team:
            raise KillTeamRuleError("only the AI can place its own operative")
        if state["phase"] != "setup":
            if state.get("active_operative_id") != operative_id:
                raise KillTeamRuleError("only the active AI operative can move during a tactical turn")
            if int(operative.get("ap", 0)) < 1:
                raise KillTeamRuleError("operative has insufficient AP")
        previous = operative["position"]
        total = 0.0
        for point in path:
            current = {axis: _number(point.get(axis, 0), f"path.{axis}") for axis in ("x", "y", "z")}
            total += math.hypot(current["x"] - previous["x"], current["z"] - previous["z"])
            previous = current
        if state["phase"] != "setup" and total / state["units_per_inch"] > float(operative["profile"]["move"]):
            raise KillTeamRuleError("movement exceeds the operative's move characteristic")
        target = previous
        try:
            self.bridge.move_object(operative["guid"], target)
            actual = self.bridge.get_object(operative["guid"])
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("operative placement commit is uncertain") from exc
        try:
            actual_position = _position(actual)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("operative placement readback is invalid") from exc
        if any(
            abs(actual_position[axis] - target[axis]) > verification_tolerance
            for axis in ("x", "y", "z")
        ):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("operative placement did not verify")
        operative["position"] = actual_position
        if state["phase"] != "setup":
            operative["ap"] = max(0, int(operative.get("ap", 0)) - 1)
        state["revision"] += 1
        self._record("operative.placed", {"operative_id": operative_id, "guid": operative["guid"], "position": actual_position})
        return self._recorded_result(action_id, {
            "status": "verified",
            "operative_id": operative_id,
            "guid": operative["guid"],
            "position": actual_position,
            "ap": operative.get("ap"),
            "revision": state["revision"],
        })

    def plan_objective_move(
        self,
        operative_id: str,
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """Plan a bounded objective-control move and return a MOVE command target."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        self.observe()
        operative = self._operative(operative_id, visible=False)
        if operative["team"] != self.config.ai_team:
            raise KillTeamRuleError("only the AI can plan an objective-control move for its own operative")

        objective_objects = [
            {
                "guid": guid,
                "name": str(obj.get("name") or ""),
                "position": _position(obj),
                "bounds": _bounds(obj),
            }
            for guid, obj in self._objects.items()
            if _norm(_metadata(obj).get("entity")) == "objective" and _bounds(obj) is not None
        ]
        if not objective_objects:
            raise KillTeamRuleError("no mission objectives are available")

        current = operative["position"]
        live_object = self._objects.get(operative["guid"], {})
        model_bounds = _bounds(live_object)
        if model_bounds is None:
            model_bounds = _bounds(operative)
        if model_bounds is None:
            raise KillTeamRuleError("the operative is missing usable bounds")
        model_half_x = max(0.1, (model_bounds[1] - model_bounds[0]) / 2)
        model_half_z = max(0.1, (model_bounds[3] - model_bounds[2]) / 2)

        combat_zone_bounds = None
        combat_zone_guid = str(state.get("combat_zone_guid") or "").strip()
        if combat_zone_guid and combat_zone_guid in self._objects:
            combat_zone_bounds = _bounds(self._objects[combat_zone_guid])

        blockers: list[dict[str, Any]] = []
        for guid, obj in self._objects.items():
            if guid == operative["guid"]:
                continue
            entity = _norm(_metadata(obj).get("entity"))
            if entity not in {"terrain", "objective", "operative"}:
                continue
            bounds = _bounds(obj)
            if bounds is None:
                continue
            blockers.append({
                "guid": guid,
                "entity": entity,
                "bounds": bounds,
                "position": _position(obj),
                "name": str(obj.get("name") or ""),
            })

        enemies = [
            {
                "operative_id": record["operative_id"],
                "guid": record["guid"],
                "position": copy.deepcopy(record["position"]),
                "name": str(record.get("name") or ""),
            }
            for record in self._visible_operatives().values()
            if record["team"] != self.config.ai_team and int(record.get("wounds", 0)) > 0
        ]

        move_range = float(operative["profile"]["move"]) * float(state["units_per_inch"])
        grid_step = 0.5
        max_steps = max(1, int(math.ceil(move_range / grid_step)))

        def candidate_rect(x: float, z: float) -> tuple[float, float, float, float]:
            return (x - model_half_x, x + model_half_x, z - model_half_z, z + model_half_z)

        def candidate_is_legal(x: float, z: float) -> bool:
            rect = candidate_rect(x, z)
            if combat_zone_bounds is not None and not _rect_contains_rect(combat_zone_bounds, rect):
                return False
            for blocker in blockers:
                if _rects_overlap(rect, blocker["bounds"]):
                    return False
            return True

        def candidate_summary(objective: dict[str, Any], x: float, z: float, *, contestable: bool) -> dict[str, Any]:
            position = {"x": x, "y": current["y"], "z": z}
            objective_position = objective["position"]
            exposure = 0
            cover_score = 0
            for enemy in enemies:
                blocked_by = 0
                for blocker in blockers:
                    if blocker["guid"] == enemy["guid"]:
                        continue
                    if _segment_intersects_rect(position, enemy["position"], blocker["bounds"]):
                        blocked_by += 1
                if blocked_by == 0:
                    exposure += 1
                cover_score += blocked_by
            path_distance = math.hypot(x - current["x"], z - current["z"])
            objective_distance = math.hypot(x - objective_position["x"], z - objective_position["z"])
            return {
                "objective": copy.deepcopy(objective),
                "target_position": position,
                "contestable": contestable,
                "exposure": exposure,
                "cover_score": cover_score,
                "path_distance": path_distance,
                "objective_distance": objective_distance,
                "score_contest": (exposure, -cover_score, path_distance, objective_distance, x, z),
                "score_staging": (exposure, -cover_score, objective_distance, path_distance, x, z),
            }

        objective_plans: list[dict[str, Any]] = []
        for objective in objective_objects:
            objective_bounds = objective["bounds"]
            assert objective_bounds is not None
            objective_center = _rect_center(objective_bounds)
            objective_radius = max(
                (objective_bounds[1] - objective_bounds[0]) / 2,
                (objective_bounds[3] - objective_bounds[2]) / 2,
            )
            contest_radius = objective_radius + max(model_half_x, model_half_z) + 0.5
            contestable_candidates: list[dict[str, Any]] = []
            staging_candidates: list[dict[str, Any]] = []
            for ix in range(-max_steps, max_steps + 1):
                x = current["x"] + (ix * grid_step)
                for iz in range(-max_steps, max_steps + 1):
                    z = current["z"] + (iz * grid_step)
                    if math.hypot(x - current["x"], z - current["z"]) > move_range + 1e-6:
                        continue
                    if not candidate_is_legal(x, z):
                        continue
                    objective_distance = math.hypot(x - objective_center["x"], z - objective_center["z"])
                    if objective_distance > contest_radius + 1e-6:
                        staging_candidates.append(candidate_summary(objective, x, z, contestable=False))
                        continue
                    summary = candidate_summary(objective, x, z, contestable=True)
                    contestable_candidates.append(summary)
                    staging_candidates.append(summary)

            best_contestable = min(contestable_candidates, key=lambda item: item["score_contest"]) if contestable_candidates else None
            best_staging = min(staging_candidates, key=lambda item: item["score_staging"]) if staging_candidates else None
            objective_plans.append({
                "objective": objective,
                "objective_distance": math.hypot(current["x"] - objective_center["x"], current["z"] - objective_center["z"]),
                "best_contestable": best_contestable,
                "best_staging": best_staging,
            })

        contestable_plans = [plan for plan in objective_plans if plan["best_contestable"] is not None]
        if contestable_plans:
            selected_plan = min(
                contestable_plans,
                key=lambda plan: (
                    plan["best_contestable"]["score_contest"],
                    plan["objective_distance"],
                    str(plan["objective"]["guid"]),
                ),
            )
            selected_candidate = copy.deepcopy(selected_plan["best_contestable"])
            mode = "contest"
        else:
            selected_plan = min(
                objective_plans,
                key=lambda plan: (
                    plan["objective_distance"],
                    str(plan["objective"]["guid"]),
                ),
            )
            if selected_plan["best_staging"] is None:
                raise KillTeamRuleError("no legal tactical staging point could be found")
            selected_candidate = copy.deepcopy(selected_plan["best_staging"])
            mode = "staging"

        target_position = copy.deepcopy(selected_candidate["target_position"])
        move_command = f"MOVE[{operative['guid']},{target_position['x']},{target_position['y']},{target_position['z']}]"
        result = {
            "status": "planned",
            "mode": mode,
            "operative_id": operative_id,
            "guid": operative["guid"],
            "move_command": move_command,
            "target_position": target_position,
            "objective": copy.deepcopy(selected_plan["objective"]),
            "selection": selected_candidate,
            "objective_count": len(objective_objects),
            "planned_objective_count": len(objective_plans),
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def deploy_test_model(self, *, action_id: str | None = None) -> dict[str, Any]:
        """Move the named test model to the tagged deployment zone without setup."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        model_name = "Plague Marine Warrior"
        target_tag = "_deployment_zone_blue"
        try:
            snapshot = self.bridge.list_objects(max_results=1000, compact=True)
        except Exception as exc:
            raise KillTeamSetupError("test deployment objects could not be inspected") from exc
        objects = snapshot.get("objects", []) if isinstance(snapshot, dict) else []
        if not isinstance(objects, list):
            raise KillTeamSetupError("test deployment object listing was invalid")

        def unique_tagged(tag: str) -> dict[str, Any]:
            wanted = tag.casefold()
            matches = [
                obj
                for obj in objects
                if isinstance(obj, dict)
                and any(
                    str(value).strip().casefold() == wanted
                    for value in obj.get("tags", [])
                )
            ]
            if len(matches) != 1:
                raise KillTeamSetupError(
                    f"test deployment tag {tag} must resolve to exactly one object; "
                    f"found {len(matches)}"
                )
            return matches[0]

        wanted_model_name = model_name.casefold()
        named_models = [
            obj
            for obj in objects
            if isinstance(obj, dict)
            and wanted_model_name in str(obj.get("name", "")).casefold()
        ]
        if len(named_models) != 1:
            raise KillTeamSetupError(
                f"test deployment name {model_name} must resolve to exactly one object; "
                f"found {len(named_models)}"
            )
        model = named_models[0]
        target_marker = unique_tagged(target_tag)
        model_guid = _live_object_guid(model.get("guid"))
        target_guid = _live_object_guid(target_marker.get("guid"))
        if model_guid is None or target_guid is None:
            raise KillTeamSetupError("test deployment objects have invalid live GUIDs")
        marker_position = _position(target_marker)
        marker_box = _bounds_box(target_marker)
        support_surfaces = self._terrain_support_surfaces(objects)
        rect = self._setup_board_projected_rect(model, marker_position)
        support = self._setup_board_slot_support(
            {
                "deployment_floor_y": marker_box["min_y"] if marker_box is not None else marker_position["y"],
                "support_surfaces": support_surfaces,
            },
            rect,
        )
        model_height = self._setup_board_model_height(model)
        target = {
            "x": marker_position["x"],
            "y": round(float(support["support_height"]) + model_height / 2, 6),
            "z": marker_position["z"],
        }
        try:
            actual_object = self.bridge.move_object(model_guid, target)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("test deployment commit is uncertain") from exc
        try:
            actual = _position(actual_object)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("test deployment readback is invalid") from exc
        distance_to_target = math.hypot(
            actual["x"] - target["x"],
            actual["z"] - target["z"],
        )
        if distance_to_target > 0.25 or any(abs(actual[axis] - target[axis]) > 0.05 for axis in ("y",)):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("test deployment did not reach the tagged marker")
        result = {
            "status": "verified",
            "operation": "test_deployment",
            "guid": model_guid,
            "model_name": model_name,
            "target_guid": target_guid,
            "target_tag": target_tag,
            "target_position": target,
            "position": actual,
            "distance_to_target": distance_to_target,
            "tolerance": 0.25,
        }
        if self._state is not None:
            self._state["revision"] += 1
            result["revision"] = self._state["revision"]
            self._record("test_deployment.completed", result)
        return self._recorded_result(action_id, result)

    def activate_operative(self, operative_id: str) -> dict[str, Any]:
        state = self._require_state()
        self.observe()
        operative = self._operative(operative_id, visible=False)
        if operative["team"] != self.config.ai_team:
            raise KillTeamRuleError("only an AI operative can activate")
        if state["active_operative_id"] is not None:
            raise KillTeamRuleError("an operative is already active")
        state["phase"] = "firefight"
        state["active_operative_id"] = operative_id
        operative["ap"] = int(operative["profile"]["apl"])
        state["revision"] += 1
        self._record("activation.started", {"operative_id": operative_id})
        return {"status": "active", "operative_id": operative_id, "ap": operative["ap"], "revision": state["revision"]}

    def take_tactical_turn(
        self,
        *,
        trigger: str = "",
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """Take one bounded AI tactical turn, then pass initiative onward."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        if state["phase"] == "setup":
            raise KillTeamRuleError("tactical turns are unavailable during setup")

        self.observe()
        state["turn_status"] = "running"
        state["turn_owner"] = self.config.ai_team
        state["initiative_side"] = self.config.ai_team
        initiative_token = self._move_initiative_token(self.config.ai_team, action_id=action_id)

        actions: list[dict[str, Any]] = []
        selection_reason = ""

        def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
            return math.hypot(float(a["position"]["x"]) - float(b["position"]["x"]), float(a["position"]["z"]) - float(b["position"]["z"]))

        def _tactical_move_target(operative: dict[str, Any]) -> tuple[dict[str, float] | None, str]:
            objectives = [
                {
                    "guid": guid,
                    "name": str(obj.get("name") or ""),
                    "position": _position(obj),
                    "bounds": _bounds(obj),
                }
                for guid, obj in self._objects.items()
                if _norm(_metadata(obj).get("entity")) == "objective" and _bounds(obj) is not None
            ]
            if objectives:
                try:
                    plan = self.plan_objective_move(operative["operative_id"], action_id=f"{action_id}:plan" if action_id else None)
                except (KillTeamRuleError, KillTeamSetupError):
                    plan = None
                if isinstance(plan, dict) and isinstance(plan.get("target_position"), dict):
                    target = plan["target_position"]
                    try:
                        return {axis: float(target[axis]) for axis in ("x", "y", "z")}, str(plan.get("mode", "objective"))
                    except (KeyError, TypeError, ValueError):
                        pass
            visible_targets = [
                record
                for record in self._visible_operatives().values()
                if record["team"] != self.config.ai_team and int(record.get("wounds", 0)) > 0
            ]
            if not visible_targets:
                return None, "no_movement_target"
            target = min(
                visible_targets,
                key=lambda record: (
                    _distance(operative, record),
                    str(record["operative_id"]),
                ),
            )
            move_range = float(operative["profile"]["move"]) * float(state["units_per_inch"])
            current = operative["position"]
            dx = float(target["position"]["x"]) - float(current["x"])
            dz = float(target["position"]["z"]) - float(current["z"])
            distance = math.hypot(dx, dz)
            if distance <= 1e-6:
                return None, "already_at_target"
            step = min(move_range, distance)
            scale = step / distance
            return {
                "x": float(current["x"]) + dx * scale,
                "y": float(current["y"]),
                "z": float(current["z"]) + dz * scale,
            }, f"advance_toward_{target['operative_id']}"

        def _best_shot(operative: dict[str, Any]) -> dict[str, Any] | None:
            visible_targets = [
                record
                for record in self._visible_operatives().values()
                if record["team"] != self.config.ai_team and int(record.get("wounds", 0)) > 0
            ]
            if not visible_targets:
                return None
            weapons = [
                (weapon_id, weapon)
                for weapon_id, weapon in sorted(operative.get("profile", {}).get("weapons", {}).items())
                if isinstance(weapon, dict)
            ]
            if not weapons:
                return None
            candidates: list[tuple[tuple[float, float, float, str, str], dict[str, Any]]] = []
            for target in sorted(visible_targets, key=lambda item: (str(item["operative_id"]), str(item["guid"]))):
                try:
                    evidence = self.probe_line_of_sight(operative["operative_id"], target["operative_id"])
                except KillTeamError:
                    continue
                if not evidence.get("visible", False):
                    continue
                distance = math.hypot(
                    float(operative["position"]["x"]) - float(target["position"]["x"]),
                    float(operative["position"]["z"]) - float(target["position"]["z"]),
                ) / float(state["units_per_inch"])
                for weapon_id, weapon in weapons:
                    weapon_range = weapon.get("range")
                    if weapon_range is not None and distance > float(weapon_range):
                        continue
                    score = (
                        float(weapon.get("damage", 0)),
                        float(weapon.get("attacks", 0)),
                        -distance,
                        str(target["operative_id"]),
                        str(weapon_id),
                    )
                    candidates.append((score, {
                        "weapon_id": str(weapon_id),
                        "target_id": str(target["operative_id"]),
                        "distance": distance,
                        "los_evidence": evidence,
                    }))
            if not candidates:
                return None
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

        active_id = state.get("active_operative_id")
        if active_id is None:
            choice: dict[str, Any] | None = None
            best_score: tuple[float, float, float, str] | None = None
            for record in sorted(self._visible_operatives().values(), key=lambda item: (str(item["operative_id"]), str(item["guid"]))):
                if record["team"] != self.config.ai_team or int(record.get("wounds", 0)) <= 0:
                    continue
                shot = _best_shot(record)
                move_target, move_reason = _tactical_move_target(record)
                score = (
                    1.0 if shot is not None else 0.0,
                    float(record.get("ap", 0)),
                    -min(
                        [
                            shot["distance"] if shot is not None else 9999.0,
                            math.hypot(
                                float(record["position"]["x"]) - float(move_target["x"]),
                                float(record["position"]["z"]) - float(move_target["z"]),
                            ) if move_target is not None else 9999.0,
                        ]
                    ),
                    str(record["operative_id"]),
                )
                if best_score is None or score > best_score:
                    best_score = score
                    choice = {
                        "operative_id": str(record["operative_id"]),
                        "reason": "shoot" if shot is not None else move_reason,
                        "shot": shot,
                        "move_target": move_target,
                    }
            if choice is None:
                state["phase"] = "command"
                state["turn_owner"] = "opponent"
                state["initiative_side"] = "opponent"
                state["turn_status"] = "passed"
                state["turn_sequence"] = int(state.get("turn_sequence", 0)) + 1
                state["turn_history"].append({
                    "trigger": str(trigger),
                    "actions": [],
                    "reason": "no_legal_ai_operatives",
                    "initiative_passed_to": "opponent",
                })
                state["revision"] += 1
                self._record(
                    "tactical_turn.completed",
                    {
                        "trigger": str(trigger),
                        "actions": [],
                        "initiative_passed_to": "opponent",
                        "reason": "no_legal_ai_operatives",
                    },
                )
                return self._recorded_result(action_id, {
                    "status": "passed",
                    "reason": "no legal AI operative was available to activate",
                    "initiative_side": state.get("initiative_side"),
                    "initiative_token": initiative_token,
                    "turn_owner": state.get("turn_owner"),
                    "turn_status": state.get("turn_status"),
                    "turn_sequence": state.get("turn_sequence"),
                    "revision": state["revision"],
                })
            selection_reason = str(choice.get("reason") or "")
            activation = self.activate_operative(choice["operative_id"])
            actions.append({"action": "activate_operative", "result": activation, "reason": selection_reason})
            active_id = state.get("active_operative_id")

        max_steps = 8
        for step in range(max_steps):
            self.observe()
            active_id = state.get("active_operative_id")
            if active_id is None:
                break
            operative = self._operative(str(active_id), visible=False)
            if operative["team"] != self.config.ai_team:
                break
            if int(operative.get("ap", 0)) <= 0:
                break
            shot = _best_shot(operative)
            if shot is not None:
                result = self.shoot(
                    operative["operative_id"],
                    shot["target_id"],
                    shot["weapon_id"],
                    action_id=f"{action_id}:shoot:{step}" if action_id else None,
                )
                actions.append({"action": "shoot", "result": result})
                break
            move_target, move_reason = _tactical_move_target(operative)
            if move_target is not None:
                result = self.place_operative(
                    operative["guid"],
                    [copy.deepcopy(move_target)],
                    action_id=f"{action_id}:move:{step}" if action_id else None,
                )
                actions.append({"action": "move_operative", "result": result, "reason": move_reason})
                break
            break

        if state.get("active_operative_id") is not None:
            ended = self.end_activation(action_id=f"{action_id}:end" if action_id else None)
            actions.append({"action": "end_activation", "result": ended})

        state["phase"] = "command"
        state["turn_owner"] = "opponent"
        state["initiative_side"] = "opponent"
        state["turn_status"] = "passed"
        state["turn_sequence"] = int(state.get("turn_sequence", 0)) + 1
        state["turn_history"].append({
            "trigger": str(trigger),
            "actions": copy.deepcopy(actions),
            "selection_reason": selection_reason,
            "initiative_passed_to": "opponent",
        })
        state["revision"] += 1
        self._record(
            "tactical_turn.completed",
            {
                "trigger": str(trigger),
                "actions": copy.deepcopy(actions),
                "initiative_passed_to": "opponent",
            },
        )
        return self._recorded_result(action_id, {
            "status": "passed",
            "trigger": str(trigger),
            "actions": actions,
            "initiative_side": state.get("initiative_side"),
            "initiative_token": initiative_token,
            "turn_owner": state.get("turn_owner"),
            "turn_status": state.get("turn_status"),
            "turn_sequence": state.get("turn_sequence"),
            "revision": state["revision"],
        })

    def _line_of_sight(self, attacker: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[str]]:
        state = self._require_state()
        blockers = []
        for terrain in state["terrain"]:
            if terrain["blocks_los"] and terrain["bounds"] and _segment_intersects_rect(attacker["position"], target["position"], terrain["bounds"]):
                blockers.append(terrain["guid"])
        return not blockers, blockers

    def _probe_line_of_sight(
        self,
        attacker: dict[str, Any],
        target: dict[str, Any],
        *,
        eye_local: dict[str, float] | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        """Ask TTS for bounded sampled-ray evidence and validate its identity."""
        try:
            raw = self.bridge.probe_line_of_sight(
                attacker["guid"],
                target["guid"],
                eye_local=eye_local,
                debug=debug,
            )
        except Exception as exc:
            raise KillTeamRuleError("line of sight probe failed") from exc
        if not isinstance(raw, dict):
            raise KillTeamRuleError("line of sight probe returned an invalid result")
        if str(raw.get("observer_guid", "")) != str(attacker["guid"]):
            raise KillTeamRuleError("line of sight probe observer does not match the attacker")
        if str(raw.get("target_guid", "")) != str(target["guid"]):
            raise KillTeamRuleError("line of sight probe target does not match the target")
        if not isinstance(raw.get("visible"), bool):
            raise KillTeamRuleError("line of sight probe did not return a visibility decision")
        try:
            total_rays = int(raw.get("total_rays", 0))
            visible_rays = int(raw.get("visible_rays", 0))
            visibility_fraction = float(raw.get("visibility_fraction", -1))
        except (TypeError, ValueError) as exc:
            raise KillTeamRuleError("line of sight probe returned invalid ray counts") from exc
        samples = raw.get("samples", [])
        if total_rays != 9 or not isinstance(samples, list) or len(samples) > 9:
            raise KillTeamRuleError("line of sight probe exceeded the nine-ray evidence contract")
        if not 0 <= visible_rays <= total_rays or not 0 <= visibility_fraction <= 1:
            raise KillTeamRuleError("line of sight probe returned invalid visibility evidence")
        evidence = copy.deepcopy(raw)
        evidence.update({
            "attacker_id": attacker["operative_id"],
            "target_id": target["operative_id"],
            "total_rays": total_rays,
            "visible_rays": visible_rays,
            "visibility_fraction": visibility_fraction,
        })
        return evidence

    def probe_line_of_sight(
        self,
        attacker_id: str,
        target_id: str,
        *,
        eye_local: dict[str, float] | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        """Return physical LOS evidence without mutating the game."""
        self._require_state()
        self.observe()
        attacker = self._operative(attacker_id, visible=False)
        target = self._operative(target_id)
        if attacker["team"] != self.config.ai_team:
            raise KillTeamRuleError("only an AI operative can probe line of sight")
        if target["team"] == self.config.ai_team:
            raise KillTeamRuleError("the AI cannot probe its own operative")
        return self._probe_line_of_sight(attacker, target, eye_local=eye_local, debug=debug)

    def begin_setup_validation(
        self,
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """Place the Save 131 subject and roll only the AI side of the test shot."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        profile = self._fixture_profile
        if profile is None:
            raise KillTeamRuleError("setup validation requires the Save 131 fixture profile")
        if state.get("pending_validation") is not None:
            raise KillTeamRuleError("a setup validation shot is already awaiting Red")

        attacker_id = str(state.get("deployment_subject_id") or "")
        target_id = str(state.get("visible_target_id") or "")
        snap = state.get("start_test_spot") or {}
        snap_position = snap.get("position")
        if not attacker_id or not target_id or not isinstance(snap_position, dict):
            raise KillTeamSetupError("Save 131 validation roles are incomplete")

        attacker = self._operative(attacker_id, visible=False)
        placement_action_id = f"{action_id}:placement" if action_id else None
        placement = self.place_operative(
            attacker["guid"],
            [copy.deepcopy(snap_position)],
            action_id=placement_action_id,
        )
        self.activate_operative(attacker_id)
        target = self._operative(target_id)
        weapon_id = "boltgun"
        weapon = attacker["profile"].get("weapons", {}).get(weapon_id)
        if weapon is None:
            raise KillTeamRuleError("the deployment subject does not have a Boltgun")
        los_evidence = self._probe_line_of_sight(attacker, target)
        if not los_evidence["visible"]:
            raise KillTeamRuleError("the validation target is not visible after placement")

        attack_count = int(weapon["attacks"])
        ai_dice = state["dice_by_team"].get(self.config.ai_team, [])[:attack_count]
        if len(ai_dice) != attack_count:
            raise KillTeamRuleError("the AI dice pool is too small for the Boltgun")
        try:
            rolled = self.bridge.roll_dice(
                team=self.config.ai_team,
                dice_guids=ai_dice,
                roller_guid=state["roller_guid"],
                purpose="attack",
                die_tag=profile.ai_dice_tag,
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit(
                "AI attack dice may have rolled; use read-only recovery"
            ) from exc
        raw_faces = rolled.get("faces", []) if isinstance(rolled, dict) else []
        if len(raw_faces) != attack_count or any(face is None for face in raw_faces):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("AI attack dice rolled but faces were incomplete")
        try:
            attack_faces = [int(face) for face in raw_faces]
        except (TypeError, ValueError) as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("AI attack dice returned an invalid face") from exc

        attacker["ap"] -= 1
        state["revision"] += 1
        pending = {
            "attacker_id": attacker_id,
            "target_id": target_id,
            "weapon_id": weapon_id,
            "attack_faces": attack_faces,
            "los_evidence": los_evidence,
            "defense_station_guid": profile.defense_station_guid,
            "expected_defense_dice": int(target["defense_dice"]),
        }
        state["pending_validation"] = pending
        self._record("setup_validation.awaiting_red_defense", pending)
        result = {
            "status": "awaiting_red_defense_roll",
            "attacker_id": attacker_id,
            "attacker_guid": attacker["guid"],
            "target_id": target_id,
            "target_guid": target["guid"],
            "placement": placement,
            "los_evidence": los_evidence,
            "attack_roll": attack_faces,
            "defense_station_guid": profile.defense_station_guid,
            "red_instruction": (
                "Red rolls three defense dice at 4+ in station f1adc9, then Red or "
                "the host acknowledges that the defense roll is complete."
            ),
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def complete_setup_validation(
        self,
        *,
        acknowledged_by: str,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """Read Red's settled dice after explicit acknowledgment and resolve damage."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        if str(acknowledged_by).strip().casefold() not in {"red", "host", "white, host"}:
            raise KillTeamRuleError("Red or the host must acknowledge the defense roll")
        pending = state.get("pending_validation")
        if not isinstance(pending, dict):
            raise KillTeamRuleError("no setup validation shot is awaiting Red")
        target = self._operative(str(pending["target_id"]))
        attacker = self._operative(str(pending["attacker_id"]), visible=False)
        weapon = attacker["profile"]["weapons"][str(pending["weapon_id"])]
        expected_count = int(pending["expected_defense_dice"])
        try:
            observed = self.bridge.observe_defense_roll(
                station_guid=str(pending["defense_station_guid"]),
                expected_count=expected_count,
            )
        except Exception as exc:
            raise KillTeamRuleError("Red defense dice could not be observed") from exc
        raw_faces = observed.get("faces", []) if isinstance(observed, dict) else []
        if len(raw_faces) != expected_count or any(face is None for face in raw_faces):
            raise KillTeamRuleError("Red defense station does not contain three settled dice")
        try:
            defense_faces = [int(face) for face in raw_faces]
        except (TypeError, ValueError) as exc:
            raise KillTeamRuleError("Red defense dice returned an invalid face") from exc

        attack_faces = [int(face) for face in pending["attack_faces"]]
        resolution = _resolve_ranged_successes(
            attack_faces,
            defense_faces,
            hit=int(weapon["hit"]),
            save=int(target["save"]),
            normal_damage=int(weapon["damage"]),
            critical_damage=int(weapon.get("critical_damage", weapon["damage"])),
        )
        hits = resolution["critical_hits"] + resolution["normal_hits"]
        saves = resolution["critical_saves"] + resolution["normal_saves"]
        unblocked_hits = (
            resolution["unblocked_critical_hits"]
            + resolution["unblocked_normal_hits"]
        )
        damage = resolution["damage"]
        expected_wounds = int(target["wounds"])
        expected_after = max(0, expected_wounds - damage)
        try:
            projection = self.bridge.apply_damage(
                target["guid"],
                damage=damage,
                expected_wounds=expected_wounds,
            )
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit(
                "damage may have committed; use read-only wound recovery"
            ) from exc
        if (
            not isinstance(projection, dict)
            or str(projection.get("guid", "")) != target["guid"]
            or int(projection.get("before_wounds", -1)) != expected_wounds
            or int(projection.get("after_wounds", -1)) != expected_after
        ):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("operative wound readback did not verify")

        target["wounds"] = expected_after
        state["pending_validation"] = None
        state["revision"] += 1
        event = {
            "attacker_id": attacker["operative_id"],
            "target_id": target["operative_id"],
            "weapon_id": pending["weapon_id"],
            "attack_faces": attack_faces,
            "defense_faces": defense_faces,
            "damage": damage,
            "target_wounds": expected_after,
        }
        self._record("setup_validation.resolved", event)
        result = {
            "status": "resolved",
            "attack_roll": attack_faces,
            "defense_roll": defense_faces,
            "hits": hits,
            "saves": saves,
            "unblocked_hits": unblocked_hits,
            "damage": damage,
            "target_wounds": expected_after,
            "wound_projection": copy.deepcopy(projection),
            "revision": state["revision"],
        }
        result.update(resolution)
        return self._recorded_result(action_id, result)

    def shoot(self, attacker_id: str, target_id: str, weapon_id: str, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        self.observe()
        attacker = self._operative(attacker_id, visible=False)
        target = self._operative(target_id)
        if target["team"] == self.config.ai_team:
            raise KillTeamRuleError("the AI cannot target its own operative")
        if target["wounds"] <= 0:
            raise KillTeamRuleError("target operative is already incapacitated")
        if state["active_operative_id"] != attacker_id:
            raise KillTeamRuleError("attacker is not the active AI operative")
        if attacker["ap"] < 1:
            raise KillTeamRuleError("operative has insufficient AP")
        weapon = attacker["profile"].get("weapons", {}).get(weapon_id.lower())
        if weapon is None:
            raise KillTeamRuleError(f"operative does not have weapon {weapon_id}")
        distance = math.hypot(
            attacker["position"]["x"] - target["position"]["x"],
            attacker["position"]["z"] - target["position"]["z"],
        ) / state["units_per_inch"]
        if weapon.get("range") is not None and distance > float(weapon["range"]):
            raise KillTeamRuleError("target is out of range")
        los_evidence = self._probe_line_of_sight(attacker, target)
        if not los_evidence["visible"]:
            blockers = [
                str(guid)
                for guid in los_evidence.get("blocker_guids", [])
                if str(guid).strip()
            ]
            blocker_text = ", ".join(dict.fromkeys(blockers)) or "the target silhouette"
            raise KillTeamRuleError(f"line of sight is blocked by {blocker_text}")

        ai_dice = state["dice_by_team"].get(self.config.ai_team, [])[: int(weapon["attacks"])]
        opponent_dice = state["dice_by_team"].get("opponent", [])[: int(target["defense_dice"])]
        if len(ai_dice) < int(weapon["attacks"]):
            raise KillTeamRuleError("the AI dice pool is too small for this attack")
        if len(opponent_dice) < int(target["defense_dice"]):
            raise KillTeamRuleError("the opponent defense dice pool is too small")
        try:
            attack_roll = self.bridge.roll_dice(team=self.config.ai_team, dice_guids=ai_dice, roller_guid=state["roller_guid"], purpose="attack")
            defense_roll = self.bridge.roll_dice(team="opponent", dice_guids=opponent_dice, roller_guid=state["roller_guid"], purpose="defense")
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("dice roll commit is uncertain; action was not retried") from exc
        raw_attack_faces = attack_roll.get("faces", []) if isinstance(attack_roll, dict) else []
        raw_defense_faces = defense_roll.get("faces", []) if isinstance(defense_roll, dict) else []
        if (
            len(raw_attack_faces) != int(weapon["attacks"])
            or len(raw_defense_faces) != int(target["defense_dice"])
            or any(face is None for face in [*raw_attack_faces, *raw_defense_faces])
        ):
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("physical dice rolled but one or more faces could not be read")
        try:
            attack_faces = [int(face) for face in raw_attack_faces]
            defense_faces = [int(face) for face in raw_defense_faces]
        except (TypeError, ValueError) as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("physical dice returned an invalid face") from exc
        hits = sum(face >= int(weapon["hit"]) for face in attack_faces)
        saves = sum(face >= int(target["save"]) for face in defense_faces)
        unblocked_hits = max(0, hits - saves)
        damage = unblocked_hits * int(weapon["damage"])
        target["wounds"] = max(0, int(target["wounds"]) - damage)
        attacker["ap"] -= 1
        target_object = self._objects.get(target["guid"], {})
        target_name = str(target_object.get("name") or target_id)
        wound_text = f"{{{target['wounds']}/{target['max_wounds']}}}"
        if re.search(r"\{\d+\s*/\s*\d+\}", target_name):
            target_name = re.sub(r"\{\d+\s*/\s*\d+\}", wound_text, target_name, count=1)
        else:
            target_name = f"{wound_text} {target_name}".strip()
        try:
            self.bridge.set_object_name(target["guid"], target_name)
            projected = self.bridge.get_object(target["guid"])
            if str(projected.get("name") or "") != target_name:
                raise ValueError("target name readback did not match")
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamUncertainCommit("damage committed but wound projection is uncertain") from exc
        state["revision"] += 1
        self._record("shoot.resolved", {
            "attacker_id": attacker_id,
            "target_id": target_id,
            "weapon_id": weapon_id,
            "attack_faces": attack_faces,
            "defense_faces": defense_faces,
            "damage": damage,
        })
        result = {
            "status": "resolved",
            "attacker_id": attacker_id,
            "target_id": target_id,
            "weapon_id": weapon_id,
            "distance": distance,
            "los_evidence": los_evidence,
            "attack_roll": attack_faces,
            "defense_roll": defense_faces,
            "hits": hits,
            "saves": saves,
            "unblocked_hits": unblocked_hits,
            "damage": damage,
            "target_wounds": target["wounds"],
            "revision": state["revision"],
        }
        return self._recorded_result(action_id, result)

    def _counter_guid(self, counter_name: str) -> str:
        state = self._require_state()
        name = _norm(counter_name)
        guid = str(state["counter_guids"].get(name, "")).strip()
        if not guid:
            raise KillTeamRuleError(f"counter {counter_name} is not available")
        return guid

    def _counter_object(self, counter_name: str) -> tuple[str, dict[str, Any]]:
        guid = self._counter_guid(counter_name)
        obj = self._objects.get(guid)
        if obj is None:
            raise KillTeamRuleError(f"counter {counter_name} is missing from the live scene")
        return guid, obj

    def _apply_counter_delta(self, counter_name: str, delta: int) -> dict[str, Any]:
        guid, obj = self._counter_object(counter_name)
        current = obj.get("counter_value", 0)
        try:
            current_value = int(current)
        except (TypeError, ValueError) as exc:
            raise KillTeamRuleError(f"counter {counter_name} returned an invalid value") from exc
        updated = max(0, current_value + int(delta))
        try:
            projected = self.bridge.set_counter_value(guid, updated)
        except Exception as exc:
            raise KillTeamRuleError(f"counter {counter_name} could not be updated") from exc
        if not isinstance(projected, dict) or str(projected.get("guid", "")).strip() != guid:
            raise KillTeamRuleError(f"counter {counter_name} did not verify")
        obj["counter_value"] = updated
        return {
            "guid": guid,
            "name": str(obj.get("name") or counter_name),
            "before": current_value,
            "after": updated,
        }

    def _score_counter_name(self, counter_name: str) -> str:
        state = self._require_state()
        requested = _norm(counter_name)
        if requested in state["counter_guids"]:
            return requested
        if requested in {"", "objective", "vp", "victory_point", "victory_points"}:
            for candidate in ("vp", "kill_vp", "tac_vp", "crit_vp"):
                if candidate in state["counter_guids"]:
                    return candidate
        raise KillTeamRuleError(f"score counter {counter_name} is not available")

    def _objective_object(self, objective_id: str) -> dict[str, Any]:
        candidate = str(objective_id or "").strip()
        if not candidate:
            raise KillTeamRuleError("objective_id is required")
        matches: list[dict[str, Any]] = []
        for obj in self._objects.values():
            if _norm(_metadata(obj).get("entity")) != "objective":
                continue
            if str(obj.get("guid", "")).strip() == candidate:
                return obj
            if _norm(obj.get("name")) == _norm(candidate):
                matches.append(obj)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KillTeamRuleError(f"unknown objective {objective_id}")
        raise KillTeamRuleError(f"objective {objective_id} is ambiguous")

    def _spawn_marker(
        self,
        marker_type: str,
        position: dict[str, float],
        *,
        name: str = "",
        object_type: str = "BlockSquare",
        locked: bool = True,
    ) -> dict[str, Any]:
        marker_label = str(marker_type or "").strip()
        if not marker_label:
            raise KillTeamRuleError("marker_type is required")
        spawn_name = str(name or marker_label).strip() or marker_label
        spawn_position = {axis: _number(position.get(axis, 0), f"position.{axis}") for axis in ("x", "y", "z")}
        try:
            spawned = self.bridge.spawn_builtin(
                object_type=object_type,
                position=spawn_position,
                rotation={"x": 0.0, "y": 0.0, "z": 0.0},
                scale={"x": 0.6, "y": 0.2, "z": 0.6},
                name=spawn_name,
                locked=locked,
            )
        except Exception as exc:
            raise KillTeamRuleError("marker spawn failed") from exc
        if not isinstance(spawned, dict):
            raise KillTeamRuleError("marker spawn returned an invalid result")
        spawned_object = spawned.get("object") if isinstance(spawned.get("object"), dict) else None
        marker_guid = _live_object_guid(
            spawned_object.get("guid") if spawned_object is not None else spawned.get("guid")
        )
        if not marker_guid:
            raise KillTeamUncertainCommit("marker spawn did not return a stable GUID")
        try:
            projected = self.bridge.get_object(marker_guid)
        except Exception as exc:
            self._mark_uncertain(None)
            raise KillTeamUncertainCommit("marker spawn committed but the readback failed") from exc
        projected_position = _position(projected)
        for axis in ("x", "y", "z"):
            if not math.isclose(projected_position[axis], spawn_position[axis], abs_tol=0.05):
                self._mark_uncertain(None)
                raise KillTeamUncertainCommit("marker spawn did not verify at the requested position")
        actual_name = str(projected.get("name") or "").strip()
        if spawn_name and actual_name != spawn_name:
            self._mark_uncertain(None)
            raise KillTeamUncertainCommit("marker spawn did not verify its name")
        return {
            "guid": marker_guid,
            "marker_type": marker_label,
            "name": actual_name or spawn_name,
            "position": projected_position,
            "object_type": str(projected.get("type") or object_type),
            "locked": bool(projected.get("locked", locked)),
        }

    def end_activation(self, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        active_id = state.get("active_operative_id")
        if active_id is None:
            raise KillTeamRuleError("no operative is currently active")
        state["active_operative_id"] = None
        state["phase"] = "firefight"
        state["revision"] += 1
        event = {"active_operative_id": active_id}
        self._record("activation.ended", event)
        return self._recorded_result(action_id, {
            "status": "ended",
            "active_operative_id": active_id,
            "revision": state["revision"],
        })

    def advance_turning_point(self, *, cp_gain: int = 1, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        if state.get("pending_validation") is not None:
            raise KillTeamRuleError("cannot advance the turning point while setup validation is pending")
        state["turning_point"] = int(state.get("turning_point", 1)) + 1
        state["active_operative_id"] = None
        state["phase"] = "command"
        cp_result: dict[str, Any] | None = None
        if int(cp_gain) != 0:
            cp_result = self._apply_counter_delta("cp", int(cp_gain))
        state["revision"] += 1
        event = {
            "turning_point": state["turning_point"],
            "cp_gain": int(cp_gain),
            "cp_result": copy.deepcopy(cp_result) if cp_result is not None else None,
        }
        self._record("turning_point.advanced", event)
        result = {
            "status": "advanced",
            "turning_point": state["turning_point"],
            "phase": state["phase"],
            "cp_gain": int(cp_gain),
            "revision": state["revision"],
        }
        if cp_result is not None:
            result["cp"] = cp_result
        return self._recorded_result(action_id, result)

    def gain_cp(self, amount: int = 1, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        if int(amount) <= 0:
            raise KillTeamRuleError("gain_cp requires a positive amount")
        state = self._require_state()
        cp_result = self._apply_counter_delta("cp", int(amount))
        state["revision"] += 1
        self._record("resource.cp_gained", {
            "amount": int(amount),
            "counter": copy.deepcopy(cp_result),
        })
        return self._recorded_result(action_id, {
            "status": "updated",
            "resource": "cp",
            "amount": int(amount),
            "counter": cp_result,
            "revision": state["revision"],
        })

    def spend_cp(self, amount: int = 1, *, action_id: str | None = None) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        if int(amount) <= 0:
            raise KillTeamRuleError("spend_cp requires a positive amount")
        state = self._require_state()
        _, obj = self._counter_object("cp")
        current = int(obj.get("counter_value", 0))
        if current < int(amount):
            raise KillTeamRuleError("insufficient CP")
        cp_result = self._apply_counter_delta("cp", -int(amount))
        state["revision"] += 1
        self._record("resource.cp_spent", {
            "amount": int(amount),
            "counter": copy.deepcopy(cp_result),
        })
        return self._recorded_result(action_id, {
            "status": "updated",
            "resource": "cp",
            "amount": int(amount),
            "counter": cp_result,
            "revision": state["revision"],
        })

    def place_marker(
        self,
        marker_type: str,
        position: dict[str, float],
        *,
        name: str = "",
        object_type: str = "BlockSquare",
        locked: bool = True,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        state = self._require_state()
        marker = self._spawn_marker(
            marker_type,
            position,
            name=name,
            object_type=object_type,
            locked=locked,
        )
        markers = state.setdefault("markers", [])
        if not isinstance(markers, list):
            raise KillTeamRuleError("marker ledger is corrupted")
        markers.append(copy.deepcopy(marker))
        state["revision"] += 1
        self._record("marker.placed", copy.deepcopy(marker))
        return self._recorded_result(action_id, {
            "status": "placed",
            "marker": marker,
            "revision": state["revision"],
        })

    def score_objective(
        self,
        objective_id: str,
        *,
        points: int = 1,
        counter: str = "vp",
        marker_type: str = "objective",
        marker_name: str = "",
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        if int(points) <= 0:
            raise KillTeamRuleError("score_objective requires a positive point value")
        state = self._require_state()
        objective = self._objective_object(objective_id)
        position = _position(objective)
        marker = self._spawn_marker(
            marker_type,
            position,
            name=marker_name or str(objective.get("name") or marker_type),
            object_type="BlockSquare",
            locked=True,
        )
        score_counter = self._score_counter_name(counter)
        score_result = self._apply_counter_delta(score_counter, int(points))
        markers = state.setdefault("markers", [])
        if not isinstance(markers, list):
            raise KillTeamRuleError("marker ledger is corrupted")
        markers.append(copy.deepcopy(marker))
        state["revision"] += 1
        event = {
            "objective_id": str(objective.get("guid") or objective_id),
            "objective_name": str(objective.get("name") or ""),
            "marker": copy.deepcopy(marker),
            "counter": score_counter,
            "points": int(points),
            "score": copy.deepcopy(score_result),
        }
        self._record("objective.scored", event)
        return self._recorded_result(action_id, {
            "status": "scored",
            "objective": {
                "guid": str(objective.get("guid") or ""),
                "name": str(objective.get("name") or ""),
                "position": position,
            },
            "counter": score_counter,
            "points": int(points),
            "score": score_result,
            "marker": marker,
            "revision": state["revision"],
        })
