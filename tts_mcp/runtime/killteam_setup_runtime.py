from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol


class KillTeamSetupError(RuntimeError):
    """Base error for placement-only Kill Team setup."""


class KillTeamSetupRuleError(KillTeamSetupError):
    """A requested placement is not legal or not uniquely resolvable."""


class KillTeamSetupUncertainCommit(KillTeamSetupError):
    """A bridge mutation may have committed and must not be retried."""


class KillTeamSetupBridge(Protocol):
    def ping(self) -> dict[str, Any]: ...

    def list_objects(self, **kwargs: Any) -> dict[str, Any]: ...

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]: ...

    def place_model(self, guid: str, position: dict[str, float]) -> dict[str, Any]: ...


class TTSKillTeamSetupBridge:
    """Small adapter over the dedicated placement-only Lua bridge."""

    def __init__(self, request: Any) -> None:
        self._request = request

    def ping(self) -> dict[str, Any]:
        return self._request("setup_ping", {})

    def list_objects(self, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "max_results": int(kwargs.get("max_results", 1000)),
            "compact": bool(kwargs.get("compact", True)),
        }
        if "name_contains" in kwargs:
            payload["name_contains"] = str(kwargs.get("name_contains", ""))
        if "tag" in kwargs:
            payload["tag"] = str(kwargs.get("tag", ""))
        return self._request("setup_list_objects", payload)

    @staticmethod
    def _placement_payload(guid: str, position: dict[str, float]) -> dict[str, Any]:
        x = float(position["x"])
        y = float(position["y"])
        z = float(position["z"])
        return {
            "guid": str(guid),
            "x": x,
            "y": y,
            "z": z,
            "position": {
                "x": x,
                "y": y,
                "z": z,
            },
        }

    def move_object(self, guid: str, position: dict[str, float]) -> dict[str, Any]:
        return self._request("move_object", self._placement_payload(guid, position))

    def place_model(self, guid: str, position: dict[str, float]) -> dict[str, Any]:
        return self._request("setup_place_model", self._placement_payload(guid, position))


_SCRIPT_BODY_KEYS = ("script", "LuaScript", "luaScript", "source", "text", "content")
_SETUP_BRIDGE_VERIFICATION_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_SETUP_BRIDGE_VERIFICATION_CACHE_LOCK = Lock()


