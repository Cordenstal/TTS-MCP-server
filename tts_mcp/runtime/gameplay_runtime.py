from __future__ import annotations

"""Bounded game-play intelligence for the TTS AI gateway.

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


def should_capture_game_vision(message: str, game: str, lifecycle: str) -> bool:
    """Return whether this chat explicitly starts a live move-preparation turn.

    Camera movement and screen capture are expensive side effects. Ordinary
    conversation, status queries, and setup requests should not trigger them.
    """
    if not str(game).strip() or str(lifecycle).strip().lower() != "running":
        return False
    text = str(message or "").strip().lower()
    if not text:
        return False
    return bool(
        re.search(r"\b(?:make|take|play)\s+(?:your\s+|a\s+|the\s+)?move\b", text)
        or re.search(r"\b(?:move|attack|capture)\b", text)
    )


def checkers_capture_holding_position(captured: dict[str, Any], objects: list[dict[str, Any]]) -> dict[str, float]:
    """Choose a visible, orderly off-board position for a captured checker."""
    expected = {f"{letter}{rank}" for letter in "ABCDEFGH" for rank in range(1, 9)}
    squares: dict[str, tuple[float, float]] = {}
    for item in objects:
        if not isinstance(item, dict):
            continue
        position = item.get("position") or {}
        try:
            x, z = float(position["x"]), float(position["z"])
        except (KeyError, TypeError, ValueError):
            continue
        for tag in item.get("tags") or []:
            square = str(tag).strip().upper()
            if re.fullmatch(r"[A-H][1-8]", square):
                if square in squares:
                    raise ValueError("checkers square tags are ambiguous; cannot place a captured checker safely")
                squares[square] = (x, z)
    if set(squares) != expected:
        raise ValueError("the complete tagged checkers board is required to place a captured checker off-board")

    x_centers = sorted({position[0] for position in squares.values()})
    z_centers = sorted({position[1] for position in squares.values()})
    step = min(
        min(second - first for first, second in zip(x_centers, x_centers[1:])),
        min(second - first for first, second in zip(z_centers, z_centers[1:])),
    )
    captured_name = f"{captured.get('name', '')} {' '.join(str(tag) for tag in captured.get('tags') or [])}".lower()
    is_red = "red" in captured_name
    board_edge = max(x_centers) if is_red else min(x_centers)
    direction = 1.0 if is_red else -1.0
    same_color_off_board = 0
    for item in objects:
        if not isinstance(item, dict) or str(item.get("guid") or "") == str(captured.get("guid") or ""):
            continue
        if str(item.get("type", "")).lower() != "checker":
            continue
        position = item.get("position") or {}
        try:
            is_off_board = (float(position["x"]) - board_edge) * direction > step * 0.5
        except (KeyError, TypeError, ValueError):
            continue
        item_name = f"{item.get('name', '')} {' '.join(str(tag) for tag in item.get('tags') or [])}".lower()
        if is_off_board and ("red" in item_name) == is_red:
            same_color_off_board += 1
    column, row = divmod(same_color_off_board, len(z_centers))
    captured_position = captured.get("position") or {}
    try:
        y = float(captured_position["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("captured checker has no usable height") from exc
    return {
        "x": board_edge + direction * step * (2 + column),
        "y": y,
        "z": z_centers[row],
    }


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
    for _ in re.finditer(r"^\s*KILLTEAM_ROLL_INITIATIVE\s*$", text, re.I | re.M):
        add("killteam_roll_initiative", {})
    for m in re.finditer(r"KILLTEAM_SELECT_ROSTER\[([^\]]+)\]", text, re.I):
        add("killteam_select_roster_card", {"contained_guid": m.group(1).strip()})
    for _ in re.finditer(r"^\s*KILLTEAM_LOCK_ROSTERS\s*$", text, re.I | re.M):
        add("killteam_lock_rosters", {})
    for m in re.finditer(r"KILLTEAM_START_DEPLOYMENT\[([^\]]+)\]", text, re.I):
        add("killteam_start_setup_deployment", {"operative_id": m.group(1).strip()})
    for m in re.finditer(r"KILLTEAM_SETUP_PLACE\[([^,\]]+),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r")\]", text, re.I):
        add("killteam_setup_place_model", {
            "guid": m.group(1).strip(),
            "x": float(m.group(2)),
            "y": float(m.group(3)),
            "z": float(m.group(4)),
        })
    for m in re.finditer(r"KILLTEAM_DEPLOY_SETUP\[([^,\]]+),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r")\]", text, re.I):
        add("killteam_deploy_setup_operative", {
            "guid": m.group(1).strip(),
            "x": float(m.group(2)),
            "y": float(m.group(3)),
            "z": float(m.group(4)),
        })
    for _ in re.finditer(r"^\s*KILLTEAM_ROLLBACK_PENDING\s*$", text, re.I | re.M):
        add("killteam_rollback_pending_deployment", {})
    for m in re.finditer(r"KILLTEAM_RECONCILE_SETUP\[([^\]]+)\]", text, re.I):
        add("killteam_reconcile_setup_step", {"side_id": m.group(1).strip()})
    for m in re.finditer(r"KILLTEAM_PLACE\[([^,\]]+),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r"),\s*(" + _NUMBER + r")\]", text, re.I):
        add("killteam_place_operative", {
            "guid": m.group(1).strip(),
            "x": float(m.group(2)),
            "y": float(m.group(3)),
            "z": float(m.group(4)),
        })
    for m in re.finditer(
        r"KILLTEAM_VALIDATE_SETUP\[([A-Za-z0-9_-]{1,64})\]",
        text,
        re.I,
    ):
        add("killteam_begin_setup_validation", {"action_id": m.group(1)})
    for _ in re.finditer(r"^\s*KILLTEAM_DEPLOY_TEST\s*$", text, re.I | re.M):
        add("killteam_deploy_test_model", {})
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
            if item["action"] in {
                "move_object",
                "killteam_roll_initiative",
                "killteam_select_roster_card",
                "killteam_lock_rosters",
                "killteam_start_setup_deployment",
                "killteam_setup_place_model",
                "killteam_deploy_setup_operative",
                "killteam_rollback_pending_deployment",
                "killteam_reconcile_setup_step",
                "killteam_place_operative",
                "killteam_deploy_test_model",
                "killteam_begin_setup_validation",
                "rotate_object",
                "set_object_lock",
                "spawn_builtin",
                "spawn_catalog",
                "place_catalog",
                "broadcast",
                "destroy_object",
            }:
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


class GamePromptBuilder:
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
        selected_game = game.strip() or "none"
        base = (
            "You are a Tabletop Simulator game-playing opponent. Play the selected game as the AI-controlled side against human players.\n"
            "Use only the selected game's rules; do not import rules or roles from another game. Use only state visible to the AI player.\n"
            "Before moving, verify the AI side, whose turn it is, the board state, and the legal action. If anything is uncertain, say what is missing and ask for clarification. Never guess.\n"
            "When play is running and it is the verified AI turn, choose and execute a legal move yourself. State it briefly and emit the executable command; do not ask a human to move for you.\n"
            "Prefer the fast structured object_list observation. Use a screenshot when object data is missing, contradictory, visually ambiguous, or after a move lands more than 0.5 world units from its expected position on any axis.\n"
            "If any action or verification fails, stop issuing actions, report the failure in concise natural language, and wait for player instructions. A player's manual correction is not evidence until you re-observe the board.\n"
            "Use live object data for GUIDs and world coordinates. Never invent GUIDs or use visual guesses instead of structured coordinates. Preserve the source object's y coordinate.\n"
            "For board games, copy target x/z values from the live square-center mapping. Never calculate a diagonal with sqrt(2), pixel offsets, or an approximate midpoint; a target between square centers is invalid.\n"
            "For ordinary object actions, emit only these commands: MOVE[guid,x,y,z], ROTATE[guid,x,y,z], LOCK[guid], UNLOCK[guid], SPAWN[guid,x,z], PLACE[guid,x,z], SPAWN_BUILTIN[type,x,y,z], BROADCAST[text], DESTROY[guid]. Destruction requires host approval.\n"
            "Do not select or spawn bags, decks, or containers as scene objects. Keep responses concise and do not invent narrative scenes. Keep raw inventories, GUID lists, positions, rotations, bounds, tags, and internal diagnostics out of player-facing chat; use them internally and report only the requested conclusion or next action.\n"
        )
        sections = [
            base,
            f"Selected game: {selected_game}",
            f"Intent for this turn: {intent.value}",
            "The authoritative current Tabletop Simulator state is supplied separately after this instruction.",
        ]
        if rules:
            sections.append("Selected game rules:\n" + rules)
        elif game:
            sections.append(
                "No rules file was found for the selected game. Do not make a move until the host provides "
                "or installs that game's rules under game_rules/<name>/rules.md."
            )
        if selected_game.lower() == "checkers":
            sections.append(
                "CHECKERS EXECUTION PROTOCOL (mandatory):\n"
                "In this chat gateway, the direct tts_move_checkers_piece MCP tool is not callable. "
                "The only way to execute the validated checkers move path is the MOVE line below.\n"
                "The gateway does not execute prose, algebraic notation, or a tool name. "
                "For exactly one black move, emit exactly one standalone line in this form:\n"
                "MOVE[black_piece_guid,target_square_center_x,source_piece_y,target_square_center_z]\n"
                "The GUID is the live source piece GUID. The x and z values are the destination square center, not the source position. "
                "Copy the destination x/z from the authoritative live square mapping; preserve the source y. "
                "Do not write 'from', 'to', a second bracket, a zone name, or explanatory text on that line. "
                "The server converts this command into the validated checkers movement path, which rejects occupied, non-diagonal, backward, and illegal capture moves. "
                "Before emitting it, check every black piece for a mandatory capture; if any capture exists, emit only a legal capture. "
                "If no legal move can be proven, emit no MOVE command and state the missing evidence."
            )
        if selected_game.lower() == "killteam":
            sections.append(
                "KILL TEAM OBSERVATION AND MOVEMENT PROTOCOL (mandatory):\n"
                "Call tts_killteam_setup once when the loaded table or roster changes, then call "
                "tts_killteam_observe only when you need fresh live state outside automatic setup. The returned AI "
                "operatives contain operative_id, exact TTS guid, name, description, profile, bounds, and x/y/z "
                "position. Use those records to identify the AI's models; never infer a GUID from a screenshot or "
                "invent one.\n"
                "If the live observation does not contain the model or profile needed for the requested action, call "
                "tts_killteam_get_roster. It reads only the dedicated AI roster container and returns bounded item "
                "names, descriptions, tags, and contained GUID metadata. Do not inspect arbitrary containers.\n"
                "When objective control is the goal, call tts_killteam_plan_objective_move with the operative_id "
                "before emitting MOVE. Use the returned MOVE target instead of inventing a coordinate and prefer "
                "the safest contesting point the planner returns.\n"
                "To move one of the AI's own models, emit exactly one standalone line in this form:\n"
                "MOVE[guid,x,y,z]\n"
                "Use the live GUID from tts_killteam_observe or the current setup deployment plan. Preserve the source y coordinate unless you are "
                "intentionally changing elevation. Do not emit KILLTEAM_PLACE for ordinary movement. Before moving "
                "a model near an enemy, inspect the current board and use the visible model positions, terrain "
                "bounds, and line-of-sight probe; stop if any identity or position is unclear."
                "\nFor semantic pregame roster setup, use these setup commands before the firefight phase:\n"
                "KILLTEAM_ROLL_INITIATIVE\n"
                "KILLTEAM_SELECT_ROSTER[contained_guid]\n"
                "KILLTEAM_LOCK_ROSTERS\n"
                "KILLTEAM_START_DEPLOYMENT[operative_id]\n"
                "MOVE[guid,target_x,target_y,target_z]\n"
                "KILLTEAM_ROLLBACK_PENDING\n"
                "KILLTEAM_RECONCILE_SETUP[side_id]\n"
                "Assume the AI side has initiative unless the host explicitly overrides it outside the runtime. After tts_killteam_setup, use setup.next_action and setup.ai_plan to select the first AI model and use its recommended position. Call KILLTEAM_START_DEPLOYMENT for one model at a time, then emit exactly one MOVE using the live figurine GUID and recommended coordinates, then call KILLTEAM_RECONCILE_SETUP for the active side. Deploy only the number shown by setup.current_batch_target for the active AI pass; after the AI batch is complete, stop and wait for the player to place the active human batch. Never emit an extra AI deployment after the runtime switches current_side to the opponent. If setup.mode is roster_cards, use KILLTEAM_SELECT_ROSTER and KILLTEAM_LOCK_ROSTERS first. "
                "Follow setup.ai_plan.deployment_order during model deployment, taking the first undeployed entry for the active stage. Use the live figurine GUID from setup.next_action or the roster/model observation when placing the model. "
                "The runtime tracks the pending setup operative and the active side after each confirmed deployment.\n"
                "Use MOVE[guid,target_x,target_y,target_z] for the live figurine move. The GUID must identify the figurine you are placing, not the roster-card operative ID; preserve its live y coordinate. "
                "For the dedicated placement-only setup bridge, use tts_killteam_setup_ping and tts_killteam_setup_list_objects to resolve the live model, then use "
                "KILLTEAM_SETUP_PLACE[guid,x,y,z] for exact setup placement instead of the legacy deployment flow."
                "\nFor the deployment smoke test, emit exactly one standalone line:\n"
                "KILLTEAM_DEPLOY_TEST\n"
                "This zero-argument command resolves exactly one model whose name contains Plague Marine Warrior "
                "and exactly one destination tagged _deployment_zone_blue. It copies the zone's x/z coordinates, preserves the "
                "model's y coordinate, moves the model, and verifies its final x/z position within 0.25 units. "
                "It does not require Kill Team setup."
                "\nFor the agreed Save 131 vertical-slice test, emit exactly one standalone line:\n"
                "KILLTEAM_VALIDATE_SETUP[action_id]\n"
                "Use a new stable action_id such as setup-shot-001. The server places the discovered staged "
                "operative at _start_test_spot, verifies nine-ray LOS to the discovered visible enemy, rolls only "
                "Blue's Boltgun dice, and pauses. Never claim Red rolled or acknowledge Red's roll yourself."
            )
        return "\n\n".join(sections)


# Compatibility alias for integrations that imported the old class name. New
# code should use GamePromptBuilder because the prompt is not D&D-specific.
DndPromptBuilder = GamePromptBuilder


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
    def __init__(
        self,
        request: Callable[[str, dict[str, Any]], dict[str, Any]],
        propose: Callable[[dict[str, Any]], str],
        review: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.request = request
        self.propose = propose
        self.review = review

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
                return {
                    "executed": results,
                    "approval_required": proposals,
                    "stopped": True,
                    "stop_reason": "action was blocked; waiting for player instructions",
                }
            effective_command = command
            position_correction: dict[str, Any] | None = None
            captured_checker_guid: str | None = None
            king_companions: list[dict[str, Any]] = []
            crown_after_move = False
            if active_game.strip().lower() == "checkers" and command.action == "move_object":
                # The active checkers save is host-mapped with the red side at
                # negative Z. AI-controlled men must advance toward red, never
                # sideways or away from it. Validate the source in TTS before
                # allowing the mutating bridge action.
                try:
                    # Prefer the authoritative scene snapshot for source lookup.
                    # This avoids failing a safe move when a TTS build drops a
                    # transient single-object callback.
                    stack = self.request("list_objects", {"max_results": 250, "compact": True})
                    live_objects = stack.get("objects") or []
                    source = next(
                        (item for item in live_objects if str(item.get("guid", "")).lower() == str(command.args["guid"]).lower()),
                        None,
                    )
                    if source is None:
                        source = self.request("get_object", {"guid": command.args["guid"]})
                    if str(source.get("type", "")).lower() != "checker":
                        results.append({"action": command.action, "status": "blocked", "reason": "only Checker objects may be moved during a checkers game", "args": command.args})
                        return {
                            "executed": results,
                            "approval_required": proposals,
                            "stopped": True,
                            "stop_reason": "action was blocked; waiting for player instructions",
                        }
                    king_companions = self._stacked_checker_companions(source, live_objects)
                    is_king = bool(king_companions) or self._is_double_stacked_checker(source, live_objects)
                    corrected_args, position_correction, correction_error = self._normalize_checkers_move(
                        command.args,
                        source,
                        live_objects,
                    )
                    if correction_error:
                        results.append({
                            "action": command.action,
                            "status": "blocked",
                            "reason": correction_error,
                            "args": command.args,
                            "source_position": source.get("position"),
                        })
                        return {
                            "executed": results,
                            "approval_required": proposals,
                            "stopped": True,
                            "stop_reason": "action was blocked; waiting for player instructions",
                        }
                    if corrected_args != command.args:
                        effective_command = ParsedCommand(command.action, corrected_args, command.destructive)
                    captured_checker_guid, capture_error = self._checkers_capture_target(
                        source,
                        effective_command.args,
                        live_objects,
                    )
                    if capture_error:
                        results.append({
                            "action": command.action,
                            "status": "blocked",
                            "reason": capture_error,
                            "args": effective_command.args,
                            "source_position": source.get("position"),
                        })
                        return {
                            "executed": results,
                            "approval_required": proposals,
                            "stopped": True,
                            "stop_reason": "action was blocked; waiting for player instructions",
                        }
                    # A normal step is one row; a potential capture spans two
                    # rows. Men may capture backward under English draughts,
                    # so only reject sideways/backward *ordinary* moves here.
                    # A double-stacked piece is a crowned king and may move in
                    # either direction.
                    source_position = source.get("position") or {}
                    target_z = float(effective_command.args["z"])
                    delta_z = target_z - float(source_position["z"])
                    if not is_king and delta_z >= -0.5 and abs(delta_z) < 3.0:
                        results.append({
                            "action": command.action,
                            "status": "blocked",
                            "reason": "checkers moves must advance toward the red side (negative world Z)",
                            "args": effective_command.args,
                            "source_position": source.get("position"),
                        })
                        return {
                            "executed": results,
                            "approval_required": proposals,
                            "stopped": True,
                            "stop_reason": "action was blocked; waiting for player instructions",
                        }
                    crown_after_move = not is_king and self._checkers_reaches_black_king_row(
                        effective_command.args,
                        live_objects,
                    )
                    # A board-square move is verified immediately after the
                    # bridge callback. Animated motion can still be in flight
                    # at that point and produces a false postcondition
                    # failure, so validated checkers moves are atomic.
                    checkers_args = dict(effective_command.args)
                    checkers_args["_checkers_instant"] = True
                    effective_command = ParsedCommand(command.action, checkers_args, command.destructive)
                except Exception as exc:
                    results.append({"action": command.action, "status": "blocked", "reason": f"could not verify checkers move direction: {exc}", "args": command.args})
                    return {
                        "executed": results,
                        "approval_required": proposals,
                        "stopped": True,
                        "stop_reason": "action was blocked; waiting for player instructions",
                    }
            try:
                # A failed mutation is an uncertainty stop. Do not replay an
                # unknown or unverified TTS action automatically; the next
                # step requires fresh player feedback.
                attempts = 1
                result: dict[str, Any] = {}
                # A bridge error before the post-action read must never be
                # reported as a successful move. Verification becomes true
                # only after _verify observes the requested state in TTS.
                verification: dict[str, Any] = {"verified": False, "checks": [], "errors": ["move was not verified"]}
                capture: dict[str, Any] | None = None
                last_error = ""
                for attempt in range(1, attempts + 1):
                    try:
                        result = self.request(effective_command.action, self._bridge_args(effective_command))
                        verification = self._verify(effective_command)
                        if verification.get("verified", False):
                            break
                        last_error = "; ".join(verification.get("errors", []))
                    except Exception as exc:
                        last_error = str(exc)
                    if attempt < attempts:
                        continue
                if verification.get("verified", False) and captured_checker_guid:
                    try:
                        captured_checker = next(
                            item for item in live_objects
                            if str(item.get("guid", "")).lower() == captured_checker_guid.lower()
                        )
                        holding_position = checkers_capture_holding_position(captured_checker, live_objects)
                        # Save 128 has no physical shelf below the off-board
                        # capture rows. Lock the captured checker first so it
                        # cannot fall through the table between the move
                        # callback and verified readback.
                        capture_lock_command = ParsedCommand(
                            "set_object_lock",
                            {"guid": captured_checker_guid, "locked": True},
                        )
                        capture_lock_result = self.request(
                            "set_object_lock",
                            self._bridge_args(capture_lock_command),
                        )
                        capture_lock_verification = self._verify(capture_lock_command)
                        if not capture_lock_verification.get("verified", False):
                            raise RuntimeError("captured checker could not be locked before removal")
                        capture_command = ParsedCommand(
                            "move_object",
                            {"guid": captured_checker_guid, **holding_position, "_checkers_instant": True},
                        )
                        capture_result = self.request("move_object", self._bridge_args(capture_command))
                        capture_verification = self._verify(capture_command)
                        if not capture_verification.get("verified", False):
                            raise RuntimeError("captured checker did not reach its off-board holding position")
                        capture = {
                            "guid": captured_checker_guid,
                            "off_board_position": holding_position,
                            "lock": {
                                "result": capture_lock_result,
                                "verification": capture_lock_verification,
                            },
                            "result": capture_result,
                            "verification": capture_verification,
                        }
                    except Exception as exc:
                        last_error = f"captured checker removal was not verified: {exc}"
                        verification = {
                            **verification,
                            "verified": False,
                            "errors": [*verification.get("errors", []), last_error],
                        }
                if verification.get("verified", False) and king_companions:
                    try:
                        source_y = float((source.get("position") or {})["y"])
                        companion_moves: list[dict[str, Any]] = []
                        for companion in king_companions:
                            companion_position = companion.get("position") or {}
                            companion_command = ParsedCommand(
                                "move_object",
                                {
                                    "guid": str(companion["guid"]),
                                    "x": float(effective_command.args["x"]),
                                    "y": float(effective_command.args["y"]) + float(companion_position["y"]) - source_y,
                                    "z": float(effective_command.args["z"]),
                                    "_checkers_instant": True,
                                },
                            )
                            companion_result = self.request("move_object", self._bridge_args(companion_command))
                            companion_verification = self._verify(companion_command)
                            if not companion_verification.get("verified", False):
                                raise RuntimeError("king marker did not follow the crowned checker")
                            companion_moves.append({"guid": companion_command.args["guid"], "result": companion_result})
                        king_stack = {"moved_markers": companion_moves}
                    except Exception as exc:
                        last_error = f"king marker movement was not verified: {exc}"
                        verification = {
                            **verification,
                            "verified": False,
                            "errors": [*verification.get("errors", []), last_error],
                        }
                else:
                    king_stack = None
                crown: dict[str, Any] | None = None
                if verification.get("verified", False) and crown_after_move:
                    try:
                        crown_position = {
                            "x": float(effective_command.args["x"]),
                            "y": float(effective_command.args["y"]) + 0.5,
                            "z": float(effective_command.args["z"]),
                        }
                        spawned = self.request("spawn_catalog", {"guid": str(source["guid"]), "position": crown_position})
                        marker = spawned.get("object") or {}
                        marker_guid = str(marker.get("guid") or "")
                        if not marker_guid:
                            raise RuntimeError("king marker clone returned no GUID")
                        marker_command = ParsedCommand(
                            "move_object",
                            {"guid": marker_guid, **crown_position, "_checkers_instant": True},
                        )
                        marker_move_result = self.request(
                            "move_object",
                            self._bridge_args(marker_command),
                        )
                        try:
                            marker_verification = self._verify(marker_command)
                        except Exception:
                            # TTS merges two stacked checkers into a new
                            # object in some saves. That destroys the clone's
                            # GUID even though the physical king is correct.
                            marker_verification = self._verify_checkers_king_stack(crown_position)
                        if not marker_verification.get("verified", False):
                            raise RuntimeError("king marker did not settle on the crowned checker")
                        crown = {
                            "marker_guid": marker_guid,
                            "position": crown_position,
                            "result": spawned,
                            "move": marker_move_result,
                            "verification": marker_verification,
                        }
                    except Exception as exc:
                        last_error = f"crowning was not verified: {exc}"
                        verification = {
                            **verification,
                            "verified": False,
                            "errors": [*verification.get("errors", []), last_error],
                        }
                status = "executed" if verification.get("verified", False) else "unverified"
                entry = {"action": command.action, "status": status, "attempts": attempt, "result": result, "verification": verification}
                if position_correction is not None:
                    entry["position_correction"] = position_correction
                if capture is not None:
                    entry["capture"] = capture
                if king_stack is not None:
                    entry["king_stack"] = king_stack
                if crown is not None:
                    entry["crown"] = crown
                if last_error and status != "executed":
                    entry["error"] = last_error
                if status != "executed" and verification.get("visual_review_required") and self.review is not None:
                    try:
                        entry["visual_review"] = self.review(entry)
                    except Exception as exc:
                        entry["visual_review"] = {
                            "requested": True,
                            "attached": False,
                            "error": str(exc)[:300],
                        }
                results.append(entry)
                if status != "executed":
                    return {
                        "executed": results,
                        "approval_required": proposals,
                        "stopped": True,
                        "stop_reason": "action failed; waiting for player instructions",
                    }
            except Exception as exc:  # bridge errors become fail-fast evidence, not crashes
                results.append({"action": command.action, "status": "failed", "error": str(exc), "args": command.args})
                return {
                    "executed": results,
                    "approval_required": proposals,
                    "stopped": True,
                    "stop_reason": "action failed; waiting for player instructions",
                }
        return {"executed": results, "approval_required": proposals, "stopped": False}

    @staticmethod
    def _checkers_piece_identity(piece: dict[str, Any]) -> str:
        tags = piece.get("tags") or []
        tag_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags)
        return f"{piece.get('name', '')} {tag_text}".lower()

    @classmethod
    def _checkers_capture_target(
        cls,
        source: dict[str, Any],
        target: dict[str, Any],
        objects: list[dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        """Resolve the exact red checker removed by a validated two-square jump."""
        source_position = source.get("position") or {}
        try:
            source_x = float(source_position["x"])
            source_z = float(source_position["z"])
            target_x = float(target["x"])
            target_z = float(target["z"])
        except (KeyError, TypeError, ValueError):
            return None, "checkers capture requires numeric source and target coordinates"

        tagged_squares = cls._checkers_tagged_square_grid(objects)
        midpoint_x = (source_x + target_x) / 2
        midpoint_z = (source_z + target_z) / 2
        tolerance = 0.5
        is_capture = False
        if tagged_squares is not None:
            def nearest_square(x: float, z: float) -> str:
                return min(
                    tagged_squares,
                    key=lambda square: (tagged_squares[square][0] - x) ** 2 + (tagged_squares[square][1] - z) ** 2,
                )

            source_square = nearest_square(source_x, source_z)
            target_square = nearest_square(target_x, target_z)
            file_delta = ord(target_square[0]) - ord(source_square[0])
            rank_delta = int(target_square[1]) - int(source_square[1])
            is_capture = abs(file_delta) == abs(rank_delta) == 2
            if is_capture:
                midpoint_square = f"{chr(ord(source_square[0]) + file_delta // 2)}{int(source_square[1]) + rank_delta // 2}"
                midpoint_x, midpoint_z = tagged_squares[midpoint_square]
                centers = [position for position in tagged_squares.values()]
                axis_steps = [
                    abs(second - first)
                    for axis in (0, 1)
                    for first, second in zip(sorted({position[axis] for position in centers}), sorted({position[axis] for position in centers})[1:])
                ]
                tolerance = max(0.25, min(axis_steps) * 0.30)
        else:
            checker_positions: list[tuple[float, float]] = []
            for item in objects:
                if not isinstance(item, dict) or str(item.get("type", "")).lower() != "checker":
                    continue
                position = item.get("position") or {}
                try:
                    checker_positions.append((float(position["x"]), float(position["z"])))
                except (KeyError, TypeError, ValueError):
                    continue
            if len(checker_positions) >= 2:
                def step(axis: int) -> float | None:
                    differences = sorted(
                        abs(first[axis] - second[axis])
                        for index, first in enumerate(checker_positions)
                        for second in checker_positions[index + 1:]
                        if 0.75 < abs(first[axis] - second[axis]) < 3.0
                    )
                    return differences[0] if differences else None

                step_x, step_z = step(0), step(1)
                if step_x and step_z:
                    is_capture = round((target_x - source_x) / step_x) in {-2, 2} and round((target_z - source_z) / step_z) in {-2, 2}
                    tolerance = max(0.25, min(step_x, step_z) * 0.30)

        if not is_capture:
            return None, None
        candidates: list[dict[str, Any]] = []
        source_guid = str(source.get("guid") or "").lower()
        for item in objects:
            if not isinstance(item, dict) or str(item.get("guid") or "").lower() == source_guid:
                continue
            if str(item.get("type", "")).lower() != "checker":
                continue
            position = item.get("position") or {}
            try:
                at_midpoint = abs(float(position["x"]) - midpoint_x) <= tolerance and abs(float(position["z"]) - midpoint_z) <= tolerance
            except (KeyError, TypeError, ValueError):
                continue
            if at_midpoint:
                candidates.append(item)
        red_candidates = [item for item in candidates if "red" in cls._checkers_piece_identity(item)]
        if len(red_candidates) != 1:
            return None, "a two-square checkers move must jump exactly one opposing red checker"
        return str(red_candidates[0].get("guid") or ""), None

    @classmethod
    def _checkers_reaches_black_king_row(cls, target: dict[str, Any], objects: list[dict[str, Any]]) -> bool:
        tagged_squares = cls._checkers_tagged_square_grid(objects)
        if tagged_squares is None:
            return False
        try:
            target_z = float(target["z"])
        except (KeyError, TypeError, ValueError):
            return False
        z_values = [position[1] for position in tagged_squares.values()]
        spacing = min(second - first for first, second in zip(sorted(set(z_values)), sorted(set(z_values))[1:]))
        return abs(target_z - min(z_values)) <= max(0.25, spacing * 0.30)

    @staticmethod
    def _stacked_checker_companions(source: dict[str, Any], objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        source_position = source.get("position") or {}
        try:
            source_x = float(source_position["x"])
            source_y = float(source_position["y"])
            source_z = float(source_position["z"])
        except (KeyError, TypeError, ValueError):
            return []
        source_guid = str(source.get("guid") or "")
        companions: list[dict[str, Any]] = []
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
                companions.append(candidate)
        return companions

    @classmethod
    def _checkers_tagged_square_grid(
        cls,
        objects: list[dict[str, Any]],
    ) -> dict[str, tuple[float, float]] | None:
        """Return the authoritative A1-H8 square centers when TTS exposes them.

        Checkers themselves are movable and can be left a few hundredths of a
        unit off-center after prior turns.  Their positions are therefore a
        poor source of board geometry when the save includes tagged Layout
        zones for every square.
        """
        squares: dict[str, tuple[float, float]] = {}
        for item in objects:
            if not isinstance(item, dict):
                continue
            tags = item.get("tags") or []
            position = item.get("position") or {}
            try:
                x = float(position["x"])
                z = float(position["z"])
            except (KeyError, TypeError, ValueError):
                continue
            for tag in tags:
                square = str(tag).strip().upper()
                if not re.fullmatch(r"[A-H][1-8]", square):
                    continue
                if square in squares:
                    # Ambiguous zones must not control a physical move.
                    return None
                squares[square] = (x, z)

        expected = {f"{letter}{rank}" for letter in "ABCDEFGH" for rank in range(1, 9)}
        return squares if set(squares) == expected else None

    @classmethod
    def _normalize_checkers_move_with_tagged_squares(
        cls,
        args: dict[str, Any],
        source: dict[str, Any],
        objects: list[dict[str, Any]],
        squares: dict[str, tuple[float, float]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        """Validate a move against fixed board zones instead of movable men."""
        source_position = source.get("position") or {}
        try:
            source_x = float(source_position["x"])
            source_z = float(source_position["z"])
            requested_x = float(args["x"])
            requested_z = float(args["z"])
        except (KeyError, TypeError, ValueError):
            return dict(args), None, "checkers move requires numeric x and z coordinates"

        def nearest_square(x: float, z: float) -> tuple[str, float]:
            square, position = min(
                squares.items(),
                key=lambda entry: (entry[1][0] - x) ** 2 + (entry[1][1] - z) ** 2,
            )
            return square, ((position[0] - x) ** 2 + (position[1] - z) ** 2) ** 0.5

        source_square, source_distance = nearest_square(source_x, source_z)
        target_square, target_distance = nearest_square(requested_x, requested_z)
        column_centers = sorted({position[0] for position in squares.values()})
        rank_centers = sorted({position[1] for position in squares.values()})
        step = min(
            min(abs(second - first) for first, second in zip(column_centers, column_centers[1:])),
            min(abs(second - first) for first, second in zip(rank_centers, rank_centers[1:])),
        )
        source_tolerance = max(0.5, step * 0.30)
        target_tolerance = max(0.25, step * 0.30)
        if source_distance > source_tolerance:
            return dict(args), None, "source checker is not on a known checkers square; refusing an uncertain move"
        if target_distance > target_tolerance:
            return dict(args), None, "target is between tagged checkers squares; refusing an imprecise move"

        column_delta = ord(target_square[0]) - ord(source_square[0])
        rank_delta = int(target_square[1]) - int(source_square[1])
        if abs(column_delta) != abs(rank_delta) or abs(column_delta) not in {1, 2}:
            return dict(args), None, "target is not a one-step or capture diagonal on the checkers board"

        target_x, target_z = squares[target_square]
        for item in objects:
            if not isinstance(item, dict) or str(item.get("guid") or "") == str(source.get("guid") or ""):
                continue
            if str(item.get("type", "")).lower() != "checker":
                continue
            position = item.get("position") or {}
            try:
                occupied_x = float(position["x"])
                occupied_z = float(position["z"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(occupied_x - target_x) <= target_tolerance and abs(occupied_z - target_z) <= target_tolerance:
                return dict(args), None, "target square is occupied; refusing to move onto another checker"

        corrected = dict(args)
        corrected["x"] = target_x
        corrected["z"] = target_z
        if corrected == args:
            return corrected, None, None
        return corrected, {
            "requested": {"x": requested_x, "z": requested_z},
            "corrected": {"x": target_x, "z": target_z},
            "source_square": source_square,
            "target_square": target_square,
        }, None

    @classmethod
    def _normalize_checkers_move(
        cls,
        args: dict[str, Any],
        source: dict[str, Any],
        objects: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        """Snap only obvious model rounding to the live checkers square lattice.

        Vision models commonly calculate a diagonal using ``sqrt(2)``. TTS
        board squares are axis-aligned world-coordinate centers, so that
        calculation lands between squares. Prefer fixed A1-H8 Layout zones;
        only fall back to live checker spacing when the board has no complete
        tagged grid.
        """
        tagged_squares = cls._checkers_tagged_square_grid(objects)
        if tagged_squares is not None:
            return cls._normalize_checkers_move_with_tagged_squares(args, source, objects, tagged_squares)

        checker_positions: list[tuple[float, float]] = []
        for item in objects:
            if not isinstance(item, dict) or str(item.get("type", "")).lower() != "checker":
                continue
            position = item.get("position") or {}
            try:
                checker_positions.append((float(position["x"]), float(position["z"])))
            except (KeyError, TypeError, ValueError):
                continue
        if len(checker_positions) < 2:
            return dict(args), None, None

        def spacing(axis: int) -> float | None:
            differences = sorted(
                abs(first[axis] - second[axis])
                for index, first in enumerate(checker_positions)
                for second in checker_positions[index + 1:]
                if 0.75 < abs(first[axis] - second[axis]) < 3.0
            )
            return differences[0] if differences else None

        step_x = spacing(0)
        step_z = spacing(1)
        if step_x is None or step_z is None:
            return dict(args), None, None

        source_position = source.get("position") or {}
        try:
            source_x = float(source_position["x"])
            source_z = float(source_position["z"])
            requested_x = float(args["x"])
            requested_z = float(args["z"])
        except (KeyError, TypeError, ValueError):
            return dict(args), None, "checkers move requires numeric x and z coordinates"

        raw_dx = requested_x - source_x
        raw_dz = requested_z - source_z
        if abs(raw_dx) < 0.25 or abs(raw_dz) < 0.25:
            return dict(args), None, "checkers moves must change x and z diagonally; target is not a board square"

        steps_x = round(raw_dx / step_x)
        steps_z = round(raw_dz / step_z)
        if steps_x == 0 or steps_z == 0 or abs(steps_x) != abs(steps_z) or abs(steps_x) not in {1, 2}:
            return dict(args), None, "target is not a one-step or capture diagonal on the live checkers board"

        target_x = source_x + steps_x * step_x
        target_z = source_z + steps_z * step_z
        error_x = abs(requested_x - target_x)
        error_z = abs(requested_z - target_z)
        tolerance = max(0.25, min(step_x, step_z) * 0.30)
        if error_x > tolerance or error_z > tolerance:
            return dict(args), None, "target is between live checkers squares; refusing an imprecise move"

        # A landing square must be empty. This also prevents correcting a
        # stale model command onto another piece's square.
        for item in checker_positions:
            if abs(item[0] - target_x) <= tolerance and abs(item[1] - target_z) <= tolerance:
                try:
                    same_source = abs(item[0] - source_x) <= tolerance and abs(item[1] - source_z) <= tolerance
                except TypeError:
                    same_source = False
                if not same_source:
                    return dict(args), None, "target square is occupied; refusing to move onto another checker"

        corrected = dict(args)
        corrected["x"] = target_x
        corrected["z"] = target_z
        if corrected == args:
            return corrected, None, None
        return corrected, {
            "requested": {"x": requested_x, "z": requested_z},
            "corrected": {"x": target_x, "z": target_z},
            "grid_step": {"x": step_x, "z": step_z},
        }, None

    @staticmethod
    def _is_double_stacked_checker(source: dict[str, Any], objects: list[dict[str, Any]]) -> bool:
        """Return true when this table represents a king as two stacked checkers."""
        try:
            if float(source.get("quantity", 0)) >= 2:
                return True
        except (TypeError, ValueError):
            pass
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

        return bool(CommandExecution._stacked_checker_companions(source, objects))

    def _verify_checkers_king_stack(self, crown_position: dict[str, float]) -> dict[str, Any]:
        """Verify a crown that TTS merged into a new, replacement stack GUID."""
        listing = self.request("list_objects", {"max_results": 250, "compact": True})
        objects = [item for item in listing.get("objects", []) if isinstance(item, dict)]
        matches: list[dict[str, Any]] = []
        for item in objects:
            if str(item.get("type", "")).lower() != "checker":
                continue
            position = item.get("position") or {}
            try:
                at_crown_square = (
                    abs(float(position["x"]) - float(crown_position["x"])) <= 0.15
                    and abs(float(position["z"]) - float(crown_position["z"])) <= 0.15
                    and abs(float(position["y"]) - float(crown_position["y"])) <= 0.75
                )
            except (KeyError, TypeError, ValueError):
                continue
            if at_crown_square and self._is_double_stacked_checker(item, objects):
                matches.append(item)
        if len(matches) == 1:
            return {
                "verified": True,
                "checks": ["post-crown merged king stack"],
                "errors": [],
                "object": matches[0],
            }
        return {
            "verified": False,
            "checks": ["post-crown merged king stack"],
            "errors": ["no unique double-stacked checker was found on the crown square"],
        }

    def _verify(self, command: ParsedCommand) -> dict[str, Any]:
        guid = command.args.get("guid")
        if not guid or command.action not in {"move_object", "rotate_object", "set_object_lock"}:
            return {"verified": True, "checks": ["bridge acknowledged action"]}
        try:
            actual = self.request("get_object", {"guid": guid})
        except Exception:
            # Some TTS builds intermittently drop the compact single-object
            # callback while still answering list_objects. Keep verification
            # authoritative without treating a successful move as unverified
            # solely because that endpoint missed its callback.
            if command.action != "move_object":
                raise
            listing = self.request("list_objects", {"max_results": 250, "compact": True})
            actual = next(
                (item for item in listing.get("objects", []) if str(item.get("guid", "")).lower() == str(guid).lower()),
                None,
            )
            if actual is None:
                raise
        errors: list[str] = []
        position_delta: dict[str, float] = {}
        visual_review_required = False
        if command.action == "set_object_lock" and actual.get("locked") != command.args.get("locked"):
            errors.append("lock state did not match requested state")
        if command.action == "move_object":
            position = actual.get("position") or {}
            for axis in ("x", "y", "z"):
                delta = abs(float(position.get(axis, 0)) - float(command.args[axis]))
                position_delta[axis] = delta
                if delta > 0.15:
                    errors.append(f"position.{axis} did not settle at target (off by {delta:.3f})")
                if delta > 0.5:
                    visual_review_required = True
        if command.action == "rotate_object":
            rotation = actual.get("rotation") or {}
            for axis in ("x", "y", "z"):
                if abs(float(rotation.get(axis, 0)) - float(command.args[axis])) > 1.0:
                    errors.append(f"rotation.{axis} did not settle at target")
        return {
            "verified": not errors,
            "checks": ["post-action get_object"],
            "errors": errors,
            "object": actual,
            "position_delta": position_delta,
            "visual_review_required": visual_review_required,
        }

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
                "smooth": not bool(args.get("_checkers_instant", False)),
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
