"""Shared readable and structured runtime tracing for the MCP stack."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
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


def _clip_console(value: Any, limit: int = 220) -> str:
    """Render a bounded single-line value for the live console."""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _console_detail(value: Any, limit: int = 220) -> str:
    """Render useful structured detail without putting raw JSON on the console."""
    if value is None:
        return "-"
    if isinstance(value, dict):
        if not value:
            return "{}"
        axes = ("x", "y", "z")
        if all(axis in value for axis in axes):
            return "(" + ",".join(_clip_console(value[axis], 24) for axis in axes) + ")"
        parts = []
        for key in (
            "guid", "name", "type", "action", "player", "message", "text", "model",
            "position", "rotation", "bounds", "state_id", "ok", "success",
        ):
            if key in value:
                parts.append(f"{key}={_console_detail(value[key], 80)}")
        if parts:
            return _clip_console(" ".join(parts), limit)
        return f"{len(value)} fields"
    if isinstance(value, (list, tuple)):
        return f"{len(value)} items"
    if isinstance(value, bool):
        return "true" if value else "false"
    return _clip_console(value, limit)


def _console_response_text(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    for key in ("response", "text", "content"):
        content = response.get(key)
        if isinstance(content, str) and content.strip():
            return content
    return ""


def _console_player(value: Any) -> str:
    if not isinstance(value, dict):
        return _clip_console(value, 80)
    identity = value.get("color") or value.get("name") or value.get("steam_name") or "unknown"
    host = ", host" if value.get("host") else ""
    return f"{_clip_console(identity, 60)}{host}"


def console_event(event: dict[str, Any]) -> str:
    """Return a concise human-facing line without dumping event payload JSON."""
    kind = str(event.get("kind", "event"))
    trace_id = str(event.get("trace_id", "-"))
    timestamp = datetime.fromtimestamp(float(event.get("at_unix", time.time()))).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]

    if kind == "ai_message_received":
        detail = f'RECEIVED "{_clip_console(event.get("message", ""))}" from {_console_player(event.get("player", {}))}'
    elif kind == "ai_message_response":
        commands = event.get("commands", [])
        command_count = len(commands) if isinstance(commands, list) else 0
        detail = f'SENT "{_clip_console(event.get("message", ""))}" ({command_count} command(s))'
        if event.get("error"):
            detail += f' error={_clip_console(event["error"], 160)}'
    elif kind == "ai_prompt_built":
        detail = "AI prompt built"
        for key, label in (
            ("message_count", "messages"),
            ("prompt_chars", "prompt_chars"),
            ("gameplay_prompt_chars", "gameplay_chars"),
            ("context_chars", "context_chars"),
            ("object_count", "objects"),
            ("state_in_user_turn", "state_in_user"),
        ):
            if event.get(key) is not None:
                detail += f" {label}={_console_detail(event[key], 40)}"
    elif kind == "ai_request_start":
        payload = event.get("payload", {})
        message = payload.get("message", "") if isinstance(payload, dict) else ""
        conversation = payload.get("conversation_id", "") if isinstance(payload, dict) else ""
        detail = f'AI request "{_clip_console(message)}"'
        if conversation:
            detail += f" conversation={_clip_console(conversation, 80)}"
        if event.get("backend_kind"):
            detail += f' backend={_clip_console(event["backend_kind"], 40)}'
    elif kind == "ai_backend_outbound":
        detail = "AI backend request sent"
        if event.get("backend"):
            detail += f' ({_clip_console(event["backend"], 40)})'
        if event.get("url"):
            detail += f' {_clip_console(event["url"], 100)}'
        request_payload = event.get("payload")
        if isinstance(request_payload, dict):
            if request_payload.get("model"):
                detail += f' model={_clip_console(request_payload["model"], 80)}'
            messages = request_payload.get("messages")
            if isinstance(messages, list):
                detail += f' messages={len(messages)}'
            if request_payload.get("stream") is not None:
                detail += f' stream={_console_detail(request_payload["stream"], 20)}'
        if event.get("message_count") is not None:
            detail += f' messages={_console_detail(event["message_count"], 40)}'
        if event.get("prompt_chars") is not None:
            detail += f' prompt_chars={_console_detail(event["prompt_chars"], 40)}'
        image_attached = event.get("image_attached", event.get("has_image"))
        if image_attached is not None:
            detail += f' image={_console_detail(image_attached, 20)}'
    elif kind == "ai_backend_inbound":
        detail = "AI backend response received"
        if event.get("backend"):
            detail += f' ({_clip_console(event["backend"], 40)})'
        if event.get("status") is not None:
            detail += f' status={_console_detail(event["status"], 30)}'
        response_text = _console_response_text(event.get("response"))
        if response_text:
            detail += f' text="{_clip_console(response_text, 260)}"'
        if isinstance(event.get("response"), dict):
            choices = event["response"].get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    detail += f' finish={_clip_console(finish_reason, 30)}'
    elif kind in {
        "tts_request_start", "tts_request_complete", "tts_request_error", "tts_request_timeout",
        "tts_action_start", "tts_action_complete", "tts_action_error", "tts_action_timeout",
    }:
        action = _clip_console(event.get("action", "unknown"), 60)
        suffix = {
            "tts_request_start": "started",
            "tts_request_complete": "completed",
            "tts_request_error": "failed",
            "tts_request_timeout": "timed out",
            "tts_action_start": "started",
            "tts_action_complete": "completed",
            "tts_action_error": "failed",
            "tts_action_timeout": "timed out",
        }[kind]
        detail = f"TTS action {action} {suffix}"
        if kind in {"tts_request_start", "tts_action_start"} and event.get("args"):
            detail += f' args={_console_detail(event["args"], 180)}'
        if event.get("elapsed_ms") is not None:
            detail += f' elapsed={_console_detail(event["elapsed_ms"], 40)}ms'
        if kind in {"tts_request_complete", "tts_action_complete"} and event.get("result"):
            detail += f' result={_console_detail(event["result"], 180)}'
        if event.get("error"):
            detail += f': {_clip_console(event["error"], 160)}'
    elif kind in {"mcp_tool_start", "mcp_tool_complete", "mcp_tool_error"}:
        tool = _clip_console(event.get("tool", "unknown"), 80)
        suffix = {"mcp_tool_start": "started", "mcp_tool_complete": "completed", "mcp_tool_error": "failed"}[kind]
        detail = f"MCP tool {tool} {suffix}"
        if kind == "mcp_tool_start" and (event.get("args") or event.get("arguments")):
            detail += f' args={_console_detail(event.get("args", event.get("arguments")), 180)}'
        if event.get("elapsed_ms") is not None:
            detail += f' elapsed={_console_detail(event["elapsed_ms"], 40)}ms'
        if kind == "mcp_tool_complete" and event.get("result"):
            detail += f' result={_console_detail(event["result"], 180)}'
        if event.get("error"):
            detail += f': {_clip_console(event["error"], 160)}'
    elif kind == "http_request":
        detail = f"HTTP {_clip_console(event.get('method', ''), 10)} {_clip_console(event.get('path', ''), 120)}"
    elif kind == "http_response":
        detail = f"HTTP response {_clip_console(event.get('status', ''), 20)} {_clip_console(event.get('path', ''), 120)}"
    elif kind == "http_request_payload":
        payload = event.get("payload")
        detail = "HTTP payload received"
        if isinstance(payload, dict) and payload.get("message"):
            detail += f' message="{_clip_console(payload["message"], 220)}"'
        if isinstance(payload, dict) and payload.get("player"):
            detail += f' player={_console_player(payload["player"])}'
    elif kind == "ai_response":
        response = event.get("response")
        detail = "AI gateway response"
        if isinstance(response, dict):
            if response.get("text"):
                detail += f' text="{_clip_console(response["text"], 260)}"'
            commands = response.get("parsed_commands", response.get("commands", []))
            if isinstance(commands, list):
                detail += f' commands={len(commands)}'
    elif kind == "ai_commands_processed":
        commands = event.get("commands", [])
        execution = event.get("execution", {})
        detail = f"AI commands processed count={len(commands) if isinstance(commands, list) else 0}"
        if isinstance(execution, dict):
            for key in ("executed", "blocked", "approval_required"):
                value = execution.get(key)
                if isinstance(value, list):
                    detail += f" {key}={len(value)}"
    elif kind == "ai_scene_objects":
        detail = f"AI scene context objects={_console_detail(event.get('count', 0), 40)}"
        if event.get("game"):
            detail += f' game={_clip_console(event["game"], 60)}'
    elif kind == "ai_vision_capture":
        detail = f"AI vision capture attached={_console_detail(event.get('attached'), 20)}"
        if event.get("bytes") is not None:
            detail += f' bytes={_console_detail(event["bytes"], 40)}'
        if event.get("error"):
            detail += f' error={_clip_console(event["error"], 160)}'
    elif kind == "ai_vision_skipped":
        detail = "AI vision skipped"
        if event.get("reason"):
            detail += f': {_clip_console(event["reason"], 160)}'
    elif kind in {"tts_inbound", "tts_outbound"}:
        direction = "from TTS" if kind == "tts_inbound" else "to TTS"
        detail = f"TTS message {direction} (messageID={_clip_console(event.get('message_id', '?'), 20)})"
        if event.get("action"):
            detail += f' action={_clip_console(event["action"], 60)}'
        if event.get("message"):
            detail += f' text="{_clip_console(event["message"], 220)}"'
    elif kind == "tts_lua_error":
        detail = "TTS Lua error"
        if event.get("prefix"):
            detail += f' prefix="{_clip_console(event["prefix"], 160)}"'
        if event.get("guid"):
            detail += f' guid={_clip_console(event["guid"], 80)}'
        if event.get("error"):
            detail += f' error="{_clip_console(event["error"], 12000)}"'
    elif kind in {"chat_message", "tts_print"}:
        detail = f"TTS {kind.replace('_', ' ')}"
        value = event.get("message") or event.get("text") or event.get("printed")
        if value:
            detail += f' text="{_clip_console(value, 12000)}"'
    elif kind == "process_start":
        detail = f"Process started ({_clip_console(event.get('mode', ''), 40)})"
    elif kind == "process_stop":
        detail = "Process stopped"
    else:
        detail = ""
        for key in ("component", "action", "tool", "direction", "status", "error"):
            value = event.get(key)
            if value not in (None, "", [], {}):
                detail = f"{key}={_clip_console(value, 120)}"
                break

    line = f"{timestamp} | {kind} | trace={trace_id}"
    return f"{line} | {detail}" if detail else line


class _ConsoleFormatter(logging.Formatter):
    def format(self, log_record: logging.LogRecord) -> str:
        try:
            event = json.loads(str(log_record.msg))
        except (TypeError, json.JSONDecodeError):
            return str(log_record.msg)
        return console_event(event)


class _NonBlockingConsoleHandler(logging.StreamHandler):
    """Drop console sink errors without aborting later trace handlers."""

    def handleError(self, record: logging.LogRecord) -> None:
        # A gateway launched from a temporary shell can outlive stderr. The
        # standard handler may write its own diagnostic to that same closed
        # stream, raising again before file handlers receive the record.
        return


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

    pretty_handler = _NonBlockingConsoleHandler()
    pretty_handler.setFormatter(_ConsoleFormatter())
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


# Trace handlers may write to a log file shared by a recently restarted server.
# On Windows, rotation or an antivirus/file-indexing lock can stall that write.
# Application threads must never wait for diagnostic output before serving TTS
# or HTTP traffic, so a single daemon worker owns the potentially blocking I/O.
_TRACE_QUEUE: queue.Queue[str] = queue.Queue(maxsize=4096)


def _trace_writer() -> None:
    while True:
        message = _TRACE_QUEUE.get()
        try:
            TRACE_LOG.info(message)
        except Exception:
            # Tracing is diagnostic only. Keep the bridge responsive if a
            # handler or rotating log file is temporarily unavailable.
            pass
        finally:
            _TRACE_QUEUE.task_done()


if TRACE_ENABLED:
    _TRACE_WRITER_THREAD = threading.Thread(
        target=_trace_writer,
        name="tts-runtime-trace-writer",
        daemon=True,
    )
    _TRACE_WRITER_THREAD.start()


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
        try:
            _TRACE_QUEUE.put_nowait(
                json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            )
        except queue.Full:
            # Preserve the live bridge over exhaustive diagnostics. The in
            # memory recent-event buffer above remains available.
            pass
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
