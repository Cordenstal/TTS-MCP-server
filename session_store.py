from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SessionStore:
    """Small SQLite-backed store for resumable sessions and audit events."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        configured = path or os.getenv("TTS_SESSION_DB", "tts_mcp_sessions.sqlite3")
        self.path = Path(configured).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    save_name TEXT PRIMARY KEY,
                    game_name TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    save_name TEXT,
                    game_name TEXT,
                    turn_number INTEGER,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(save_name) REFERENCES sessions(save_name)
                        ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_session_time
                    ON audit_events(save_name, created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_type_time
                    ON audit_events(event_type, created_at);

                CREATE TABLE IF NOT EXISTS controller_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_aliases (
                    alias TEXT NOT NULL,
                    game_name TEXT NOT NULL DEFAULT '',
                    guid TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(alias, game_name)
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_alias_guid
                    ON semantic_aliases(guid);
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def checkpoint(
        self,
        save_name: str,
        game_name: str,
        state: dict[str, Any],
        *,
        turn_number: int | None = None,
    ) -> dict[str, Any]:
        if not save_name.strip():
            raise ValueError("save_name must not be empty")
        if not game_name.strip():
            raise ValueError("game_name must not be empty")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(save_name, game_name, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(save_name) DO UPDATE SET
                    game_name = excluded.game_name,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (save_name.strip(), game_name.strip(), self._json(state), now, now),
            )
            self._insert_audit(
                connection,
                save_name=save_name.strip(),
                game_name=game_name.strip(),
                turn_number=turn_number,
                event_type="session_checkpoint",
                payload={"state": state},
                created_at=now,
            )
        return self.get_session(save_name) or {}

    def get_session(self, save_name: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE save_name = ?", (save_name.strip(),)
            ).fetchone()
        if row is None:
            return None
        return {
            "save_name": row["save_name"],
            "game_name": row["game_name"],
            "state": json.loads(row["state_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        save_name: str | None = None,
        game_name: str | None = None,
        turn_number: int | None = None,
        created_at: float | None = None,
    ) -> int:
        timestamp = created_at or time.time()
        with self._lock, self._connect() as connection:
            return self._insert_audit(
                connection,
                save_name=save_name,
                game_name=game_name,
                turn_number=turn_number,
                event_type=event_type,
                payload=payload,
                created_at=timestamp,
            )

    def save_controller_state(self, state: dict[str, Any]) -> None:
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO controller_state(id, state_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (self._json(state), now),
            )

    def get_controller_state(self) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, updated_at FROM controller_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return {"state": json.loads(row["state_json"]), "updated_at": row["updated_at"]}

    def save_semantic_alias(
        self,
        alias: str,
        guid: str,
        *,
        game_name: str = "",
        role: str = "",
    ) -> dict[str, Any]:
        alias_key = alias.strip().lower()
        game_key = game_name.strip().lower()
        if not alias_key or not guid.strip():
            raise ValueError("alias and guid must not be empty")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO semantic_aliases(alias, game_name, guid, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias, game_name) DO UPDATE SET
                    guid = excluded.guid,
                    role = excluded.role,
                    updated_at = excluded.updated_at
                """,
                (alias_key, game_key, guid.strip(), role.strip(), now, now),
            )
        return {
            "alias": alias_key,
            "game_name": game_key,
            "guid": guid.strip(),
            "role": role.strip(),
            "updated_at": now,
        }

    def list_semantic_aliases(self, *, game_name: str = "") -> list[dict[str, Any]]:
        game_key = game_name.strip().lower()
        with self._lock, self._connect() as connection:
            if game_key:
                rows = connection.execute(
                    "SELECT * FROM semantic_aliases WHERE game_name IN ('', ?) ORDER BY alias",
                    (game_key,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM semantic_aliases ORDER BY game_name, alias"
                ).fetchall()
        return [dict(row) for row in rows]

    def delete_semantic_alias(self, alias: str, *, game_name: str = "") -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM semantic_aliases WHERE alias = ? AND game_name = ?",
                (alias.strip().lower(), game_name.strip().lower()),
            )
        return cursor.rowcount > 0

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        save_name: str | None,
        game_name: str | None,
        turn_number: int | None,
        event_type: str,
        payload: dict[str, Any],
        created_at: float,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO audit_events(
                save_name, game_name, turn_number, event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                save_name,
                game_name,
                turn_number,
                event_type,
                self._json(payload),
                created_at,
            ),
        )
        return int(cursor.lastrowid)

    def audit_events(
        self,
        *,
        save_name: str = "",
        turn_number: int | None = None,
        event_type: str = "",
        since_unix: float | None = None,
        until_unix: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if save_name.strip():
            clauses.append("save_name = ?")
            values.append(save_name.strip())
        if turn_number is not None:
            clauses.append("turn_number = ?")
            values.append(turn_number)
        if event_type.strip():
            clauses.append("event_type = ?")
            values.append(event_type.strip())
        if since_unix is not None:
            clauses.append("created_at >= ?")
            values.append(since_unix)
        if until_unix is not None:
            clauses.append("created_at <= ?")
            values.append(until_unix)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 1000))
        values.append(safe_limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, save_name, game_name, turn_number, event_type,
                       payload_json, created_at
                FROM audit_events
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "save_name": row["save_name"],
                "game_name": row["game_name"],
                "turn_number": row["turn_number"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
