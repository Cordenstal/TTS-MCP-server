from __future__ import annotations

import json
import hmac
import os
import queue
import re
import shlex
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_controller import AIController
from session_store import SessionStore
from runtime_trace import record as _record_trace
from gameplay_runtime import (
    CatalogIndex,
    CommandExecution,
    GamePromptBuilder,
    ParsedCommand,
    ScenePlacementIntelligence,
    classify_intent,
    parse_ai_commands,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _admin_token() -> str:
    return os.getenv("TTS_ADMIN_TOKEN", "").strip()


def _authorized_admin(handler: BaseHTTPRequestHandler) -> bool:
    """Require a bearer token for all stateful/admin gateway operations."""
    expected = _admin_token()
    supplied = handler.headers.get("Authorization", "")
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _require_admin(handler: BaseHTTPRequestHandler) -> bool:
    if _authorized_admin(handler):
        return True
    _json_response(handler, 401, {"error": "admin authentication required"})
    return False


def _require_transport_auth(handler: BaseHTTPRequestHandler) -> bool:
    """Authenticate requests when the gateway has deliberately left localhost."""
    host = getattr(handler.server, "server_address", ("127.0.0.1",))[0]
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    expected = os.getenv("TTS_HTTP_AUTH_TOKEN", "").strip()
    supplied = handler.headers.get("Authorization", "")
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if expected and hmac.compare_digest(supplied, expected):
        return True
    _json_response(handler, 401, {"error": "HTTP authentication required"})
    return False


def _command_allowed(command: str) -> bool:
    """Allow only explicitly named backend executables when CLI mode is enabled."""
    try:
        argv = shlex.split(command, posix=False)
    except ValueError:
        return False
    if not argv:
        return False
    allowed = {
        item.strip().lower()
        for item in os.getenv("TTS_ALLOWED_BACKEND_EXECUTABLES", "").split(",")
        if item.strip()
    }
    executable = Path(argv[0]).name.lower()
    return bool(allowed) and executable in allowed


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    _record_trace(
        "http_response",
        direction="gateway_to_client",
        method=getattr(handler, "command", ""),
        path=getattr(handler, "path", ""),
        status=status,
        payload=payload,
    )
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


ADMIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TTS AI Backend</title><style>
body{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#111827;color:#e5e7eb}
section{background:#1f2937;border:1px solid #374151;border-radius:10px;padding:1rem;margin:1rem 0}
label{display:block;margin:.7rem 0 .25rem;color:#cbd5e1}input,select,textarea{width:100%;box-sizing:border-box;padding:.55rem;background:#111827;color:#f9fafb;border:1px solid #4b5563;border-radius:6px}textarea{min-height:150px;font-family:inherit}
button{padding:.55rem .8rem;margin:.5rem .4rem .2rem 0;border:0;border-radius:6px;background:#2563eb;color:white;cursor:pointer}button.danger{background:#b91c1c}button.secondary{background:#4b5563}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.muted{color:#9ca3af}.status{padding:.7rem;background:#111827;border-radius:6px;white-space:pre-wrap}.conversation{border-top:1px solid #374151;padding:.7rem 0}.msg{padding:.45rem;margin:.35rem 0;background:#111827;border-radius:5px}.role{color:#93c5fd;font-weight:600}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body><h1>TTS AI Backend</h1>
<p class="muted">Local control panel. It manages AI servicing; the MCP/TTS bridge remains connected.</p>
<section><h2>Server</h2><div id="status" class="status">Loading...</div><button onclick="server('start')">Start</button><button onclick="server('restart')">Restart</button><button class="danger" onclick="server('stop')">Stop AI</button></section>
<section><h2>Backend configuration</h2><div class="grid"><div><label>Backend kind</label><select id="kind"><option value="http">HTTP / OpenAI-compatible</option><option value="command">Local CLI command</option><option value="queue">Queue for MCP/Codex</option></select><label>Backend URL</label><input id="url" placeholder="http://127.0.0.1:11434/api/chat"><label>Command</label><input id="command" placeholder="ollama run llama3.2"><label>Model</label><input id="model" list="modelOptions" placeholder="Select or type a model"><datalist id="modelOptions"></datalist><button class="secondary" onclick="models()">Discover Ollama models</button><span id="models" class="muted"></span></div><div><label>Request format</label><select id="format"><option value="ollama">Ollama native chat (vision)</option><option value="openai">OpenAI chat completions</option><option value="generic">Generic JSON</option></select><label>Timeout seconds</label><input id="timeout" type="number" min="1"><label>Observation tool calls per turn</label><input id="observationCalls" type="number" min="1" max="20"><label>Observation/review timeout seconds</label><input id="observationTimeout" type="number" min="1" max="300"><label>Ollama keep-alive</label><input id="keepAlive" placeholder="30m"><label>Bearer token (leave blank to keep current)</label><input id="token" type="password"><label><input id="echo" type="checkbox" style="width:auto"> Echo mode</label><label><input id="vision" type="checkbox" style="width:auto"> Legacy move-preparation screenshots</label></div></div><label>System prompt</label><textarea id="prompt" placeholder="Stable instructions for the AI player..."></textarea><button onclick="save()">Save and apply</button><span id="saveResult" class="muted"></span></section>
<section><h2>Conversation log</h2><button class="secondary" onclick="loadConversations()">Refresh</button><div id="conversations"></div></section>
<script>
const $=id=>document.getElementById(id); const adminToken=prompt('TTS admin token (TTS_ADMIN_TOKEN):')||''; const json=async(url,opt={})=>{opt.headers={...(opt.headers||{}),Authorization:'Bearer '+adminToken};let r=await fetch(url,opt);let d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d};
async function refresh(){let d=await json('/admin/api/status');$('status').textContent=JSON.stringify(d,null,2);let c=d.config;$('kind').value=c.kind||'queue';$('url').value=c.url||'';$('command').value=c.command||'';$('model').value=c.model||'';$('format').value=c.format||'openai';$('timeout').value=c.timeout||60;$('observationCalls').value=c.observation_max_calls||4;$('observationTimeout').value=c.observation_timeout||15;$('keepAlive').value=c.ollama_keep_alive||'30m';$('echo').checked=!!c.echo;$('vision').checked=c.vision!==false;$('prompt').value=c.system_prompt||'';}
async function server(action){try{await json('/admin/api/server/'+action,{method:'POST'});await refresh()}catch(e){alert(e)}}
async function save(){let b={kind:$('kind').value,url:$('url').value,command:$('command').value,model:$('model').value,format:$('format').value,timeout:Number($('timeout').value),observation_max_calls:Number($('observationCalls').value),observation_timeout:Number($('observationTimeout').value),ollama_keep_alive:$('keepAlive').value,echo:$('echo').checked,vision:$('vision').checked,system_prompt:$('prompt').value};try{await json('/admin/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});$('saveResult').textContent='Saved and applied';await refresh()}catch(e){$('saveResult').textContent=e}}
async function models(){try{let d=await json('/admin/api/models');let opts=$('modelOptions');opts.innerHTML='';(d.models||[]).forEach(m=>{let o=document.createElement('option');o.value=m;opts.appendChild(o)});$('models').textContent=(d.models||[]).length+' model(s) found'+(d.source?' from '+d.source:'')}catch(e){$('models').textContent=e}}
async function loadConversations(){let d=await json('/admin/api/conversations');$('conversations').innerHTML=(d.conversations||[]).map(c=>`<div class="conversation"><button class="secondary" onclick="showConversation('${encodeURIComponent(c.conversation_id)}')">View</button><button class="danger" onclick="resetConversation('${encodeURIComponent(c.conversation_id)}')">Reset</button> <b>${c.conversation_id}</b><span class="muted"> — ${c.message_count} messages</span><div id="c-${encodeURIComponent(c.conversation_id)}"></div></div>`).join('')||'<p class="muted">No conversations yet.</p>'}
async function showConversation(id){let d=await json('/admin/api/conversations/'+id);$('c-'+id).innerHTML=(d.messages||[]).map(m=>`<div class="msg"><span class="role">${m.role}</span>: ${String(m.content).replaceAll('<','&lt;')}</div>`).join('')}
async function resetConversation(id){if(confirm('Reset this conversation?')){await json('/admin/api/conversations/'+id,{method:'DELETE'});loadConversations()}}
refresh();loadConversations();setInterval(refresh,10000);
</script></body></html>"""


class BackendConfigStore:
    """JSON-backed settings that can be edited without restarting the bridge."""

    def __init__(self) -> None:
        configured = os.getenv("TTS_BACKEND_CONFIG", "").strip()
        self.path = (
            Path(configured).expanduser().resolve()
            if configured
            else Path(__file__).resolve().parent / "tts_mcp_backend.local.json"
        )
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                # Keep the checked-in JSON as a non-secret starter template;
                # all saved credentials/configuration go to the ignored file.
                template = self.path.with_name("tts_mcp_backend.json")
                try:
                    value = json.loads(template.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    return {}
        return value if isinstance(value, dict) else {}

    def save(self, value: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    for key in ("text", "response", "output"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    if isinstance(message, str):
        return message

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            if isinstance(first.get("text"), str):
                return first["text"]
            choice_message = first.get("message")
            if isinstance(choice_message, dict) and isinstance(
                choice_message.get("content"), str
            ):
                return choice_message["content"]
    if isinstance(payload.get("content"), list):
        parts = [
            item.get("text", "")
            for item in payload["content"]
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if parts:
            return "".join(parts)
    return ""


def _response_was_truncated(payload: Any) -> bool:
    """Return whether a backend ended generation before producing an answer."""
    if not isinstance(payload, dict):
        return False
    reasons = [payload.get("done_reason"), payload.get("finish_reason")]
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reasons.append(choices[0].get("finish_reason"))
    return any(str(reason or "").strip().lower() in {"length", "max_tokens", "max_token", "length_limit"} for reason in reasons)


def _public_ai_text(text: str) -> str:
    """Return only concise, non-empty natural-language player chat."""
    candidate = str(text or "").strip()
    if not candidate:
        return ""
    # The HTTP gateway itself uses JSON, but JSON must never become player
    # chat. Reject a complete object/array response before line filtering so
    # multi-line serialized payloads cannot leak through one row at a time.
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, (dict, list)):
        return ""

    cleaned = re.sub(
        r"(?im)^\s*(?:MOVE|ROTATE|LOCK|UNLOCK|SPAWN|PLACE|SPAWN_BUILTIN|BROADCAST|DESTROY)\[[^\]\r\n]*\]\s*$",
        "",
        text,
    )
    public_lines: list[str] = []
    internal_headers = (
        "authoritative current context:",
        "current tabletop simulator state:",
        "relevant scene/catalog candidates:",
        "all live top-level table objects:",
        "tagged board objects:",
    )
    for line in cleaned.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if any(lowered.startswith(header) for header in internal_headers):
            continue
        # Remove raw JSON/object rows and markdown table rows that expose the
        # internal board inventory. Natural-language conclusions remain.
        is_json_row = (
            (stripped.startswith("{") and stripped.endswith("}"))
            or (stripped.startswith("[") and stripped.endswith("]"))
            or ("\"guid\"" in lowered and "\"position\"" in lowered)
            or ("\"rotation\"" in lowered and "\"bounds\"" in lowered)
        )
        is_state_row = bool(
            re.match(r"^(?:guid|position|rotation|bounds|zone_guids|smooth_moving|locked|tags)\s*[:=]", lowered)
            or (
                "position" in lowered
                and "rotation" in lowered
                and ("guid" in lowered or "piece" in lowered or "pawn" in lowered or "king" in lowered)
            )
        )
        is_state_table = "guid" in lowered and "position" in lowered and "rotation" in lowered
        if is_json_row or is_state_row or is_state_table:
            continue
        # Keep chat readable even when a backend pads a line with tabs or a
        # large run of spaces. TTS renders those characters literally.
        public_lines.append(re.sub(r"[^\S\r\n]+", " ", stripped))

    result = "\n".join(public_lines).strip()
    if not result:
        return ""
    # Prevent an accidentally echoed long state dump from becoming a chat
    # flood even if it is formatted as prose rather than JSON.
    if len(result) > 2000:
        result = result[:1997].rstrip() + "..."
    return result


OBSERVATION_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "tts_get_object",
            "description": "Get one visible TTS object by its exact GUID.",
            "parameters": {"type": "object", "properties": {"guid": {"type": "string"}}, "required": ["guid"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_list_objects",
            "description": "List visible TTS objects with exact GUIDs, names, tags, transforms, bounds, and lock state.",
            "parameters": {"type": "object", "properties": {
                "name_contains": {"type": "string"},
                "tag": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
                "compact": {"type": "boolean"},
            }},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_search_scene",
            "description": "Search visible scene objects by name, tag, type, description, or GUID.",
            "parameters": {"type": "object", "properties": {
                "reference": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            }, "required": ["reference"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_find_nearest_objects",
            "description": "Find visible objects nearest a world point or reference GUID.",
            "parameters": {"type": "object", "properties": {
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
                "reference_guid": {"type": "string"}, "name_contains": {"type": "string"},
                "tag": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            }},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_find_objects_in_region",
            "description": "Find visible objects whose bounds intersect an axis-aligned world region.",
            "parameters": {"type": "object", "properties": {
                "minimum_x": {"type": "number"}, "minimum_y": {"type": "number"}, "minimum_z": {"type": "number"},
                "maximum_x": {"type": "number"}, "maximum_y": {"type": "number"}, "maximum_z": {"type": "number"},
                "name_contains": {"type": "string"}, "tag": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            }, "required": ["minimum_x", "minimum_y", "minimum_z", "maximum_x", "maximum_y", "maximum_z"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_get_zone_objects",
            "description": "List visible objects currently occupying a scripting zone.",
            "parameters": {"type": "object", "properties": {
                "guid": {"type": "string"}, "ignore_tags": {"type": "boolean"},
            }, "required": ["guid"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_get_scene_summary",
            "description": "Return a bounded compact summary of visible top-level scene objects; use only when targeted lookup is insufficient.",
            "parameters": {"type": "object", "properties": {
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            }},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_capture_view",
            "description": "Capture the current visible TTS view without moving the camera.",
            "parameters": {"type": "object", "properties": {
                "left": {"type": "integer"}, "top": {"type": "integer"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
                "max_width": {"type": "integer"}, "jpeg_quality": {"type": "integer"},
            }},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_capture_view_info",
            "description": "Capture the current TTS view and return only geometry and blank-frame health metadata.",
            "parameters": {"type": "object", "properties": {
                "left": {"type": "integer"}, "top": {"type": "integer"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
                "max_width": {"type": "integer"},
            }},
        },
    },
]
OBSERVATION_TOOL_NAMES = {
    item["function"]["name"] for item in OBSERVATION_TOOL_SPECS
}
VISUAL_OBSERVATION_TOOL_NAMES = {"tts_capture_view", "tts_capture_view_info"}
_TOOL_BLOB_KEYS = {"script", "scriptstates", "ui_xml", "raw", "logs"}


def _compact_tool_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[depth limit]"
    if isinstance(value, dict):
        return {
            str(key): item if str(key) == "image_base64" and isinstance(item, str) else _compact_tool_value(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
            if str(key).lower() not in _TOOL_BLOB_KEYS
        }
    if isinstance(value, list):
        return [_compact_tool_value(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:2000]
    return str(value)[:500]


def _checkers_legal_black_moves(
    pieces: list[dict[str, Any]], squares: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Derive exact, executable Black move candidates from visible board state.

    A capture candidate is a complete bounded game action: the executor moves
    the selected black checker and removes the verified jumped red checker.
    """
    if not pieces or not squares:
        return [], False
    x_values = sorted({float(square["x"]) for square in squares})
    z_values = sorted({float(square["z"]) for square in squares})
    by_coordinate = {
        (round(float(square["x"]), 6), round(float(square["z"]), 6)): square
        for square in squares
    }
    if len(x_values) < 2 or len(z_values) < 2:
        return [], False

    square_spacing = min(
        min(second - first for first, second in zip(x_values, x_values[1:])),
        min(second - first for first, second in zip(z_values, z_values[1:])),
    )
    # Captured checkers remain in the scene but are stored beyond the board.
    # They must not be snapped back to an edge square merely because it is the
    # nearest tagged zone. Keep a tolerance for ordinary physics drift while
    # excluding the off-board holding rows.
    board_tolerance = max(0.5, square_spacing * 0.35)

    def nearest(values: list[float], value: float) -> int:
        return min(range(len(values)), key=lambda index: abs(values[index] - value))

    def square_at(file_index: int, rank_index: int) -> dict[str, Any] | None:
        if not (0 <= file_index < len(x_values) and 0 <= rank_index < len(z_values)):
            return None
        return by_coordinate.get((round(x_values[file_index], 6), round(z_values[rank_index], 6)))

    for piece in pieces:
        position = piece.get("position") or {}
        try:
            x, z = float(position["x"]), float(position["z"])
            file_index = nearest(x_values, x)
            rank_index = nearest(z_values, z)
            nearest_x, nearest_z = x_values[file_index], z_values[rank_index]
            if ((x - nearest_x) ** 2 + (z - nearest_z) ** 2) ** 0.5 > board_tolerance:
                piece["_file"] = -1
                piece["_rank"] = -1
            else:
                piece["_file"] = file_index
                piece["_rank"] = rank_index
        except (KeyError, TypeError, ValueError):
            piece["_file"] = -1
            piece["_rank"] = -1
    occupied: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for piece in pieces:
        location = (int(piece["_file"]), int(piece["_rank"]))
        if location[0] >= 0 and location[1] >= 0:
            occupied.setdefault(location, []).append(piece)

    # A crowned king is represented by two vertically stacked Checker
    # objects. Only the lower piece is a movable source; the upper piece is
    # its marker and must not create duplicate legal moves.
    movable_piece_guids: set[str] = set()
    for stack in occupied.values():
        base = min(
            stack,
            key=lambda piece: float((piece.get("position") or {}).get("y", 0)),
        )
        movable_piece_guids.add(str(base.get("guid") or "").lower())

    def color(piece: dict[str, Any]) -> str:
        return str(piece.get("_identity", "")).lower()

    def candidate(piece: dict[str, Any], target: dict[str, Any], *, kind: str) -> dict[str, Any]:
        target_position = target["position"]
        source_position = piece["position"]
        return {
            "guid": piece.get("guid"),
            "from": piece.get("_square_tag", ""),
            "target": {
                "tag": target["tag"],
                "x": target_position["x"],
                "y": source_position["y"],
                "z": target_position["z"],
            },
            "kind": kind,
        }

    for piece in pieces:
        source = square_at(int(piece["_file"]), int(piece["_rank"]))
        piece["_square_tag"] = source["tag"] if source else ""

    captures: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for piece in pieces:
        if "black" not in color(piece):
            continue
        if str(piece.get("guid") or "").lower() not in movable_piece_guids:
            continue
        file_index, rank_index = int(piece["_file"]), int(piece["_rank"])
        if file_index < 0 or rank_index < 0:
            continue
        is_king = len(occupied.get((file_index, rank_index), [])) > 1
        rank_directions = (-1, 1) if is_king else (-1,)
        for rank_delta in rank_directions:
            for file_delta in (-1, 1):
                adjacent = (file_index + file_delta, rank_index + rank_delta)
                landing = (file_index + 2 * file_delta, rank_index + 2 * rank_delta)
                adjacent_pieces = occupied.get(adjacent, [])
                landing_square = square_at(*landing)
                if landing_square and not occupied.get(landing) and any("red" in color(item) for item in adjacent_pieces):
                    captures.append(candidate(piece, landing_square, kind="capture"))
                target_square = square_at(*adjacent)
                if target_square and not adjacent_pieces:
                    steps.append(candidate(piece, target_square, kind="step"))
    return (captures, True) if captures else (steps, False)


def _checkers_board_observation(value: dict[str, Any]) -> dict[str, Any] | None:
    """Return the small, complete board view a checkers model actually needs.

    A raw TTS object list includes physics, bounds, transforms and hands for
    every table object.  It is both too large for a local model and, when the
    generic 50-item cap applies, can omit the destination squares.  Preserve
    all live checkers and every canonical square instead.
    """
    objects = value.get("objects")
    if not isinstance(objects, list):
        return None
    pieces: list[dict[str, Any]] = []
    squares: list[dict[str, Any]] = []
    legal_piece_records: list[dict[str, Any]] = []
    legal_square_records: list[dict[str, Any]] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        tags = [str(tag).strip() for tag in obj.get("tags", []) if str(tag).strip()]
        direct_tag = str(obj.get("tag", "")).strip()
        if direct_tag:
            tags.append(direct_tag)
        position = obj.get("position") if isinstance(obj.get("position"), dict) else {}
        compact_position = {
            axis: position[axis]
            for axis in ("x", "y", "z")
            if axis in position
        }
        identity = " ".join((
            str(obj.get("name", "")), str(obj.get("type", "")), " ".join(tags),
        )).lower()
        if "checker" in identity:
            legal_piece_records.append({
                "guid": obj.get("guid"), "position": compact_position, "_identity": identity,
            })
            pieces.append({
                "guid": obj.get("guid"),
                "name": obj.get("name"),
                "position": compact_position,
                "locked": obj.get("locked"),
                "tags": tags,
            })
        square_tags = [tag.upper() for tag in tags if re.fullmatch(r"[A-H][1-8]", tag, re.I)]
        for tag in square_tags:
            if "x" in compact_position and "z" in compact_position:
                legal_square_records.append({
                    "tag": tag,
                    "position": {"x": compact_position["x"], "z": compact_position["z"]},
                    "x": compact_position["x"], "z": compact_position["z"],
                })
            squares.append({
                "tag": tag,
                "position": {axis: compact_position[axis] for axis in ("x", "z") if axis in compact_position},
            })
    if not pieces and not squares:
        return None
    squares.sort(key=lambda item: (int(item["tag"][1]), item["tag"][0]))
    legal_moves, mandatory_capture = _checkers_legal_black_moves(legal_piece_records, legal_square_records)
    return {
        "ok": bool(value.get("ok", True)),
        "count": value.get("count", len(objects)),
        "checkers": {
            "pieces": pieces,
            "squares": squares,
            "legal_black_moves": legal_moves,
            "mandatory_capture_required": mandatory_capture,
        },
        "truncated": bool(value.get("truncated", False)),
    }


class ChatHistoryStore:
    """Persistent, bounded conversation history for the AI gateway."""

    def __init__(self) -> None:
        self.path = os.getenv("AI_CHAT_HISTORY_DB", os.getenv("TTS_SESSION_DB", "tts_mcp_sessions.sqlite3"))
        self.limit = max(2, min(int(os.getenv("AI_CHAT_HISTORY_TURNS", "12")), 100))
        self._lock = threading.RLock()
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_conversation "
                "ON ai_chat_messages(conversation_id, id)"
            )

    def messages(self, conversation_id: str) -> list[dict[str, str]]:
        with self._lock, sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT role, content FROM ai_chat_messages "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, self.limit),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def append(self, conversation_id: str, messages: list[dict[str, str]]) -> None:
        now = time.time()
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.executemany(
                "INSERT INTO ai_chat_messages(conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                [(conversation_id, item["role"], item["content"], now) for item in messages],
            )
            connection.execute(
                "DELETE FROM ai_chat_messages WHERE conversation_id = ? AND id NOT IN "
                "(SELECT id FROM ai_chat_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?)",
                (conversation_id, conversation_id, self.limit),
            )

    def reset(self, conversation_id: str) -> None:
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                "DELETE FROM ai_chat_messages WHERE conversation_id = ?", (conversation_id,)
            )

    def conversations(self) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT conversation_id, COUNT(*), MAX(created_at) "
                "FROM ai_chat_messages GROUP BY conversation_id ORDER BY MAX(created_at) DESC"
            ).fetchall()
        return [{"conversation_id": row[0], "message_count": row[1], "last_message_at": row[2]} for row in rows]


class ChatBackend:
    def __init__(self) -> None:
        self.config_store = BackendConfigStore()
        self._config_lock = threading.RLock()
        self.enabled = True
        self.history = ChatHistoryStore()
        self.context_provider: Callable[[], dict[str, Any]] | None = None
        self.observation_tools: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self.controller_provider: Callable[[], dict[str, Any]] | None = None
        self.command_execution: CommandExecution | None = None
        self._turn_lock = threading.RLock()
        self._context_local = threading.local()
        catalog_path = os.getenv("TTS_OBJECT_CATALOG", "").strip()
        # Do not implicitly import or discover the former V6 catalog. Scene
        # awareness comes exclusively from live TTS objects and screenshots.
        self.catalog = CatalogIndex(catalog_path or None)
        self.prompt_builder = GamePromptBuilder(Path(__file__).resolve().parent / "game_rules", self.catalog)
        self.scene_intelligence = ScenePlacementIntelligence(self.catalog)
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        self.reload(self.config_store.load())

    def configure_gameplay(
        self,
        *,
        controller_provider: Callable[[], dict[str, Any]],
        request: Callable[[str, dict[str, Any]], dict[str, Any]],
        propose: Callable[[dict[str, Any]], str],
    ) -> None:
        self.controller_provider = controller_provider
        self.command_execution = CommandExecution(
            request,
            propose,
            review=self._review_execution_failure,
        )

    def configure_observation_tools(
        self, tools: dict[str, Callable[[dict[str, Any]], Any]]
    ) -> None:
        """Attach the explicitly allowlisted, read-only TTS observations."""
        unknown = set(tools) - OBSERVATION_TOOL_NAMES
        if unknown:
            raise ValueError(f"unknown observation tools: {', '.join(sorted(unknown))}")
        self.observation_tools = dict(tools)

    def _gameplay_context(self, payload: dict[str, Any], message: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        intent = classify_intent(message)
        # Ordinary chat starts context-light. Live scene evidence is acquired
        # only through the bounded read-only tool loop below.
        context: dict[str, Any] = {}
        controller = self.controller_provider() if self.controller_provider else {}
        game = str(controller.get("active_game", ""))
        prompt = self.prompt_builder.build(game=game, intent=intent, context=context)
        return prompt, context, [{"intent": intent.value, "game": game}]

    @staticmethod
    def _observation_instructions() -> str:
        return (
            "Live TTS scene data is not included automatically. For a move, first use tts_list_objects for exact "
            "GUIDs, tags, transforms, and occupancy. Use tts_capture_view when board orientation, appearance, "
            "stacking, occupancy, or other visual evidence is needed; it captures the current view without moving "
            "the camera and returns an image to the model. Image review is expensive: request at most one "
            "successful screenshot per turn, and only after structured observations leave a genuinely visual question "
            "unresolved. If a capture fails or returns no image, it does not consume the visual budget. A post-move "
            "position discrepancy greater than 0.5 world units on any axis requires visual review. Never guess a "
            "GUID, coordinate, or visual fact. Screenshots do not prove exact transforms. If any action or "
            "verification fails, stop issuing actions and wait for player instructions. "
            "For checkers, tts_list_objects returns checkers.legal_black_moves. Select exactly one listed step "
            "and copy its guid and target x/y/z into MOVE; never invent a different source or destination. "
            "When that list is non-empty, it already resolves occupancy and geometry, so do not request a screenshot "
            "before selecting one of those moves. "
            "If mandatory_capture_required is true, select exactly one listed capture MOVE. The server validates "
            "the jumped red checker and removes it only after the move is verified. "
            "Tool calls and raw results are internal; answer "
            "players with concise natural language only. For backends without native tool calling, emit exactly "
            "one JSON object of the form "
            '{"tool_call":{"name":"tts_search_scene","arguments":{"reference":"..."}}}.'
        )

    @staticmethod
    def _validate_observation_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if not isinstance(call, dict):
            raise ValueError("tool call must be an object")
        name = str(call.get("name", "")).strip()
        if name not in OBSERVATION_TOOL_NAMES:
            raise ValueError(f"tool is not allowlisted: {name or '<missing>'}")
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"tool arguments are not valid JSON: {exc}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        bounded = dict(arguments)
        allowed_arguments = {
            "tts_get_object": {"guid"},
            "tts_list_objects": {"name_contains", "tag", "max_results", "compact"},
            "tts_search_scene": {"reference", "max_results"},
            "tts_find_nearest_objects": {"x", "y", "z", "reference_guid", "name_contains", "tag", "max_results"},
            "tts_find_objects_in_region": {"minimum_x", "minimum_y", "minimum_z", "maximum_x", "maximum_y", "maximum_z", "name_contains", "tag", "max_results"},
            "tts_get_zone_objects": {"guid", "ignore_tags"},
            "tts_get_scene_summary": {"max_results"},
            "tts_capture_view": {"left", "top", "width", "height", "max_width", "jpeg_quality"},
            "tts_capture_view_info": {"left", "top", "width", "height", "max_width"},
        }[name]
        unknown_arguments = set(bounded) - allowed_arguments
        if unknown_arguments:
            raise ValueError(f"unsupported arguments for {name}: {', '.join(sorted(unknown_arguments))}")
        if name == "tts_get_object" or name == "tts_get_zone_objects":
            key = "guid"
            if not str(bounded.get(key, "")).strip():
                raise ValueError(f"{name} requires guid")
        if name == "tts_search_scene" and not str(bounded.get("reference", "")).strip():
            raise ValueError("tts_search_scene requires reference")
        if name == "tts_list_objects":
            bounded["max_results"] = max(1, min(int(bounded.get("max_results", 200)), 1000))
            bounded["compact"] = bool(bounded.get("compact", True))
        if name == "tts_get_scene_summary":
            bounded["max_results"] = max(1, min(int(bounded.get("max_results", 50)), 50))
        if name in {"tts_search_scene", "tts_find_nearest_objects", "tts_find_objects_in_region"}:
            bounded["max_results"] = max(1, min(int(bounded.get("max_results", 10)), 50))
        if name == "tts_find_nearest_objects" and not str(bounded.get("reference_guid", "")).strip():
            if any(axis not in bounded for axis in ("x", "y", "z")):
                raise ValueError("tts_find_nearest_objects requires reference_guid or x, y, and z")
        if name in {"tts_capture_view", "tts_capture_view_info"}:
            bounded["left"] = max(-10000, min(int(bounded.get("left", 0)), 10000))
            bounded["top"] = max(-10000, min(int(bounded.get("top", 0)), 10000))
            bounded["width"] = max(1, min(int(bounded.get("width", 1920)), 3840))
            bounded["height"] = max(1, min(int(bounded.get("height", 1080)), 2160))
            bounded["max_width"] = max(1, min(int(bounded.get("max_width", 1600)), 2000))
        if name == "tts_capture_view":
            bounded["jpeg_quality"] = max(30, min(int(bounded.get("jpeg_quality", 85)), 95))
        return name, bounded

    def _invoke_observation(self, call: dict[str, Any]) -> dict[str, Any]:
        name, arguments = self._validate_observation_call(call)
        callback = self.observation_tools.get(name)
        if callback is None:
            return {"ok": False, "error": "observation tools are unavailable this turn"}
        try:
            result = callback(arguments)
            if not isinstance(result, dict):
                result = {"value": result}
            controller = self.controller_provider() if self.controller_provider else {}
            if name == "tts_list_objects" and str(controller.get("active_game", "")).strip().lower() == "checkers":
                checkers_board = _checkers_board_observation(result)
                if checkers_board is not None:
                    return checkers_board
            compact = _compact_tool_value(result)
            if not isinstance(compact, dict):
                compact = {"value": compact}
            compact.setdefault("ok", True)
            return compact
        except Exception as exc:
            return {"ok": False, "error": f"{name} failed: {str(exc)[:300]}"}

    def _invoke_observation_with_image_budget(
        self,
        call: dict[str, Any],
        image_count: int,
    ) -> tuple[dict[str, Any], int]:
        name = str(call.get("name", ""))
        if name in VISUAL_OBSERVATION_TOOL_NAMES:
            if image_count >= 1:
                return {
                    "ok": False,
                    "error": "image review budget exhausted; one screenshot is allowed per turn",
                }, image_count
            result = self._invoke_observation(call)
            # A failed or empty capture must not consume the one-image budget;
            # the model may still retry the visual observation once with a
            # corrected rectangle or after TTS rendering recovers.
            if result.get("ok") is True and isinstance(result.get("image_base64"), str) and result["image_base64"]:
                return result, image_count + 1
            return result, image_count
        return self._invoke_observation(call), image_count

    @staticmethod
    def _observation_failure_report() -> str:
        """Describe an observation failure without guessing its infrastructure cause."""
        return (
            "I couldn't inspect the board because a live observation tool failed. "
            "I won't assume the Lua bridge is missing. Please provide further instructions or ask me to retry."
        )

    @staticmethod
    def _extract_tool_calls(payload: Any) -> list[dict[str, Any]]:
        message: Any = None
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
            if message is None:
                message = payload.get("message")
        if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
            calls: list[dict[str, Any]] = []
            for item in message["tool_calls"]:
                if not isinstance(item, dict):
                    continue
                function = item.get("function") if isinstance(item.get("function"), dict) else item
                calls.append({
                    "id": str(item.get("id", uuid.uuid4().hex)),
                    "name": str(function.get("name", "")),
                    "arguments": function.get("arguments", {}),
                })
            return calls
        text = _extract_text(payload)
        try:
            candidate = json.loads(text.strip())
        except (TypeError, json.JSONDecodeError):
            return []
        if isinstance(candidate, dict) and isinstance(candidate.get("tool_call"), dict):
            return [{"id": uuid.uuid4().hex, **candidate["tool_call"]}]
        if isinstance(candidate, dict) and isinstance(candidate.get("tool_calls"), list):
            return [item for item in candidate["tool_calls"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _assistant_tool_message(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict):
                    return dict(message)
            message = payload.get("message")
            if isinstance(message, dict):
                return dict(message)
        return {"role": "assistant", "content": _extract_text(payload)}

    @staticmethod
    def _tool_result_message(call: dict[str, Any], result: dict[str, Any], *, ollama: bool) -> dict[str, Any]:
        image_data = result.get("image_base64")
        text_result = dict(result)
        text_result.pop("image_base64", None)
        content = json.dumps(text_result, ensure_ascii=False, separators=(",", ":"))
        if ollama:
            message: dict[str, Any] = {"role": "tool", "content": content}
            if isinstance(image_data, str) and image_data:
                message["images"] = [image_data]
            return message
        if isinstance(image_data, str) and image_data:
            return {"role": "tool", "tool_call_id": call["id"], "content": [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
            ]}
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    def reload(self, overrides: dict[str, Any] | None = None) -> None:
        values = dict(overrides or {})
        configured_kind = str(values.get("kind", os.getenv("AI_BACKEND_KIND", ""))).strip().lower()
        self.url = str(values.get("url", os.getenv("AI_BACKEND_URL", ""))).strip()
        self.command = str(values.get("command", os.getenv("AI_BACKEND_COMMAND", ""))).strip()
        self.kind = configured_kind or ("command" if self.command else "http" if self.url else "queue")
        self.model = str(values.get("model", os.getenv("AI_BACKEND_MODEL", ""))).strip()
        self.format = str(values.get("format", os.getenv("AI_BACKEND_FORMAT", "openai"))).strip().lower()
        self.token = str(values.get("token", os.getenv("AI_BACKEND_TOKEN", ""))).strip()
        # Vision-capable local models can take several minutes to process the
        # board snapshot on CPU. A short transport timeout makes TTS report a
        # misleading empty response before the model can return its MOVE line.
        self.timeout = max(1.0, float(values.get("timeout", os.getenv("AI_BACKEND_TIMEOUT", "300"))))
        self.echo = bool(values.get("echo", _env_bool("AI_BACKEND_ECHO", False)))
        self.system_prompt = str(values.get("system_prompt", os.getenv("AI_BACKEND_SYSTEM_PROMPT", ""))).strip()
        self.default_conversation_id = str(values.get("conversation_id", os.getenv("AI_BACKEND_CONVERSATION_ID", "tts-default"))).strip() or "tts-default"
        self.vision = bool(values.get("vision", True))
        self.ollama_keep_alive = str(values.get("ollama_keep_alive", os.getenv("OLLAMA_KEEP_ALIVE", "30m"))).strip() or "30m"
        try:
            self.observation_max_calls = max(1, min(int(values.get("observation_max_calls", os.getenv("AI_OBSERVATION_MAX_CALLS", "4"))), 20))
        except (TypeError, ValueError):
            self.observation_max_calls = 4
        try:
            self.observation_timeout = max(1.0, min(float(values.get("observation_timeout", os.getenv("AI_OBSERVATION_TIMEOUT", "300"))), 300.0))
        except (TypeError, ValueError):
            self.observation_timeout = 300.0
        try:
            self.ollama_num_ctx = max(0, int(values.get("ollama_num_ctx", os.getenv("OLLAMA_NUM_CTX", "0")) or 0))
        except (TypeError, ValueError):
            self.ollama_num_ctx = 0

    def health(self) -> dict[str, Any]:
        return {
            "running": self.enabled,
            "configured": self.kind == "queue" or bool(self.url or self.command) or self.echo,
            "kind": self.kind,
            "url": self.url or None,
            "command": self.command or None,
            "format": self.format if self.kind == "http" else ("echo" if self.echo else None),
            "model": self.model or None,
            "conversation_id": self.default_conversation_id,
            "history_turns": self.history.limit,
        }

    def public_config(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "url": self.url, "command": self.command,
            "model": self.model, "format": self.format, "timeout": self.timeout,
            "echo": self.echo, "system_prompt": self.system_prompt,
            "conversation_id": self.default_conversation_id, "vision": self.vision,
            "ollama_keep_alive": self.ollama_keep_alive,
            "ollama_num_ctx": self.ollama_num_ctx,
            "observation_max_calls": self.observation_max_calls,
            "observation_timeout": self.observation_timeout,
            "token_configured": bool(self.token),
        }

    def save_config(self, values: dict[str, Any]) -> None:
        allowed = {"kind", "url", "command", "model", "format", "timeout", "echo", "system_prompt", "conversation_id", "vision", "ollama_keep_alive", "ollama_num_ctx", "observation_max_calls", "observation_timeout"}
        config = {key: values[key] for key in allowed if key in values}
        if str(config.get("kind", self.kind)).strip().lower() == "command" and not _env_bool("TTS_ALLOW_COMMAND_BACKEND"):
            raise ValueError("command backend is disabled; set TTS_ALLOW_COMMAND_BACKEND=1 explicitly")
        if str(config.get("kind", self.kind)).strip().lower() == "command" and not _command_allowed(str(config.get("command", self.command))):
            raise ValueError("command executable is not in TTS_ALLOWED_BACKEND_EXECUTABLES")
        if "token" in values and str(values["token"]).strip():
            config["token"] = str(values["token"]).strip()
        elif self.token:
            config["token"] = self.token
        self.config_store.save(config)
        self.reload(config)

    def _conversation(self, payload: dict[str, Any]) -> str:
        return str(payload.get("conversation_id") or self.default_conversation_id).strip() or self.default_conversation_id

    @staticmethod
    def _ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style multimodal content to Ollama native messages."""
        converted: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content", "")
            if not isinstance(content, list):
                converted_message: dict[str, Any] = {
                    "role": message.get("role", "user"),
                    "content": str(content),
                }
                existing_images = message.get("images")
                if isinstance(existing_images, list) and existing_images:
                    converted_message["images"] = [
                        image for image in existing_images
                        if isinstance(image, str) and image
                    ]
                if isinstance(message.get("tool_calls"), list):
                    converted_message["tool_calls"] = message["tool_calls"]
                converted.append(converted_message)
                continue
            text_parts: list[str] = []
            images: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {})
                    url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                    if isinstance(url, str) and "," in url and url.startswith("data:"):
                        images.append(url.split(",", 1)[1])
            converted_message: dict[str, Any] = {
                "role": message.get("role", "user"),
                "content": "\n".join(text_parts),
            }
            if images:
                converted_message["images"] = images
            converted.append(converted_message)
        return converted

    def _messages(self, payload: dict[str, Any], message: str) -> tuple[str, list[dict[str, Any]]]:
        conversation_id = self._conversation(payload)
        messages = self.history.messages(conversation_id)
        # Keep stale sessions from turning a single TTS reply into a very
        # slow model call.  Preserve the newest turns and cap each message.
        bounded: list[dict[str, Any]] = []
        remaining = 12000
        for item in reversed(messages):
            content = _public_ai_text(str(item.get("content", "")))
            content = content[:3000]
            if remaining <= 0:
                break
            content = content[:remaining]
            bounded.append({"role": item.get("role", "user"), "content": content})
            remaining -= len(content)
        messages = list(reversed(bounded))
        gameplay_prompt, context, _ = self._gameplay_context(payload, message)
        self._context_local.value = context
        # Reassert gameplay instructions on every turn. Previously, with the
        # default (generated) prompt and existing history, only stale chat
        # messages reached the model. That let it narrate algebraic moves
        # instead of emitting the executable MOVE command.
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        if gameplay_prompt:
            messages.append({"role": "system", "content": gameplay_prompt})
        messages.append({"role": "system", "content": self._observation_instructions()})
        _record_trace(
            "ai_prompt_built",
            conversation_id=conversation_id,
            message_count=len(messages),
            prompt_chars=sum(len(str(item.get("content", ""))) for item in messages),
            gameplay_prompt_chars=len(gameplay_prompt),
            context_chars=0,
            object_count=0,
            state_in_user_turn=False,
        )
        messages.append({"role": "user", "content": message})
        return conversation_id, messages

    def _review_execution_failure(self, failure: dict[str, Any]) -> dict[str, Any]:
        """Capture a post-move view and ask the backend to explain the failure.

        The review is deliberately diagnostic only. It cannot emit or execute
        movement commands; the failed action has already reached the
        uncertainty stop and must wait for player instructions.
        """
        verification = failure.get("verification", {})
        callback = self.observation_tools.get("tts_capture_view")
        if callback is None:
            return {"requested": True, "attached": False, "error": "visual observation is unavailable"}
        try:
            capture = callback({})
        except Exception as exc:
            return {"requested": True, "attached": False, "error": str(exc)[:300]}
        if not isinstance(capture, dict):
            return {"requested": True, "attached": False, "error": "visual observation returned an invalid result"}
        image_data = capture.get("image_base64")
        if not isinstance(image_data, str) or not image_data:
            return {
                "requested": True,
                "attached": False,
                "error": str(capture.get("error", "visual observation returned no image"))[:300],
            }

        review = {
            "requested": True,
            "attached": True,
            "bytes": len(image_data),
        }
        if self.kind != "http" or not self.url:
            review["text"] = "The board image was captured, but this backend cannot perform a follow-up visual review."
            return review

        expected = (failure.get("result") or {}).get("position") if isinstance(failure.get("result"), dict) else None
        prompt = (
            "Review this current Tabletop Simulator board image after a failed move. "
            "Do not issue any tool calls or movement commands. Briefly describe the likely visual cause, "
            "or say that the cause is unclear. This is a diagnostic report only; the action is stopped."
        )
        messages = [{
            "role": "system",
            "content": "You are performing a read-only visual failure review. Never propose or execute a new action.",
        }, {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt + " Expected placement: " + json.dumps(expected or verification.get("position_delta", {}), separators=(",", ":"))},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
            ],
        }]
        try:
            response = self._http_request({"message": prompt}, messages, include_tools=False)
            review_text = _public_ai_text(_extract_text(response))
            if review_text:
                review["text"] = review_text
        except Exception as exc:
            review["error"] = str(exc)[:300]
        return review

    @staticmethod
    def _failure_report(execution: dict[str, Any]) -> str:
        review_text = ""
        for entry in execution.get("executed", []):
            if not isinstance(entry, dict):
                continue
            review = entry.get("visual_review")
            if isinstance(review, dict) and review.get("text"):
                review_text = _public_ai_text(str(review["text"]))
                if review_text:
                    break
        if review_text:
            return _public_ai_text(
                "I couldn't complete that action, so I stopped. Visual review: "
                f"{review_text} Please provide further instructions."
            )
        return "I couldn't complete that action, so I stopped. Please provide further instructions."

    @staticmethod
    def _normalize_checkers_commands(
        commands: list[ParsedCommand],
        candidates: list[dict[str, Any]],
        *,
        mandatory_capture: bool,
    ) -> tuple[list[ParsedCommand], list[dict[str, Any]]]:
        """Constrain model MOVE text to the rules adapter's live candidates."""
        if not candidates:
            return commands, []
        usable: list[tuple[ParsedCommand, dict[str, Any]]] = []
        for candidate in candidates:
            target = candidate.get("target")
            guid = str(candidate.get("guid", "")).strip()
            if not guid or not isinstance(target, dict):
                continue
            try:
                args = {
                    "guid": guid,
                    "x": float(target["x"]),
                    "y": float(target["y"]),
                    "z": float(target["z"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
            usable.append((ParsedCommand("move_object", args), candidate))
        if not usable:
            return commands, []
        normalized: list[ParsedCommand] = []
        corrections: list[dict[str, Any]] = []
        for command in commands:
            if command.action != "move_object":
                normalized.append(command)
                continue
            matching = next(
                (
                    (candidate_command, candidate)
                    for candidate_command, candidate in usable
                    if str(candidate_command.args["guid"]).lower() == str(command.args.get("guid", "")).lower()
                    and all(abs(float(candidate_command.args[axis]) - float(command.args.get(axis, 0))) <= 0.05 for axis in ("x", "y", "z"))
                ),
                None,
            )
            selected, candidate = matching if matching is not None else usable[0]
            normalized.append(selected)
            if matching is None:
                corrections.append({
                    "original": dict(command.args),
                    "selected": dict(selected.args),
                    "target_tag": str((candidate.get("target") or {}).get("tag", "")),
                })
        return normalized, corrections

    def _finalize_result(self, result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # Serialize command application so two player messages cannot mutate
        # the same board between observation and post-action verification.
        with self._turn_lock:
            text = str(result.get("text", ""))
            commands = parse_ai_commands(text)
            controller = self.controller_provider() if self.controller_provider else {}
            corrections: list[dict[str, Any]] = []
            if str(controller.get("active_game", "")).strip().lower() == "checkers":
                candidates = result.get("_checkers_legal_moves")
                if isinstance(candidates, list):
                    commands, corrections = self._normalize_checkers_commands(
                        commands,
                        candidates,
                        mandatory_capture=bool(result.get("_checkers_mandatory_capture", False)),
                    )
            # Player chat must never receive the internal board snapshot or
            # telemetry, even when the model echoed it without emitting a
            # command. Commands are parsed first, then hidden from chat by
            # the same public-text filter.
            result["text"] = _public_ai_text(text)
            if corrections:
                target_tag = corrections[0].get("target_tag") or "the selected square"
                result["text"] = f"I will move a black checker to {target_tag}."
                result["command_corrections"] = corrections
                _record_trace("checkers_model_move_normalized", corrections=corrections)
            blocked: list[dict[str, Any]] = []
            # Commands are consumed by the server, not spoken into the TTS
            # chat. Keep only the sanitized player-facing text.
            dispatchable = []
            for command in commands:
                if command.action in {"spawn_catalog", "place_catalog"}:
                    catalog_object = self.catalog.get(str(command.args.get("guid", "")))
                    if not catalog_object:
                        blocked.append({"action": command.action, "status": "blocked", "reason": "catalog GUID is not known", "args": command.args})
                        continue
                    object_type = str(catalog_object.get("type", "")).lower()
                    object_name = str(catalog_object.get("name", "")).lower()
                    if "bag" in object_type or "container" in object_type or "master bag" in object_name:
                        blocked.append({"action": command.action, "status": "blocked", "reason": "bag/container catalog entries cannot be spawned as scene objects", "args": command.args})
                        continue
                    command.args.update({
                        "container_name": catalog_object.get("container") or "",
                        "container_path": catalog_object.get("containerPath") or catalog_object.get("container_path") or [],
                        "master_bag_guid": catalog_object.get("masterBagGuid") or catalog_object.get("master_bag_guid") or "",
                    })
                    if not self._catalog_container_is_live(command.args):
                        blocked.append({"action": command.action, "status": "blocked", "reason": "required catalog container is not present in the live TTS scene", "args": command.args})
                        continue
                dispatchable.append(command)
            result["parsed_commands"] = [{"action": item.action, "args": item.args, "destructive": item.destructive} for item in commands]
            if self.command_execution is not None and blocked:
                # A rejected action is itself a failure. Do not allow another
                # parsed action from the same model response to continue.
                result["execution"] = {
                    "executed": [],
                    "approval_required": [],
                    "blocked": blocked,
                    "stopped": True,
                    "stop_reason": "action was blocked; waiting for player instructions",
                }
                result["text"] = self._failure_report(result["execution"])
            elif self.command_execution is not None and dispatchable:
                execution = self.command_execution.execute(
                    dispatchable,
                    running=str(controller.get("state", "")) == "running",
                    active_game=str(controller.get("active_game", "")),
                )
                execution.setdefault("blocked", []).extend(blocked)
                result["execution"] = execution
                if execution.get("stopped") or any(
                    isinstance(item, dict) and item.get("status") in {"failed", "unverified", "blocked"}
                    for item in execution.get("executed", [])
                ):
                    result["text"] = self._failure_report(execution)
                verified_actions = any(
                    item.get("status") == "executed"
                    for item in execution.get("executed", [])
                    if isinstance(item, dict)
                )
                if execution.get("executed") or execution.get("approval_required"):
                    _record_trace("ai_commands_processed", commands=result["parsed_commands"], execution=execution)
                if str(controller.get("state", "")) == "running" and (verified_actions or execution.get("approval_required")):
                    # This is the autonomous turn boundary.  The controller
                    # persists it, allowing pause/resume to remain host-owned.
                    GatewayHandler.controller.advance_turn("ai")
            elif blocked:
                result["execution"] = {"executed": [], "approval_required": [], "blocked": blocked}
            return result

    def _catalog_container_is_live(self, args: dict[str, Any]) -> bool:
        """Prevent stale V6 catalog paths from causing Lua bag lookups."""
        context = getattr(self._context_local, "value", {})
        objects = context.get("objects") if isinstance(context, dict) else None
        if not isinstance(objects, list):
            return False
        live_guids = {str(item.get("guid", "")).lower() for item in objects if isinstance(item, dict)}
        live_names = {str(item.get("name", "")).strip().lower() for item in objects if isinstance(item, dict)}
        master_guid = str(args.get("master_bag_guid", "")).strip().lower()
        path = args.get("container_path") if isinstance(args.get("container_path"), list) else []
        container_name = str(args.get("container_name", "")).strip().lower()
        if master_guid and master_guid in live_guids:
            return True
        if path and str(path[0]).strip().lower() in live_names:
            return True
        return bool(container_name and container_name in live_names)

    def reset(self, conversation_id: str | None = None) -> str:
        selected = (conversation_id or self.default_conversation_id).strip() or self.default_conversation_id
        self.history.reset(selected)
        return selected

    def next_message(self, timeout: float) -> dict[str, Any] | None:
        try:
            return self._inbox.get(timeout=max(0.0, min(timeout, 300.0)))
        except queue.Empty:
            return None

    def _queue_for_external_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["tools"] = OBSERVATION_TOOL_SPECS
        payload["tool_call_endpoint"] = "/chat/tool"
        payload["tool_budget"] = {
            "max_calls": self.observation_max_calls,
            "timeout_seconds": self.observation_timeout,
        }
        item = {"id": uuid.uuid4().hex, "received_at": time.time(), "payload": payload}
        _record_trace(
            "ai_queue_outbound",
            direction="gateway_to_external_ai_client",
            item_id=item["id"],
            payload=payload,
        )
        try:
            self._inbox.put_nowait(item)
        except queue.Full as exc:
            raise RuntimeError("AI inbox is full; no external AI client is consuming it") from exc
        return {"text": "", "commands": [], "queued": True, "id": item["id"], "tool_call_endpoint": "/chat/tool"}

    def _complete_command(self, payload: dict[str, Any], messages: list[dict[str, Any]], *, include_tools: bool = True) -> dict[str, Any]:
        if not _env_bool("TTS_ALLOW_COMMAND_BACKEND"):
            raise RuntimeError("command backend is disabled; set TTS_ALLOW_COMMAND_BACKEND=1 explicitly")
        if not self.command:
            raise RuntimeError("AI_BACKEND_COMMAND is required when AI_BACKEND_KIND=command")
        if not _command_allowed(self.command):
            raise RuntimeError("AI backend executable is not in TTS_ALLOWED_BACKEND_EXECUTABLES")
        try:
            argv = shlex.split(self.command, posix=False)
        except ValueError as exc:
            raise RuntimeError(f"Invalid AI_BACKEND_COMMAND: {exc}") from exc
        if not argv:
            raise RuntimeError("AI_BACKEND_COMMAND must not be empty")

        command_payload = dict(payload)
        command_payload["messages"] = messages
        if include_tools:
            command_payload["tools"] = OBSERVATION_TOOL_SPECS
        encoded = json.dumps(command_payload, ensure_ascii=False)
        _record_trace(
            "ai_backend_outbound",
            direction="gateway_to_ai_cli",
            backend="command",
            payload=command_payload,
        )
        try:
            completed = subprocess.run(
                argv,
                input=encoded,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"AI CLI was not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"AI CLI timed out after {self.timeout:g} seconds") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                f"AI CLI exited with code {completed.returncode}: {detail[:500]}"
            )

        output = completed.stdout.strip()
        try:
            result: Any = json.loads(output)
        except json.JSONDecodeError:
            result = output
        text = _extract_text(result)
        if not text and isinstance(result, str):
            text = result
        if not text:
            raise RuntimeError("AI CLI returned no text on stdout")
        return {"text": text, "commands": [], "backend_response": result}

    def _complete_command_with_tools(
        self, payload: dict[str, Any], messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        started = time.monotonic()
        tool_count = 0
        image_count = 0
        observation_failures: list[dict[str, Any]] = []
        observation_successes = 0
        current = list(messages)
        while True:
            result = self._complete_command(
                payload,
                current,
                include_tools=tool_count < self.observation_max_calls,
            )
            calls = self._extract_tool_calls(result.get("backend_response"))
            if not calls:
                if observation_failures and not observation_successes:
                    result["text"] = self._observation_failure_report()
                result["observation_failures"] = observation_failures
                result["observation_successes"] = observation_successes
                return result
            remaining = self.observation_max_calls - tool_count
            if remaining <= 0 or time.monotonic() - started >= self.observation_timeout:
                return {
                    "text": "I could not finish checking the game state within the observation limit.",
                    "commands": [],
                    "backend_response": result.get("backend_response"),
                }
            current.append(self._assistant_tool_message(result.get("backend_response")))
            for call in calls[:remaining]:
                try:
                    name, arguments = self._validate_observation_call(call)
                    normalized_call = {"id": call.get("id", uuid.uuid4().hex), "name": name, "arguments": arguments}
                    tool_result, image_count = self._invoke_observation_with_image_budget(normalized_call, image_count)
                except (TypeError, ValueError) as exc:
                    normalized_call = {"id": call.get("id", uuid.uuid4().hex), "name": str(call.get("name", "")), "arguments": {}}
                    tool_result = {"ok": False, "error": str(exc)[:300]}
                if tool_result.get("ok") is False:
                    observation_failures.append({
                        "name": normalized_call.get("name", ""),
                        "error": str(tool_result.get("error", "observation failed"))[:300],
                    })
                else:
                    observation_successes += 1
                current.append(self._tool_result_message(normalized_call, tool_result, ollama=False))
                tool_count += 1
                if tool_count >= self.observation_max_calls or time.monotonic() - started >= self.observation_timeout:
                    break
            if tool_count >= self.observation_max_calls or time.monotonic() - started >= self.observation_timeout:
                current.append({
                    "role": "system",
                    "content": "The read-only observation budget is exhausted. Do not request another tool; answer using the evidence already returned.",
                })

    def _http_request(self, payload: dict[str, Any], messages: list[dict[str, Any]], *, include_tools: bool = True) -> Any:
        native_ollama = self.format == "ollama" or self.url.rstrip("/").endswith("/api/chat")
        if native_ollama:
            request_payload: dict[str, Any] = {
                "model": self.model,
                "messages": self._ollama_messages(messages),
                "stream": False,
                # Gemma exposed a multi-thousand-token hidden reasoning trace
                # for a simple board list and reached its response limit before
                # emitting the executable MOVE line. Gameplay needs a bounded
                # final answer, not a trace, and the local API supports this
                # explicit opt-out for thinking-capable models.
                "think": False,
                "keep_alive": self.ollama_keep_alive,
            }
            if self.ollama_num_ctx:
                request_payload["options"] = {"num_ctx": self.ollama_num_ctx}
        elif self.format == "generic":
            request_payload = {key: value for key, value in payload.items() if key not in {"message", "player"}}
            request_payload["messages"] = messages
        else:
            request_payload = {"messages": messages, "stream": False}
            if self.model:
                request_payload["model"] = self.model
        if include_tools:
            request_payload["tools"] = OBSERVATION_TOOL_SPECS

        encoded = json.dumps(request_payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.url, data=encoded, headers=headers, method="POST")
        _record_trace(
            "ai_backend_outbound",
            direction="gateway_to_ai_backend",
            backend="http",
            url=self.url,
            payload=request_payload,
            image_attached=any(
                (isinstance(item.get("images"), list) and bool(item["images"]))
                or (
                    isinstance(item.get("content"), list)
                    and any(part.get("type") == "image_url" for part in item["content"] if isinstance(part, dict))
                )
                for item in (request_payload.get("messages", []) if native_ollama else messages)
            ),
            tools_enabled=include_tools,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI backend returned HTTP {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach AI backend: {exc.reason}") from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("AI backend returned invalid JSON") from exc
        _record_trace(
            "ai_backend_inbound",
            direction="ai_backend_to_gateway",
            backend="http",
            url=self.url,
            response=result,
        )
        return result

    def _complete_http_with_tools(
        self,
        payload: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = time.monotonic()
        tool_count = 0
        image_count = 0
        observation_failures: list[dict[str, Any]] = []
        observation_successes = 0
        checkers_legal_moves: list[dict[str, Any]] = []
        checkers_mandatory_capture = False
        current = list(messages)
        response: Any = None
        while True:
            response = self._http_request(payload, current, include_tools=tool_count < self.observation_max_calls)
            calls = self._extract_tool_calls(response)
            if not calls:
                text = _extract_text(response)
                if observation_failures and not observation_successes:
                    text = self._observation_failure_report()
                elif not text.strip() and _response_was_truncated(response):
                    text = (
                        "I reached my response limit before I could finish analyzing the board, so I stopped. "
                        "Please provide further instructions."
                    )
                return {
                    "text": text,
                    "commands": [],
                    "backend_response": response,
                    "observation_failures": observation_failures,
                    "observation_successes": observation_successes,
                    "_checkers_legal_moves": checkers_legal_moves,
                    "_checkers_mandatory_capture": checkers_mandatory_capture,
                }
            remaining = self.observation_max_calls - tool_count
            if remaining <= 0 or time.monotonic() - started >= self.observation_timeout:
                return {
                    "text": "I could not finish checking the game state within the observation limit.",
                    "commands": [],
                    "backend_response": response,
                }
            current.append(self._assistant_tool_message(response))
            for call in calls[:remaining]:
                try:
                    name, arguments = self._validate_observation_call(call)
                    normalized_call = {"id": call.get("id", uuid.uuid4().hex), "name": name, "arguments": arguments}
                    result, image_count = self._invoke_observation_with_image_budget(normalized_call, image_count)
                except (TypeError, ValueError) as exc:
                    result = {"ok": False, "error": str(exc)[:300]}
                    normalized_call = {"id": call.get("id", uuid.uuid4().hex), "name": str(call.get("name", "")), "arguments": {}}
                if result.get("ok") is False:
                    observation_failures.append({
                        "name": normalized_call.get("name", ""),
                        "error": str(result.get("error", "observation failed"))[:300],
                    })
                else:
                    observation_successes += 1
                    if name == "tts_list_objects" and isinstance(result.get("checkers"), dict):
                        board = result["checkers"]
                        candidates = board.get("legal_black_moves")
                        if isinstance(candidates, list):
                            checkers_legal_moves = [item for item in candidates if isinstance(item, dict)]
                        checkers_mandatory_capture = bool(board.get("mandatory_capture_required", False))
                current.append(self._tool_result_message(
                    normalized_call,
                    result,
                    ollama=self.format == "ollama" or self.url.rstrip("/").endswith("/api/chat"),
                ))
                tool_count += 1
                if tool_count >= self.observation_max_calls or time.monotonic() - started >= self.observation_timeout:
                    break
            if tool_count >= self.observation_max_calls or time.monotonic() - started >= self.observation_timeout:
                current.append({
                    "role": "system",
                    "content": "The read-only observation budget is exhausted. Do not request another tool; answer using the evidence already returned.",
                })

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("AI backend is stopped. Start it from /admin.")
        message = str(payload.get("message", ""))
        payload = dict(payload)
        payload.setdefault("message", message)
        _record_trace(
            "ai_request_start",
            direction="gateway_to_ai_backend",
            backend_kind=self.kind,
            payload=payload,
        )
        conversation_id, messages = self._messages(payload, message)
        if self.kind == "queue":
            payload["conversation_id"] = conversation_id
            payload["messages"] = messages
            result = self._queue_for_external_client(payload)
            _record_trace("ai_response", direction="ai_backend_to_gateway", response=result)
            return result
        if self.kind == "command":
            result = self._complete_command_with_tools(payload, messages)
            if result.get("text"):
                self.history.append(conversation_id, [
                    {"role": "user", "content": _public_ai_text(message)},
                    {"role": "assistant", "content": _public_ai_text(str(result["text"]))},
                ])
            result = self._finalize_result(result, payload)
            _record_trace("ai_response", direction="ai_backend_to_gateway", response=result)
            return result
        if not self.url:
            if self.echo:
                result = {"text": message, "commands": []}
                safe_message = _public_ai_text(message)
                self.history.append(conversation_id, [{"role": "user", "content": safe_message}, {"role": "assistant", "content": safe_message}])
                _record_trace("ai_response", direction="ai_backend_to_gateway", response=result)
                return self._finalize_result(result, payload)
            raise RuntimeError("No AI backend configured. Set AI_BACKEND_URL, AI_BACKEND_COMMAND, or AI_BACKEND_KIND=queue.")

        result = self._complete_http_with_tools(payload, messages)
        text = str(result.get("text", ""))
        if text:
            self.history.append(conversation_id, [
                {"role": "user", "content": _public_ai_text(message)},
                {"role": "assistant", "content": _public_ai_text(text)},
            ])
        _record_trace("ai_response", direction="ai_backend_to_gateway", response={"text": text})
        return self._finalize_result(result, payload)


class GatewayHandler(BaseHTTPRequestHandler):
    backend = ChatBackend()
    controller = AIController(
        Path(__file__).resolve().parent / "game_rules",
        SessionStore(),
    )
    backend.context_provider = controller.context
    backend.controller_provider = controller.context
    bridge_response_callback: Callable[[dict[str, Any]], bool] | None = None

    def log_message(self, format: str, *args: Any) -> None:
        # Keep MCP stdout clean; the stdio transport owns stdout.
        return

    def do_GET(self) -> None:
        if not _require_transport_auth(self):
            return
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/")
        _record_trace("http_request", direction="client_to_gateway", method="GET", path=self.path)
        if path == "/admin":
            body = ADMIN_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/admin/api/status":
            if not _require_admin(self):
                return
            _json_response(self, 200, {"ok": True, "config": self.backend.public_config(), "health": self.backend.health()})
            return
        if path == "/admin/api/config":
            if not _require_admin(self):
                return
            _json_response(self, 200, {"ok": True, "config": self.backend.public_config()})
            return
        if path == "/admin/api/conversations":
            if not _require_admin(self):
                return
            _json_response(self, 200, {"ok": True, "conversations": self.backend.history.conversations()})
            return
        if path.startswith("/admin/api/conversations/"):
            if not _require_admin(self):
                return
            conversation_id = unquote(path.rsplit("/", 1)[-1])
            _json_response(self, 200, {"ok": True, "conversation_id": conversation_id, "messages": self.backend.history.messages(conversation_id)})
            return
        if path == "/admin/api/models":
            if not _require_admin(self):
                return
            models: list[str] = []
            sources: list[str] = []
            headers = {"Accept": "application/json"}
            if self.backend.token:
                headers["Authorization"] = f"Bearer {self.backend.token}"

            # Ollama's native endpoint is the reliable source of truth,
            # including models that are not exposed by its compatibility API.
            ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/")
            if ollama_host and not ollama_host.startswith(("http://", "https://")):
                ollama_host = "http://" + ollama_host
            ollama_url = ollama_host if ollama_host.endswith("/api/tags") else ollama_host + "/api/tags"
            candidates: list[tuple[str, str]] = [(ollama_url, "Ollama")]
            if self.backend.url:
                models_url = self.backend.url
                if "/chat/completions" in models_url:
                    models_url = models_url.split("/chat/completions", 1)[0] + "/models"
                elif models_url.endswith("/api/generate"):
                    models_url = models_url[:-len("/api/generate")] + "/api/tags"
                candidates.append((models_url, "HTTP backend"))

            for models_url, source in candidates:
                try:
                    with urlopen(Request(models_url, headers=headers), timeout=5) as response:
                        data = json.loads(response.read().decode("utf-8"))
                    entries = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
                    found = [
                        str(item.get("id", item.get("name", "")))
                        for item in entries if isinstance(item, dict)
                    ]
                    for model in found:
                        if model and model not in models:
                            models.append(model)
                    if found:
                        sources.append(source)
                except (OSError, ValueError, HTTPError, URLError):
                    continue
            _json_response(self, 200, {"ok": True, "models": models, "source": ", ".join(sources)})
            return
        if path == "/health":
            _json_response(self, 200, {"ok": True, "service": "tts-ai-gateway", "backend": self.backend.health()})
            return
        if path in {"/chat/next", "/v1/chat/next"}:
            if not _require_admin(self):
                return
            try:
                timeout = float(parse_qs(parsed.query).get("timeout", ["30"])[0])
            except ValueError:
                _json_response(self, 400, {"error": "timeout must be a number"})
                return
            item = self.backend.next_message(timeout)
            _json_response(self, 200, {"ok": True, "pending": item is not None, "item": item})
            return
        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/bridge/response":
            # Lua posts this only from the local TTS process. Do not expose a
            # way for remote clients to satisfy pending bridge requests.
            if self.client_address[0] not in {"127.0.0.1", "::1"}:
                _json_response(self, 403, {"error": "loopback bridge callback required"})
                return
            try:
                payload = self._read_json_body()
            except (ValueError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            callback = type(self).bridge_response_callback
            if callback is None:
                _json_response(self, 503, {"error": "bridge response receiver unavailable"})
                return
            accepted = callback(payload)
            _json_response(self, 200 if accepted else 409, {"ok": accepted})
            return
        if not _require_transport_auth(self):
            return
        _record_trace("http_request", direction="client_to_gateway", method="POST", path=self.path)
        if path.startswith("/admin/api/server/"):
            if not _require_admin(self):
                return
            action = path.rsplit("/", 1)[-1]
            if action == "stop":
                self.backend.enabled = False
            elif action in {"start", "restart"}:
                self.backend.reload(self.backend.config_store.load())
                self.backend.enabled = True
            else:
                _json_response(self, 404, {"error": "unknown_server_action"})
                return
            _json_response(self, 200, {"ok": True, "action": action, "health": self.backend.health()})
            return
        if path == "/admin/api/config":
            if not _require_admin(self):
                return
            try:
                payload = self._read_json_body()
                self.backend.save_config(payload)
                _json_response(self, 200, {"ok": True, "config": self.backend.public_config()})
            except (ValueError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})
            return
        if path in {"/chat/reset", "/v1/chat/reset"}:
            if not _require_admin(self):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                conversation_id = self.backend.reset(payload.get("conversation_id"))
            except (ValueError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            _json_response(self, 200, {"ok": True, "reset": True, "conversation_id": conversation_id})
            return
        if path in {"/chat/tool", "/v1/chat/tool"}:
            try:
                payload = self._read_json_body()
                result = self.backend._invoke_observation({
                    "name": payload.get("name", ""),
                    "arguments": payload.get("arguments", {}),
                })
            except (ValueError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            _json_response(self, 200, {
                "ok": bool(result.get("ok", False)),
                "name": str(payload.get("name", "")),
                "result": result,
            })
            return
        if path not in {"/chat", "/v1/chat", "/v1/ai/commands"}:
            _json_response(self, 404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2 * 1024 * 1024:
                raise ValueError("request body must be between 1 byte and 2 MB")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            _record_trace(
                "http_request_payload",
                direction="client_to_gateway",
                method="POST",
                path=path,
                payload=payload,
            )
            _record_trace(
                "ai_message_received",
                direction="tts_to_ai_gateway",
                path=path,
                message=str(payload.get("message", "")),
                player=payload.get("player", {}),
            )
            player = payload.get("player")
            is_host = isinstance(player, dict) and bool(player.get("host", False))
            command_result = self.controller.handle(
                str(payload.get("message", "")),
                is_host=is_host,
            )
            payload.setdefault("conversation_id", self.controller.conversation_id())
            if str(payload.get("message", "")).strip().lower() == "!ai start fresh":
                self.backend.reset(payload["conversation_id"])
            result = command_result or self.backend.complete(payload)
            _record_trace(
                "ai_message_response",
                direction="ai_gateway_to_tts",
                path=path,
                message=str(result.get("text", "")),
                commands=result.get("parsed_commands", result.get("commands", [])),
            )
        except (ValueError, json.JSONDecodeError) as exc:
            _json_response(self, 400, {"error": str(exc)})
            return
        except RuntimeError as exc:
            _json_response(self, 502, {"error": str(exc)})
            return

        _json_response(self, 200, result)

    do_PUT = do_POST

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 2 * 1024 * 1024:
            raise ValueError("request body must be between 1 byte and 2 MB")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        _record_trace(
            "http_request_payload",
            direction="client_to_gateway",
            method=getattr(self, "command", ""),
            path=urlsplit(self.path).path,
            payload=payload,
        )
        return payload

    def do_DELETE(self) -> None:
        if not _require_transport_auth(self):
            return
        path = urlsplit(self.path).path.rstrip("/")
        if path.startswith("/admin/api/conversations/"):
            if not _require_admin(self):
                return
            conversation_id = unquote(path.rsplit("/", 1)[-1])
            self.backend.reset(conversation_id)
            _json_response(self, 200, {"ok": True, "reset": conversation_id})
            return
        _json_response(self, 404, {"error": "not_found"})


class HttpGateway:
    def __init__(self, host: str | None = None, port: int | None = None,
                 context_provider: Callable[[], dict[str, Any]] | None = None) -> None:
        if context_provider is not None:
            GatewayHandler.backend.context_provider = context_provider
        gateway_host = host or os.getenv("TTS_HTTP_HOST", "127.0.0.1")
        gateway_port = port if port is not None else int(os.getenv("TTS_HTTP_PORT", "8765"))
        if gateway_host not in {"127.0.0.1", "localhost", "::1"}:
            if not _env_bool("TTS_HTTP_ALLOW_REMOTE"):
                raise ValueError("refusing non-loopback TTS_HTTP_HOST; set TTS_HTTP_ALLOW_REMOTE=1 only with network authentication")
            if not os.getenv("TTS_HTTP_AUTH_TOKEN", "").strip():
                raise ValueError("TTS_HTTP_AUTH_TOKEN is required when remote HTTP access is enabled")
        self.server = ThreadingHTTPServer((gateway_host, gateway_port), GatewayHandler)
        self.host = gateway_host
        self.port = gateway_port
        self._thread = threading.Thread(
            target=self.server.serve_forever,
            name="tts-ai-http-gateway",
            daemon=True,
        )

    def configure_gameplay(self, request: Callable[[str, dict[str, Any]], dict[str, Any]]) -> None:
        """Attach the already-created TTS bridge without importing server.py."""
        controller = GatewayHandler.controller
        GatewayHandler.backend.configure_gameplay(
            controller_provider=controller.context,
            request=request,
            propose=controller.propose_approval,
        )
        controller.set_approval_executor(
            lambda proposal: request(str(proposal["action"]), dict(proposal.get("args", {})))
        )

    def configure_observation_tools(
        self, provider: Callable[[str, dict[str, Any]], dict[str, Any]]
    ) -> None:
        GatewayHandler.backend.configure_observation_tools({
            name: (lambda args, tool_name=name: provider(tool_name, args))
            for name in OBSERVATION_TOOL_NAMES
        })

    def configure_bridge_response(
        self, callback: Callable[[dict[str, Any]], bool]
    ) -> None:
        """Receive private Lua bridge results without using player chat."""
        GatewayHandler.bridge_response_callback = callback

    def start(self) -> None:
        _record_trace("process_thread_start", component="ai_http_gateway", host=self.host, port=self.port)
        self._thread.start()

    def close(self) -> None:
        _record_trace("process_stop_requested", component="ai_http_gateway", host=self.host, port=self.port)
        self.server.shutdown()
        self.server.server_close()
