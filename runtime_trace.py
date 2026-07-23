"""Shared readable and structured runtime tracing for the MCP stack."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any


TRACE_ENABLED = os.getenv("TTS_TRACE", "1").strip().lower() not in {
    "0", "false", "no", "off",
}
TRACE_LOG_PATH = os.getenv(
    "TTS_TRACE_LOG",
    str(Path(__file__).resolve().parent / ".tmp" / "tts_mcp_trace.log"),
)
_trace_path = Path(TRACE_LOG_PATH)
TRACE_JSON_LOG_PATH = os.getenv(
    "TTS_TRACE_JSON_LOG",
    str(_trace_path.with_suffix(".jsonl")),
)
TRACE_LOG = logging.getLogger("tts_mcp.runtime")
TRACE_LOG.setLevel(logging.INFO)
TRACE_LOG.propagate = False

if TRACE_ENABLED and not TRACE_LOG.handlers:
    class _PrettyFormatter(logging.Formatter):
        """Render one structured event as a compact, human-readable block."""

        def format(self, log_record: logging.LogRecord) -> str:
            try:
                event = json.loads(str(log_record.msg))
            except (TypeError, json.JSONDecodeError):
                return str(log_record.msg)

            timestamp = datetime.fromtimestamp(
                float(event.get("at_unix", time.time()))
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            header = (
                f"{timestamp} | {event.get('kind', 'event')}"
                f" | trace={event.get('trace_id', '-') }"
                f" | pid={event.get('pid', '-')}"
                f" thread={event.get('thread', '-') }"
            )
            highlights = []
            for key in ("component", "direction", "action", "tool", "method", "path", "status"):
                if key in event:
                    highlights.append(f"{key}={event[key]}")
            if highlights:
                header += " | " + " ".join(highlights)

            lines = [header]
            for key, value in event.items():
                if key in {
                    "trace_id", "at_unix", "kind", "pid", "ppid", "executable",
                    "argv", "thread", "component", "direction", "action", "tool",
                    "method", "path", "status",
                }:
                    continue
                rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
                lines.append(f"  {key}: {rendered.replace(chr(10), chr(10) + '  ')}")
            return "\n".join(lines)

    pretty_handler = logging.StreamHandler()
    pretty_handler.setFormatter(_PrettyFormatter())
    TRACE_LOG.addHandler(pretty_handler)
    try:
        Path(TRACE_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        pretty_file = RotatingFileHandler(
            TRACE_LOG_PATH,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        pretty_file.setFormatter(_PrettyFormatter())
        TRACE_LOG.addHandler(pretty_file)

        json_file = RotatingFileHandler(
            TRACE_JSON_LOG_PATH,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        json_file.setFormatter(logging.Formatter("%(message)s"))
        TRACE_LOG.addHandler(json_file)
    except OSError:
        # stderr tracing remains available if the configured log is not writable.
        pass


_EVENTS: deque[dict[str, Any]] = deque(maxlen=1000)
_EVENTS_GUARD = threading.Lock()
_REDACTED_KEYS = {
    "authorization", "token", "password", "secret", "api_key", "apikey",
}
_BLOB_KEYS = {"image_base64", "image", "script", "scriptstates", "ui_xml"}


def snapshot(value: Any, depth: int = 0) -> Any:
    """Make a bounded log-safe copy while retaining useful chat text."""
    if depth > 5:
        return "<depth-limited>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            name = str(key)
            lowered = name.lower()
            if lowered in _REDACTED_KEYS or "token" in lowered or "password" in lowered:
                result[name] = "<redacted>"
            elif lowered in _BLOB_KEYS:
                if isinstance(item, (str, bytes, bytearray)):
                    result[name] = {"redacted": True, "length": len(item)}
                else:
                    result[name] = "<redacted>"
            else:
                result[name] = snapshot(item, depth + 1)
        if len(value) > 100:
            result["_truncated_keys"] = len(value) - 100
        return result
    if isinstance(value, (list, tuple)):
        items = [snapshot(item, depth + 1) for item in list(value)[:100]]
        if len(value) > 100:
            items.append(f"<truncated {len(value) - 100} items>")
        return items
    if isinstance(value, bytes):
        return {"length": len(value), "binary": True}
    if isinstance(value, str):
        return value if len(value) <= 12000 else value[:12000] + "...<truncated>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return repr(value)[:12000]


def record(kind: str, *, trace_id: str | None = None, **fields: Any) -> str:
    event_id = trace_id or uuid.uuid4().hex[:12]
    event = {
        "trace_id": event_id,
        "at_unix": time.time(),
        "kind": kind,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "executable": sys.executable,
        "argv": sys.argv[:8],
        "thread": threading.current_thread().name,
        **{key: snapshot(value) for key, value in fields.items()},
    }
    with _EVENTS_GUARD:
        _EVENTS.append(event)
    if TRACE_ENABLED:
        TRACE_LOG.info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    return event_id


def recent(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    with _EVENTS_GUARD:
        return list(_EVENTS)[-safe_limit:]


def pretty_event(event: dict[str, Any]) -> str:
    """Return the same readable representation used by the trace log."""
    timestamp = datetime.fromtimestamp(float(event.get("at_unix", time.time())))
    header = (
        f"{timestamp.astimezone().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
        f" | {event.get('kind', 'event')}"
        f" | trace={event.get('trace_id', '-')}"
        f" | pid={event.get('pid', '-')} thread={event.get('thread', '-')}"
    )
    lines = [header]
    for key, value in event.items():
        if key in {"at_unix", "kind", "trace_id", "pid", "thread"}:
            continue
        rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        lines.append(f"  {key}: {rendered.replace(chr(10), chr(10) + '  ')}")
    return "\n".join(lines)
