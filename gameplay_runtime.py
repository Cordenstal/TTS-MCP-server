from __future__ import annotations

"""Bounded D&D gameplay intelligence for the TTS AI gateway.

This module deliberately knows nothing about MCP or Lua.  It consumes a
best-effort structured context snapshot and an allowlisted bridge callback.
"""

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class Intent(str, Enum):
    SPAWN_REQUEST = "spawn_request"
    SCENE_SETUP = "scene_setup"
    ENTITY_ACTION = "entity_action"
    QUERY = "query"
    NARRATIVE = "narrative"
    OOC_COMMAND = "ooc_command"


def classify_intent(message: str) -> Intent:
    text = message.lower().strip()
    if text.startswith("!"):
        return Intent.OOC_COMMAND
    if re.search(r"\b(set up|setup|create|build|populate|decorate|scene|tavern|dungeon|village)\b", text):
        return Intent.SCENE_SETUP
    if re.search(r"\b(spawn|place|put|add|summon|bring out)\b", text):
        return Intent.SPAWN_REQUEST
    if re.search(r"\b(where|what|which|how many|distance|near|inspect|look|see)\b", text):
        return Intent.QUERY
    if re.search(r"\b(move|attack|hit|cast|open|take|roll|damage|fight|lock|unlock)\b", text):
        return Intent.ENTITY_ACTION
    return Intent.NARRATIVE


@dataclass(frozen=True)
class ParsedCommand:
    action: str
    args: dict[str, Any]
    destructive: bool = False


_GUID = r"[0-9a-fA-F]{6}"
_NUMBER = r"-?\d+(?:\.\d+)?"


def parse_ai_commands(text: str, *, max_commands: int = 50) -> list[ParsedCommand]:
    """Parse only the explicit, documented command forms emitted by the AI."""
    commands: list[ParsedCommand] = []

    def add(action: str, args: dict[str, Any], destructive: bool = False) -> None:
        if len(commands) < max_commands:
            commands.append(ParsedCommand(action, args, destructive))

    # V6-compatible catalog commands.
    for m in re.finditer(rf"(SPAWN|PLACE)\[({_GUID}),\s*({_NUMBER}),\s*({_NUMBER})\]", text, re.I):
        add("spawn_catalog" if m.group(1).lower() == "spawn" else "place_catalog", {
            "guid": m.group(2), "x": float(m.group(3)), "y": 2.0, "z": float(m.group(4)),
        })

    for m in re.finditer(rf"MOVE\[({_GUID}),\s*({_NUMBER}),\s*({_NUMBER}),\s*({_NUMBER})\]", text, re.I):
        add("move_object", {"guid": m.group(1), "x": float(m.group(2)), "y": float(m.group(3)), "z": float(m.group(4))})
    for m in re.finditer(rf"ROTATE\[({_GUID}),\s*({_NUMBER}),\s*({_NUMBER}),\s*({_NUMBER})\]", text, re.I):
        add("rotate_object", {"guid": m.group(1), "x": float(m.group(2)), "y": float(m.group(3)), "z": float(m.group(4))})
    for m in re.finditer(rf"(LOCK|UNLOCK)\[({_GUID})\]", text, re.I):
        add("set_object_lock", {"guid": m.group(2), "locked": m.group(1).lower() == "lock"})
    for m in re.finditer(rf"SPAWN_BUILTIN\[([^,\]]+),\s*({_NUMBER}),\s*({_NUMBER}),\s*({_NUMBER})\]", text, re.I):
        add("spawn_builtin", {"object_type": m.group(1).strip(), "x": float(m.group(2)), "y": float(m.group(3)), "z": float(m.group(4))})
    for m in re.finditer(r"BROADCAST\[([^\]]{1,500})\]", text, re.I):
        add("broadcast", {"message": m.group(1).strip()})
    for m in re.finditer(rf"DESTROY\[({_GUID})\]", text, re.I):
        add("destroy_object", {"guid": m.group(1)}, True)

    # Optional JSON form lets a local model emit a structured action plan
    # without granting it arbitrary Python/Lua execution.
    for block in re.findall(r"```(?:json|actions)?\s*([\s\S]*?)```", text, re.I):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        entries = value if isinstance(value, list) else value.get("actions", []) if isinstance(value, dict) else []
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("action"), str) or not isinstance(item.get("args", {}), dict):
                continue
            if item["action"] in {"move_object", "rotate_object", "set_object_lock", "spawn_builtin", "spawn_catalog", "place_catalog", "broadcast", "destroy_object"}:
                add(item["action"], dict(item.get("args", {})), item["action"] == "destroy_object")
    return commands


