"""Deep Kill Team game-rule module for the first ranged-activation slice.

The module owns the rules-level interface.  A bridge adapter supplies tagged
TTS observations and bounded physical operations; tests can supply a fake
adapter with the same small interface.
"""

from __future__ import annotations

import copy
import json
import math
import re
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

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]: ...

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

    def set_object_name(self, guid: str, name: str) -> dict[str, Any]: ...

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

    def list_objects(self, **kwargs: Any) -> dict[str, Any]:
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
        return self._request(
            "killteam_list_objects",
            {
                "max_results": kwargs.get("max_results", 1000),
                "query_tags_json": json.dumps(query_tags, separators=(",", ":")),
                "required_guids_json": json.dumps(required_guids, separators=(",", ":")),
                "snap_point_tags_json": json.dumps(snap_point_tags, separators=(",", ":")),
            },
        )

    def get_object(self, guid: str) -> dict[str, Any]:
        return self._request("get_object", {"guid": guid})

    def get_snap_points(self, guid: str) -> dict[str, Any]:
        return self._request("get_snap_points", {"guid": guid})

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]:
        return self._request(
            "move_object",
            {"guid": guid, "position": position, "smooth": False, "collide": False, "fast": True},
        )

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


def _live_object_guid(value: Any) -> str | None:
    """Return a usable TTS GUID, never TTS's stale-reference sentinel."""
    guid = str(value or "").strip()
    if not guid or guid == "-1":
        return None
    return guid


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


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise KillTeamSetupError(f"{field} must be numeric") from exc


def _position(obj: dict[str, Any]) -> dict[str, float]:
    raw = obj.get("position") or {}
    return {axis: _number(raw.get(axis, 0), f"position.{axis}") for axis in ("x", "y", "z")}


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
            target_guid = _live_object_guid(self.config.target_guid)
            if target_guid is not None:
                required_guids.append(target_guid)
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

    def _normalize_fixture_objects(
        self,
        objects: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Project Save 131's native tags and stable anchors into canonical roles."""
        profile = self._fixture_profile
        if profile is None:
            return objects

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

    def setup(self) -> dict[str, Any]:
        objects = self._normalize_fixture_objects(self._list_objects())
        self._objects = {str(obj["guid"]): obj for obj in objects}
        metadata = {guid: _metadata(obj) for guid, obj in self._objects.items()}

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
            }

        ai_ids = sorted(record["operative_id"] for record in operatives.values() if record["team"] == self.config.ai_team)
        if not ai_ids:
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
            if meta.get("entity") == "terrain":
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

        self._state = {
            "schema_version": 1,
            "status": "ready",
            "revision": 0,
            "observation_id": 0,
            "map_revision": 0,
            "phase": "setup",
            "active_operative_id": None,
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
        }
        self._record("setup.completed", {"ai_operatives": ai_ids, "visible_opponents": visible_opponents})
        result = {
            "status": "ready",
            "schema_version": 1,
            "ai_operatives": ai_ids,
            "ai_models": [copy.deepcopy(operatives[operative_id]) for operative_id in ai_ids],
            "visible_opponents": sorted(visible_opponents),
            "map_revision": 0,
            "roller_guid": rollers[0],
        }
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
        return {
            "schema_version": state["schema_version"],
            "revision": state["revision"],
            "observation_id": state["observation_id"],
            "map_revision": state["map_revision"],
            "phase": state["phase"],
            "active_operative_id": state["active_operative_id"],
            "operatives": visible,
            "terrain": terrain[:200],
            "dice": {"ai": list(state["dice_by_team"].get(self.config.ai_team, []))},
            "counters": counters,
            "roller_guid": state["roller_guid"],
            "defense_station_guid": state.get("defense_station_guid"),
            "start_test_spot": copy.deepcopy(state.get("start_test_spot")),
            "truncated": self._listing_truncated or terrain_truncated,
        }

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

    def place_operative(
        self,
        operative_id: str,
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
        operative = self._operative(operative_id, visible=False)
        if operative["team"] != self.config.ai_team:
            raise KillTeamRuleError("only the AI can place its own operative")
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
        state["revision"] += 1
        self._record("operative.placed", {"operative_id": operative_id, "position": actual_position})
        return self._recorded_result(action_id, {"status": "verified", "operative_id": operative_id, "position": actual_position, "revision": state["revision"]})

    def deploy_test_model(self, *, action_id: str | None = None) -> dict[str, Any]:
        """Move the named test model to the tagged deployment zone without setup."""
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        model_name = "Plague Marine Warrior"
        target_tag = "_deployment_zone_blue"
        try:
            snapshot = self.bridge.list_objects(
                max_results=2,
                compact=True,
                query_names=[model_name],
                query_tags=[target_tag],
            )
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
        model_position = _position(model)
        marker_position = _position(target_marker)
        target = {
            "x": marker_position["x"],
            "y": model_position["y"],
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
        if distance_to_target > 0.25:
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

        placement_action_id = f"{action_id}:placement" if action_id else None
        placement = self.place_operative(
            attacker_id,
            [copy.deepcopy(snap_position)],
            action_id=placement_action_id,
        )
        self.activate_operative(attacker_id)
        attacker = self._operative(attacker_id, visible=False)
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