def _normalize_lua_source(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _hash_lua_source(source: str) -> str:
    normalized = _normalize_lua_source(source)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _script_state_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        states = raw.get("script_states")
        if not isinstance(states, list):
            states = raw.get("scriptStates")
    elif isinstance(raw, list):
        states = raw
    else:
        states = []
    return [state for state in states if isinstance(state, dict)]


def _script_identity(state: dict[str, Any]) -> str:
    for key in ("name", "scriptName", "label", "type"):
        value = state.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "Global"


def _script_body(state: dict[str, Any]) -> str | None:
    for key in _SCRIPT_BODY_KEYS:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def verify_killteam_setup_bridge_source(
    *,
    bridge_get_scripts: Any,
    bridge_version: str,
    disk_path: Path,
) -> dict[str, Any]:
    bridge_version_text = str(bridge_version or "").strip() or "unknown"
    disk_source = disk_path.read_text(encoding="utf-8")
    disk_hash = _hash_lua_source(disk_source)
    cache_key = (bridge_version_text, disk_hash)

    with _SETUP_BRIDGE_VERIFICATION_CACHE_LOCK:
        cached = _SETUP_BRIDGE_VERIFICATION_CACHE.get(cache_key)
    if cached is not None:
        result = copy.deepcopy(cached)
        result["verification_source"] = "cache"
        return result

    try:
        raw_states = bridge_get_scripts()
    except Exception as exc:
        return {
            "bridge_version": bridge_version_text,
            "disk_hash": disk_hash,
            "loaded_hash": "",
            "loaded_script_identity": "Global",
            "reload_verified": False,
            "script_state_count": 0,
            "verification_error": f"Could not read the live Global script state: {exc}",
            "verification_source": "fresh",
        }

    script_states = _script_state_list(raw_states)
    result: dict[str, Any] = {
        "bridge_version": bridge_version_text,
        "disk_hash": disk_hash,
        "loaded_hash": "",
        "loaded_script_identity": "Global",
        "reload_verified": False,
        "script_state_count": len(script_states),
        "verification_error": "",
        "verification_source": "fresh",
    }

    if not script_states:
        result["verification_error"] = "TTS returned no script states"
        return result

    global_state = next(
        (state for state in script_states if str(state.get("name") or "").strip().lower() == "global"),
        None,
    )
    if global_state is None:
        result["verification_error"] = "Global script state was not found in TTS scriptStates"
        return result

    result["loaded_script_identity"] = _script_identity(global_state)
    loaded_source = _script_body(global_state)
    if loaded_source is None:
        result["verification_error"] = (
            f"{result['loaded_script_identity']} script state does not expose a readable script body"
        )
        return result

    loaded_hash = _hash_lua_source(loaded_source)
    result["loaded_hash"] = loaded_hash
    if loaded_hash != disk_hash:
        result["verification_error"] = (
            f"{result['loaded_script_identity']} script body does not match the on-disk setup bridge"
        )
        return result

    result["reload_verified"] = True
    with _SETUP_BRIDGE_VERIFICATION_CACHE_LOCK:
        _SETUP_BRIDGE_VERIFICATION_CACHE[cache_key] = copy.deepcopy(result)
    return result


@dataclass(frozen=True)
class KillTeamSetupConfig:
    placement_tolerance: float = 0.05


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise KillTeamSetupRuleError(f"{field} must be numeric") from exc


def _position(obj: dict[str, Any]) -> dict[str, float]:
    raw = obj.get("position") or {}
    return {
        axis: _number(raw.get(axis, 0), f"position.{axis}")
        for axis in ("x", "y", "z")
    }


def _live_guid(value: Any) -> str | None:
    guid = str(value or "").strip()
    if not guid or guid == "-1":
        return None
    return guid


def _has_tag(obj: dict[str, Any], requested: str) -> bool:
    wanted = _norm(requested)
    if not wanted:
        return True
    tags = obj.get("tags") or []
    return any(_norm(tag) == wanted for tag in tags)


def _normalized_tags(obj: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for raw in obj.get("tags") or []:
        text = _norm(raw)
        if not text:
            continue
        tags.add(text)
        if text.startswith("tts_mcp:"):
            tags.add(text.removeprefix("tts_mcp:"))
    return tags


def _rect_tuple(value: dict[str, float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(value, tuple):
        return value
    return (
        float(value["min_x"]),
        float(value["max_x"]),
        float(value["min_z"]),
        float(value["max_z"]),
    )


def _rects_overlap(
    first: dict[str, float] | tuple[float, float, float, float],
    second: dict[str, float] | tuple[float, float, float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    a = _rect_tuple(first)
    b = _rect_tuple(second)
    return not (
        a[1] < b[0] - tolerance
        or a[0] > b[1] + tolerance
        or a[3] < b[2] - tolerance
        or a[2] > b[3] + tolerance
    )


def _bounds_box(obj: dict[str, Any]) -> dict[str, Any] | None:
    raw = obj.get("bounds") or {}
    center = raw.get("center") or obj.get("position") or {}
    position = obj.get("position") or center
    size = raw.get("size") or {}
    try:
        cx = float(center["x"])
        cy = float(center["y"])
        cz = float(center["z"])
        px = float(position["x"])
        py = float(position["y"])
        pz = float(position["z"])
        sx = abs(float(size.get("x", 0)))
        sy = abs(float(size.get("y", 0)))
        sz = abs(float(size.get("z", 0)))
    except (KeyError, TypeError, ValueError):
        return None
    if min(sx, sy, sz) <= 0:
        return None
    return {
        "rect": (cx - sx / 2, cx + sx / 2, cz - sz / 2, cz + sz / 2),
        "min_y": cy - sy / 2,
        "max_y": cy + sy / 2,
        "center": {"x": cx, "y": cy, "z": cz},
        "size": {"x": sx, "y": sy, "z": sz},
        "position": {"x": px, "y": py, "z": pz},
        "pivot_to_bottom_y": py - cy + sy / 2,
    }


def _is_terrain_surface(obj: dict[str, Any]) -> bool:
    tags = _normalized_tags(obj)
    if {
        "operative",
        "kt_mission_objective",
        "_deployment_zone_blue",
        "_deployment_zone_red",
        "entity=objective",
        "entity=deployment",
    } & tags:
        return False
    return "entity=terrain" in tags or "kt_mission_terrain" in tags or "blocks_los=true" in tags


def _is_setup_objective(obj: dict[str, Any]) -> bool:
    tags = _normalized_tags(obj)
    return bool({"objective", "kt_mission_objective", "entity=objective"} & tags)


def _is_setup_blocker(obj: dict[str, Any]) -> bool:
    return _has_tag(obj, "Operative") or _is_setup_objective(obj)


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").split())


class KillTeamSetupRuntime:
    """Placement-only setup helper for a dedicated Kill Team Lua bridge."""

    def __init__(
        self,
        bridge: KillTeamSetupBridge,
        config: KillTeamSetupConfig | None = None,
    ) -> None:
        self.bridge = bridge
        self.config = config or KillTeamSetupConfig()
        self._action_results: dict[str, dict[str, Any]] = {}
        self._uncertain_action_ids: set[str] = set()
        self._revision = 0

    def _replay_or_reject(self, action_id: str | None) -> dict[str, Any] | None:
        if not action_id:
            return None
        if action_id in self._uncertain_action_ids:
            raise KillTeamSetupUncertainCommit(
                f"action {action_id} has uncertain commit status and requires read-only recovery"
            )
        result = self._action_results.get(action_id)
        return copy.deepcopy(result) if result is not None else None

    def _recorded_result(self, action_id: str | None, result: dict[str, Any]) -> dict[str, Any]:
        if action_id:
            self._action_results[action_id] = copy.deepcopy(result)
        return result

    def _mark_uncertain(self, action_id: str | None) -> None:
        if action_id:
            self._uncertain_action_ids.add(action_id)

    def ping(self) -> dict[str, Any]:
        raw = self.bridge.ping()
        if not isinstance(raw, dict):
            raise KillTeamSetupError("the placement bridge returned an invalid ping result")
        result = copy.deepcopy(raw)
        result.setdefault("status", "ready")
        return result

    def list_objects(
        self,
        *,
        name_contains: str = "",
        tag: str = "",
        max_results: int = 1000,
        compact: bool = True,
    ) -> dict[str, Any]:
        try:
            raw = self.bridge.list_objects(
                name_contains=name_contains,
                tag=tag,
                max_results=max_results,
                compact=compact,
            )
        except Exception as exc:
            raise KillTeamSetupError("placement scene enumeration failed") from exc
        if not isinstance(raw, dict):
            raise KillTeamSetupError("placement scene enumeration returned an invalid result")
        objects = raw.get("objects", [])
        if not isinstance(objects, list):
            raise KillTeamSetupError("placement scene enumeration returned invalid objects")
        bounded = copy.deepcopy(raw)
        bounded["objects"] = [item for item in objects if isinstance(item, dict)][: max(1, min(int(max_results), 1000))]
        bounded["count"] = len(bounded["objects"])
        bounded["truncated"] = bool(raw.get("truncated")) or len(objects) > len(bounded["objects"])
        return bounded

    def _unique_object(
        self,
        objects: list[dict[str, Any]],
        *,
        name_contains: str = "",
        tag: str = "",
        label: str,
    ) -> dict[str, Any]:
        wanted_name = _norm(name_contains)
        wanted_tag = _norm(tag)
        matches = [
            obj
            for obj in objects
            if (
                (not wanted_name or wanted_name in _norm(obj.get("name")))
                and _has_tag(obj, wanted_tag)
            )
        ]
        if len(matches) != 1:
            raise KillTeamSetupRuleError(
                f"{label} must resolve to exactly one live object; found {len(matches)}"
            )
        return matches[0]

    def place_model(
        self,
        guid: str,
        position: dict[str, float],
        *,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        live_guid = _live_guid(guid)
        if live_guid is None:
            raise KillTeamSetupRuleError("a live model GUID is required")
        try:
            raw_objects = self.bridge.list_objects(max_results=1000, compact=False)
        except Exception as exc:
            raise KillTeamSetupError("placement scene enumeration failed") from exc
        objects = raw_objects.get("objects", []) if isinstance(raw_objects, dict) else []
        if not isinstance(objects, list):
            raise KillTeamSetupError("placement scene enumeration returned invalid objects")
        live_model = next(
            (
                obj
                for obj in objects
                if isinstance(obj, dict) and _norm(obj.get("guid")) == _norm(live_guid)
            ),
            None,
        )
        if live_model is None:
            raise KillTeamSetupRuleError("a live model GUID is required")
        model_box = _bounds_box(live_model)
        if model_box is None:
            raise KillTeamSetupRuleError("the live model is missing bounds")
        target = {
            axis: _number(position.get(axis, 0), f"position.{axis}")
            for axis in ("x", "y", "z")
        }
        requested_target = dict(target)
        support_height: float | None = None
        support_guids: list[str] = []
        if model_box is not None:
            rect = (
                target["x"] - model_box["size"]["x"] / 2,
                target["x"] + model_box["size"]["x"] / 2,
                target["z"] - model_box["size"]["z"] / 2,
                target["z"] + model_box["size"]["z"] / 2,
            )
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                if _norm(obj.get("guid")) == _norm(live_guid):
                    continue
                box = _bounds_box(obj)
                if box is None or not _rects_overlap(rect, box["rect"]):
                    continue
                if _is_terrain_surface(obj):
                    top_y = float(box["max_y"])
                    if support_height is None or top_y > support_height:
                        support_height = top_y
                        support_guids = [str(obj.get("guid", ""))]
                    elif support_height is not None and abs(top_y - support_height) <= 1e-6:
                        support_guids.append(str(obj.get("guid", "")))
        if support_height is not None:
            target = dict(target)
            target["y"] = round(support_height + model_box["pivot_to_bottom_y"], 6)
        model_bottom_offset = float(model_box["pivot_to_bottom_y"])
        candidate_span = (
            float(target["y"]) - model_bottom_offset,
            float(target["y"]) - model_bottom_offset + model_box["size"]["y"],
        )
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            if _norm(obj.get("guid")) == _norm(live_guid) or _is_terrain_surface(obj):
                continue
            if not _is_setup_blocker(obj):
                continue
            box = _bounds_box(obj)
            if box is None or not _rects_overlap(
                (
                    target["x"] - model_box["size"]["x"] / 2,
                    target["x"] + model_box["size"]["x"] / 2,
                    target["z"] - model_box["size"]["z"] / 2,
                    target["z"] + model_box["size"]["z"] / 2,
                ),
                box["rect"],
            ):
                continue
            blocker_span = (float(box["min_y"]), float(box["max_y"]))
            if blocker_span[1] < candidate_span[0] - 1e-6 or blocker_span[0] > candidate_span[1] + 1e-6:
                continue
            if _is_setup_objective(obj):
                raise KillTeamSetupRuleError(
                    f"setup placement intersects objective {obj.get('guid', '')}"
                )
            raise KillTeamSetupRuleError("setup placement intersects another model")
        try:
            raw = self.bridge.place_model(live_guid, target)
        except Exception as exc:
            self._mark_uncertain(action_id)
            raise KillTeamSetupUncertainCommit("setup placement commit is uncertain") from exc
        if not isinstance(raw, dict):
            self._mark_uncertain(action_id)
            raise KillTeamSetupUncertainCommit("setup placement returned an invalid object")
        actual_guid = _live_guid(raw.get("guid"))
        if actual_guid is None or _norm(actual_guid) != _norm(live_guid):
            self._mark_uncertain(action_id)
            raise KillTeamSetupUncertainCommit("setup placement readback did not verify the GUID")
        actual = _position(raw)
        bridge_support_height = _optional_number(raw.get("support_height"))
        bridge_support_guids = [
            str(guid)
            for guid in (raw.get("support_guids") or [])
            if str(guid).strip()
        ]
        if bridge_support_height is not None:
            if support_height is not None and abs(bridge_support_height - support_height) > self.config.placement_tolerance:
                self._mark_uncertain(action_id)
                raise KillTeamSetupUncertainCommit("placement support height disagreed with the live bridge")
            support_height = bridge_support_height
            support_guids = bridge_support_guids
            target = dict(target)
            target["y"] = round(support_height + model_box["pivot_to_bottom_y"], 6)
        actual_box = _bounds_box(raw)
        if actual_box is not None and support_height is not None:
            verified = (
                abs(actual["x"] - target["x"]) <= self.config.placement_tolerance
                and abs(actual["z"] - target["z"]) <= self.config.placement_tolerance
                and abs(actual_box["min_y"] - support_height) <= self.config.placement_tolerance
            )
        else:
            verified = all(
                abs(actual[axis] - target[axis]) <= self.config.placement_tolerance
                for axis in ("x", "y", "z")
            )
        if not verified:
            self._mark_uncertain(action_id)
            raise KillTeamSetupUncertainCommit("setup placement did not verify")
        self._revision += 1
        result = {
            "status": "verified",
            "guid": actual_guid,
            "name": _clean_name(raw.get("name")),
            "position": actual,
            "bounds": copy.deepcopy(raw.get("bounds")),
            "requested_position": requested_target,
            "support_height": support_height,
            "support_guids": [guid for guid in support_guids if guid],
            "tags": copy.deepcopy(raw.get("tags", [])),
            "revision": self._revision,
        }
        return self._recorded_result(action_id, result)

    def deploy_named_model(
        self,
        *,
        model_name_contains: str,
        target_tag: str,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        replay = self._replay_or_reject(action_id)
        if replay is not None:
            return replay
        snapshot = self.list_objects(max_results=1000, compact=True)
        objects = snapshot.get("objects", [])
        if not isinstance(objects, list):
            raise KillTeamSetupError("placement scene enumeration returned an invalid object list")
        model = self._unique_object(
            [item for item in objects if isinstance(item, dict)],
            name_contains=model_name_contains,
            label="model",
        )
        target = self._unique_object(
            [item for item in objects if isinstance(item, dict)],
            tag=target_tag,
            label="target",
        )
        model_position = _position(model)
        target_position = _position(target)
        placement = self.place_model(
            str(model.get("guid") or ""),
            {
                "x": target_position["x"],
                "y": model_position["y"],
                "z": target_position["z"],
            },
            action_id=action_id,
        )
        result = {
            "status": "verified",
            "model_name": _clean_name(model.get("name")),
            "model_guid": str(model.get("guid") or ""),
            "target_tag": target_tag,
            "target_guid": str(target.get("guid") or ""),
            "target_position": {
                "x": target_position["x"],
                "y": model_position["y"],
                "z": target_position["z"],
            },
            "placement": placement,
            "revision": placement["revision"],
        }
        return self._recorded_result(action_id, result)

    def deploy_test_model(self, *, action_id: str | None = None) -> dict[str, Any]:
        return self.deploy_named_model(
            model_name_contains="Plague Marine Warrior",
            target_tag="_deployment_zone_blue",
            action_id=action_id,
        )
