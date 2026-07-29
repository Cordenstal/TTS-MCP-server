from __future__ import annotations

from typing import Any


ACTION_PLAN_ALLOWED = {
    "move_object",
    "rotate_object",
    "set_object_name",
    "set_object_lock",
    "spawn_builtin",
    "broadcast",
    "destroy_object",
}


def validate_action_plan(
    actions: list[dict[str, Any]],
    allow_irreversible: bool = False,
) -> list[dict[str, Any]]:
    """Validate a bounded, structured mutation plan before it reaches TTS."""
    if not isinstance(actions, list) or not actions:
        raise ValueError("actions must be a non-empty list")
    if len(actions) > 50:
        raise ValueError("actions may contain at most 50 steps")

    validated: list[dict[str, Any]] = []
    for index, item in enumerate(actions):
        if not isinstance(item, dict):
            raise ValueError(f"actions[{index}] must be an object")
        action = item.get("action")
        args = item.get("args", {})
        if not isinstance(action, str) or action not in ACTION_PLAN_ALLOWED:
            raise ValueError(
                f"actions[{index}].action must be one of "
                f"{', '.join(sorted(ACTION_PLAN_ALLOWED))}"
            )
        if not isinstance(args, dict):
            raise ValueError(f"actions[{index}].args must be an object")
        if action == "destroy_object" and not allow_irreversible:
            raise ValueError(
                "destroy_object requires allow_irreversible=true and explicit user confirmation"
            )
        preconditions = item.get("preconditions", {})
        postconditions = item.get("postconditions", {})
        if not isinstance(preconditions, dict) or not isinstance(postconditions, dict):
            raise ValueError(f"actions[{index}] preconditions/postconditions must be objects")
        validated.append({
            "action": action,
            "args": dict(args),
            "preconditions": dict(preconditions),
            "postconditions": dict(postconditions),
        })
    return validated


def expectation_failures(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return human-readable mismatches for a small, JSON-safe object contract."""
    failures: list[str] = []
    for field in ("guid", "name", "type", "locked", "resting", "smooth_moving"):
        if field in expected and actual.get(field) != expected[field]:
            failures.append(f"{field}: expected {expected[field]!r}, got {actual.get(field)!r}")

    if "tags_contains" in expected:
        wanted = {str(tag).lower() for tag in expected["tags_contains"]}
        actual_tags = {str(tag).lower() for tag in actual.get("tags") or []}
        missing = sorted(wanted - actual_tags)
        if missing:
            failures.append(f"tags missing: {', '.join(missing)}")

    if "position" in expected:
        target = expected["position"]
        actual_position = actual.get("position") or {}
        tolerance = float(expected.get("max_position_error", 0.05))
        for axis in ("x", "y", "z"):
            if axis not in target or axis not in actual_position:
                failures.append(f"position missing axis {axis}")
            elif abs(float(actual_position[axis]) - float(target[axis])) > tolerance:
                failures.append(
                    f"position.{axis}: expected {target[axis]!r} ± {tolerance}, "
                    f"got {actual_position[axis]!r}"
                )
    return failures
