from __future__ import annotations

import copy
from dataclasses import dataclass
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

    def place_model(self, guid: str, position: dict[str, float]) -> dict[str, Any]:
        return self._request(
            "setup_place_model",
            {
                "guid": str(guid),
                "position": {
                    "x": float(position["x"]),
                    "y": float(position["y"]),
                    "z": float(position["z"]),
                },
            },
        )


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
        target = {
            axis: _number(position.get(axis, 0), f"position.{axis}")
            for axis in ("x", "y", "z")
        }
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
        if any(
            abs(actual[axis] - target[axis]) > self.config.placement_tolerance
            for axis in ("x", "y", "z")
        ):
            self._mark_uncertain(action_id)
            raise KillTeamSetupUncertainCommit("setup placement did not verify")
        self._revision += 1
        result = {
            "status": "verified",
            "guid": actual_guid,
            "name": _clean_name(raw.get("name")),
            "position": actual,
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