class CatalogIndex:
    """Small searchable catalog with live-object fallback."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else None
        self.objects: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path or not self.path.is_file():
            self.objects = []
            self.metadata = {}
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.objects = []
            self.metadata = {}
            return
        self.metadata = value.get("metadata", {}) if isinstance(value, dict) and isinstance(value.get("metadata", {}), dict) else {}
        self.objects = value if isinstance(value, list) else value.get("objects", []) if isinstance(value, dict) else []

    def search(self, query: str, *, limit: int = 12, objects: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        source = objects if objects else self.objects
        words = set(re.findall(r"[a-z0-9]+", query.lower()))
        wants_container = bool(words & {"bag", "bags", "container", "containers", "deck", "master"})
        ranked: list[tuple[int, dict[str, Any]]] = []
        for obj in source:
            object_type = str(obj.get("type", "")).lower()
            object_name = str(obj.get("name", "")).lower()
            if not wants_container and (
                "bag" in object_type or "container" in object_type
                or "master bag" in object_name or "table bag" in object_name
            ):
                continue
            haystack = " ".join(str(obj.get(k, "")) for k in ("guid", "name", "type", "description", "tags", "category"))
            score = sum(1 for word in words if word in haystack.lower())
            if score:
                ranked.append((score, obj))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("guid", ""))))
        return [obj for _, obj in ranked[: max(1, min(limit, 50))]]

    def get(self, guid: str) -> dict[str, Any] | None:
        wanted = str(guid).strip().lower()
        obj = next((obj for obj in self.objects if str(obj.get("guid", "")).lower() == wanted), None)
        if obj is None:
            return None
        result = dict(obj)
        if self.metadata.get("masterBagGuid") and not result.get("masterBagGuid"):
            result["masterBagGuid"] = self.metadata["masterBagGuid"]
        return result


class DndPromptBuilder:
    def __init__(self, rules_root: Path, catalog: CatalogIndex | None = None) -> None:
        self.rules_root = rules_root.resolve()
        self.catalog = catalog or CatalogIndex()

    def rules(self, game: str) -> str:
        if not game:
            return ""
        path = (self.rules_root / game / "rules.md").resolve()
        if path.parent.parent != self.rules_root or not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")[:8000]
        except OSError:
            return ""

    def build(self, *, game: str, intent: Intent, context: dict[str, Any]) -> str:
        rules = self.rules(game)
        base = (
            "You are the bounded Tabletop Simulator game agent.\n"
            "For D&D, act as a concise 5e Dungeon Master: narrate consequences, enforce the selected rules, "
            "and use structured evidence before acting.\n"
            "Never invent GUIDs. Only emit allowlisted commands using exact six-character hexadecimal GUIDs.\n"
            "For location questions and movement, use the live top-level table inventory: every GUID, position, rotation, and bounds value comes from the current TTS scene. The position is the exact world x,y,z center. Use the screenshot only to compare visual identity and board alignment; do not replace structured coordinates with visual guesses.\n"
            "When AI play state is running and it is your verified turn, act independently: select a legal object from the live inventory and emit its MOVE command. A move is complete only if the response contains an executable MOVE[guid,x,y,z] line; prose or board notation such as f6-e5 is not a command. Do not ask a player to move it for you. Preserve the source object's y coordinate unless the table's verified mapping requires another height.\n"
            "Never select or spawn a bag, master bag, category bag, deck, or container as a scene object.\n"
            "Commands are explicit text: MOVE[guid,x,y,z], ROTATE[guid,x,y,z], LOCK[guid], UNLOCK[guid], "
            "SPAWN[guid,x,z], PLACE[guid,x,z], SPAWN_BUILTIN[type,x,y,z], BROADCAST[text], or DESTROY[guid].\n"
            "Destruction is never executed automatically; it must be proposed for host approval.\n"
            "Keep responses concise and include commands immediately when an action is requested.\n"
        )
        sections = [base, f"Intent for this turn: {intent.value}", "Authoritative current context:\n" + str(context.get("text", ""))]
        if rules:
            sections.append("Selected game rules:\n" + rules)
        return "\n\n".join(sections)


class ScenePlacementIntelligence:
    def __init__(self, catalog: CatalogIndex) -> None:
        self.catalog = catalog

    def enrich(self, context: dict[str, Any], message: str, intent: Intent) -> dict[str, Any]:
        result = dict(context)
        objects = result.get("objects") if isinstance(result.get("objects"), list) else []
        # Live scene queries must never be padded with the offline V6 catalog.
        # The catalog is only relevant when the user is asking to spawn or
        # configure a scene object; otherwise it makes the AI think catalog
        # entries are physically present on the table.
        catalog_intent = intent in {Intent.SCENE_SETUP, Intent.SPAWN_REQUEST, Intent.ENTITY_ACTION}
        candidates = self.catalog.search(message, objects=objects) if catalog_intent else objects[:100]
        if catalog_intent and len(candidates) < 12:
            seen = {str(item.get("guid", "")).lower() for item in candidates}
            for item in self.catalog.search(message, limit=24):
                if str(item.get("guid", "")).lower() not in seen:
                    candidates.append(item)
                    seen.add(str(item.get("guid", "")).lower())
                if len(candidates) >= 12:
                    break
        if candidates:
            result["text"] = str(result.get("text", "")) + "\nRelevant scene/catalog candidates:\n" + "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in candidates)
        if intent == Intent.SCENE_SETUP:
            result["text"] = str(result.get("text", "")) + "\nScene guidance: establish terrain/structure first, then furniture/props, then actors and effects; avoid overlaps and verify placement."
        return result


class CommandExecution:
    def __init__(self, request: Callable[[str, dict[str, Any]], dict[str, Any]], propose: Callable[[dict[str, Any]], str]) -> None:
        self.request = request
        self.propose = propose

    def execute(self, commands: list[ParsedCommand], *, running: bool, active_game: str = "") -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        for command in commands:
            if command.destructive:
                proposal = {"action": command.action, "args": command.args, "source": "ai_command"}
                proposals.append({"action_id": self.propose(proposal), **proposal})
                continue
            if not running:
                results.append({"action": command.action, "status": "blocked", "reason": "AI play is not running", "args": command.args})
                continue
            if active_game.strip().lower() == "checkers" and command.action == "move_object":
                # The active checkers save is host-mapped with the red side at
                # negative Z. AI-controlled men must advance toward red, never
                # sideways or away from it. Validate the source in TTS before
                # allowing the mutating bridge action.
                try:
                    source = self.request("get_object", {"guid": command.args["guid"]})
                    if str(source.get("type", "")).lower() != "checker":
                        results.append({"action": command.action, "status": "blocked", "reason": "only Checker objects may be moved during a checkers game", "args": command.args})
                        continue
                    source_z = float((source.get("position") or {})["z"])
                    target_z = float(command.args["z"])
                    stack = self.request("list_objects", {"max_results": 250, "compact": True})
                    is_king = self._is_double_stacked_checker(source, stack.get("objects") or [])
                    delta_z = target_z - source_z
                    # A normal step is one row; a potential capture spans two
                    # rows. Men may capture backward under English draughts,
                    # so only reject sideways/backward *ordinary* moves here.
                    # A double-stacked piece is a crowned king and may move in
                    # either direction.
                    if not is_king and delta_z >= -0.5 and abs(delta_z) < 3.0:
                        results.append({
                            "action": command.action,
                            "status": "blocked",
                            "reason": "checkers moves must advance toward the red side (negative world Z)",
                            "args": command.args,
                            "source_position": source.get("position"),
                        })
                        continue
                except Exception as exc:
                    results.append({"action": command.action, "status": "blocked", "reason": f"could not verify checkers move direction: {exc}", "args": command.args})
                    continue
            try:
                attempts = max(1, min(int(os.getenv("AI_COMMAND_RETRIES", "2")), 3))
                result: dict[str, Any] = {}
                # A bridge error before the post-action read must never be
                # reported as a successful move. Verification becomes true
                # only after _verify observes the requested state in TTS.
                verification: dict[str, Any] = {"verified": False, "checks": [], "errors": ["move was not verified"]}
                last_error = ""
                for attempt in range(1, attempts + 1):
                    try:
                        result = self.request(command.action, self._bridge_args(command))
                        verification = self._verify(command)
                        if verification.get("verified", False):
                            break
                        last_error = "; ".join(verification.get("errors", []))
                    except Exception as exc:
                        last_error = str(exc)
                    if attempt < attempts:
                        continue
                status = "executed" if verification.get("verified", False) else "unverified"
                entry = {"action": command.action, "status": status, "attempts": attempt, "result": result, "verification": verification}
                if last_error and status != "executed":
                    entry["error"] = last_error
                results.append(entry)
            except Exception as exc:  # bridge errors become retryable evidence, not crashes
                results.append({"action": command.action, "status": "failed", "error": str(exc), "args": command.args})
        return {"executed": results, "approval_required": proposals}

    @staticmethod
    def _is_double_stacked_checker(source: dict[str, Any], objects: list[dict[str, Any]]) -> bool:
        """Return true when this table represents a king as two stacked checkers."""
        source_position = source.get("position") or {}
        try:
            source_x = float(source_position["x"])
            source_y = float(source_position["y"])
            source_z = float(source_position["z"])
        except (KeyError, TypeError, ValueError):
            return False

        bounds = source.get("bounds") or {}
        size = bounds.get("size") or {}
        try:
            if float(size.get("y", 0)) >= 0.4:
                return True
        except (TypeError, ValueError):
            pass

        source_guid = str(source.get("guid") or "")
        for candidate in objects:
            if not isinstance(candidate, dict) or str(candidate.get("guid") or "") == source_guid:
                continue
            if str(candidate.get("type", "")).lower() != "checker":
                continue
            position = candidate.get("position") or {}
            try:
                delta_x = float(position["x"]) - source_x
                delta_y = abs(float(position["y"]) - source_y)
                delta_z = float(position["z"]) - source_z
            except (KeyError, TypeError, ValueError):
                continue
            if (delta_x * delta_x + delta_z * delta_z) <= 0.16 and 0.05 <= delta_y <= 1.0:
                return True
        return False

    def _verify(self, command: ParsedCommand) -> dict[str, Any]:
        guid = command.args.get("guid")
        if not guid or command.action not in {"move_object", "rotate_object", "set_object_lock"}:
            return {"verified": True, "checks": ["bridge acknowledged action"]}
        actual = self.request("get_object", {"guid": guid})
        errors: list[str] = []
        if command.action == "set_object_lock" and actual.get("locked") != command.args.get("locked"):
            errors.append("lock state did not match requested state")
        if command.action == "move_object":
            position = actual.get("position") or {}
            for axis in ("x", "y", "z"):
                if abs(float(position.get(axis, 0)) - float(command.args[axis])) > 0.15:
                    errors.append(f"position.{axis} did not settle at target")
        if command.action == "rotate_object":
            rotation = actual.get("rotation") or {}
            for axis in ("x", "y", "z"):
                if abs(float(rotation.get(axis, 0)) - float(command.args[axis])) > 1.0:
                    errors.append(f"rotation.{axis} did not settle at target")
        return {"verified": not errors, "checks": ["post-action get_object"], "errors": errors, "object": actual}

    @staticmethod
    def _bridge_args(command: ParsedCommand) -> dict[str, Any]:
        args = dict(command.args)
        if command.action == "move_object":
            # V6 moves GUID-resolved pieces with setPositionSmooth(position,
            # false, false).  The Lua bridge rebuilds the position from flat
            # scalar fields, avoiding External Editor vector wrappers.
            return {
                "guid": args["guid"],
                "position": {axis: float(args[axis]) for axis in ("x", "y", "z")},
                "smooth": True,
                "collide": False,
                "fast": False,
            }
        if command.action == "rotate_object":
            return {"guid": args["guid"], "rotation": {axis: float(args[axis]) for axis in ("x", "y", "z")}}
        if command.action == "spawn_builtin":
            return {
                "object_type": args["object_type"],
                "position": {axis: float(args[axis]) for axis in ("x", "y", "z")},
            }
        return args
