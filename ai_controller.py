from __future__ import annotations

import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from session_store import SessionStore


ACTION_ID = re.compile(r"^[A-Za-z0-9]{4,12}$")
ACTION_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class ControllerState:
    active_game: str = ""
    state: str = "inactive"
    current_turn: str = "unknown"
    pause_reason: str = ""
    pending_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)


class AIController:
    """Host-controlled lifecycle and safety command state for the AI player."""

    def __init__(self, rules_root: Path, store: SessionStore, approval_executor: Any | None = None) -> None:
        self.rules_root = rules_root.resolve()
        self.store = store
        persisted = self.store.get_controller_state()
        saved_state = persisted.get("state", {}) if persisted else {}
        self.state = ControllerState(
            active_game=str(saved_state.get("active_game", "")),
            state=str(saved_state.get("state", "inactive")),
            current_turn=str(saved_state.get("current_turn", "unknown")),
            pause_reason=str(saved_state.get("pause_reason", "")),
            pending_approvals=dict(saved_state.get("pending_approvals", {})),
        )
        self._lock = threading.RLock()
        self.approval_executor = approval_executor

    @staticmethod
    def _public(text: str) -> dict[str, Any]:
        return {"text": text, "commands": [], "controller": True}

    def _audit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.store.record_event(
            event_type,
            payload,
            game_name=self.state.active_game or None,
        )

    def _persist(self) -> None:
        self.store.save_controller_state(
            {
                "active_game": self.state.active_game,
                "state": self.state.state,
                "current_turn": self.state.current_turn,
                "pause_reason": self.state.pause_reason,
                "pending_approvals": self.state.pending_approvals,
            }
        )

    def propose_approval(self, proposal: dict[str, Any]) -> str:
        """Create and persist a short manually typed host-approval ID."""
        with self._lock:
            for _ in range(20):
                action_id = "".join(secrets.choice(ACTION_ID_ALPHABET) for _ in range(6))
                if action_id not in self.state.pending_approvals:
                    break
            else:
                raise RuntimeError("Could not allocate a unique action ID")
            self.state.pending_approvals[action_id] = dict(proposal)
            self._persist()
            self._audit("action_proposed", {"action_id": action_id, "proposal": proposal})
            return action_id

    def _status_text(self) -> str:
        pending = ", ".join(sorted(self.state.pending_approvals)) or "none"
        game = self.state.active_game or "none"
        reason = self.state.pause_reason or "none"
        return (
            f"[AI status] game={game}; state={self.state.state}; "
            f"turn={self.state.current_turn}; pending_approval={pending}; "
            f"pause_reason={reason}"
        )

    def conversation_id(self) -> str:
        """Return a stable conversation namespace for the selected game."""
        game = self.state.active_game.strip().lower()
        return f"tts-game:{game}" if game else "tts-default"

    def context(self) -> dict[str, Any]:
        """Return the persisted lifecycle state used by the chat gateway."""
        with self._lock:
            return {
                "active_game": self.state.active_game,
                "state": self.state.state,
                "current_turn": self.state.current_turn,
                "pause_reason": self.state.pause_reason,
                "conversation_id": self.conversation_id(),
            }

    def set_approval_executor(self, executor: Any) -> None:
        self.approval_executor = executor

    def advance_turn(self, actor: str = "ai") -> str:
        """Advance the persisted autonomous turn counter after a completed turn."""
        with self._lock:
            current = self.state.current_turn
            try:
                number = int(current)
            except (TypeError, ValueError):
                number = 0
            self.state.current_turn = str(number + 1)
            self._persist()
            self._audit("turn_completed", {"actor": actor, "turn": self.state.current_turn})
            return self.state.current_turn

    def _is_host_command(self, command: str) -> bool:
        return command in {
            "game",
            "start",
            "pause",
            "resume",
            "stop",
            "status",
            "approve",
            "reject",
        }

    def handle(self, message: str, *, is_host: bool) -> dict[str, Any] | None:
        raw = message.strip()
        if not raw.lower().startswith("!ai"):
            return None

        parts = raw.split()
        if len(parts) == 1:
            return self._public("[AI] Available controls: !ai game, start, pause, resume, stop, status.")

        command = parts[1].lower()
        with self._lock:
            if self._is_host_command(command) and not is_host:
                response = self._public(
                    "[AI] I cannot follow that instruction because only the TTS host "
                    "may issue AI control commands."
                )
                self._audit("unauthorized_control_attempt", {"command": command})
                return response

            if command == "game":
                if len(parts) != 3 or not parts[2].strip():
                    return self._public("[AI] Use !ai game <name>.")
                game_name = parts[2].strip()
                game_dir = (self.rules_root / game_name).resolve()
                if game_dir.parent != self.rules_root or not game_dir.is_dir():
                    response = self._public(
                        f"[AI] I could not find the rules for '{game_name}'. "
                        f"Please create game_rules/{game_name}/ with an appropriate ruleset."
                    )
                    self._audit("game_rules_missing", {"game_name": game_name})
                    return response
                self.state.active_game = game_name
                self.state.state = "inactive"
                self.state.pause_reason = ""
                self._persist()
                self._audit("game_selected", {"game_name": game_name})
                return self._public(
                    f"[AI] Selected game '{game_name}'. Host must issue !ai start to enable play."
                )

            if command == "start":
                fresh = len(parts) == 3 and parts[2].lower() == "fresh"
                if len(parts) > 2 and not fresh:
                    return self._public("[AI] Use !ai start or !ai start fresh.")
                if not self.state.active_game:
                    return self._public("[AI] Select a game first with !ai game <name>.")
                if fresh:
                    self.state.current_turn = "unknown"
                    self.state.pending_approvals.clear()
                    self._audit("session_start_fresh", {})
                else:
                    self._audit("session_resumed", {})
                self.state.state = "running"
                self.state.pause_reason = ""
                self._persist()
                return self._public(
                    f"[AI] Autonomous play {'started fresh' if fresh else 'started/resumed'} "
                    f"for {self.state.active_game} as Player 2/Blue."
                )

            if command == "pause":
                self.state.state = "paused"
                self.state.pause_reason = "host pause"
                self._persist()
                self._audit("controller_paused", {"reason": self.state.pause_reason})
                return self._public("[AI] Autonomous play paused by the host.")

            if command == "resume":
                self.state.state = "running"
                self.state.pause_reason = ""
                self._persist()
                self._audit("controller_resumed", {})
                return self._public("[AI] Autonomous play resumed by the host.")

            if command == "stop":
                self.state.state = "stopped"
                self.state.pause_reason = "host stop"
                self._audit("controller_stopped", {})
                self._persist()
                return self._public("[AI] Autonomous play stopped by the host.")

            if command == "status":
                self._audit("status_requested", {})
                return self._public(self._status_text())

            if command in {"approve", "reject"}:
                if len(parts) != 3 or not ACTION_ID.fullmatch(parts[2]):
                    return self._public(
                        f"[AI] Use !ai {command} ACTION_ID with a 4-12 character "
                        "alphanumeric action ID."
                    )
                action_id = parts[2]
                proposal = self.state.pending_approvals.pop(action_id, None)
                if proposal is None:
                    return self._public(f"[AI] No pending action uses ID {action_id}.")
                self._audit(
                    f"action_{command}d",
                    {"action_id": action_id, "proposal": proposal},
                )
                execution: dict[str, Any] | None = None
                if command == "approve" and self.approval_executor is not None:
                    try:
                        execution = self.approval_executor(proposal)
                    except Exception as exc:  # approval remains auditable even if TTS fails
                        execution = {"status": "failed", "error": str(exc)}
                self._persist()
                response = self._public(f"[AI] Action {action_id} {command}d by the host.")
                if execution is not None:
                    response["execution"] = execution
                return response

            # `!ai` is also the explicit addressing prefix for ordinary AI
            # requests (for example, "!ai check the state of the board").
            # Only the allowlisted lifecycle commands belong to this
            # controller. Returning None lets the HTTP gateway pass every
            # other `!ai ...` message to the configured AI backend.
            return None
