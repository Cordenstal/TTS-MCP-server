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
    DndPromptBuilder,
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
<section><h2>Backend configuration</h2><div class="grid"><div><label>Backend kind</label><select id="kind"><option value="http">HTTP / OpenAI-compatible</option><option value="command">Local CLI command</option><option value="queue">Queue for MCP/Codex</option></select><label>Backend URL</label><input id="url" placeholder="http://127.0.0.1:11434/api/chat"><label>Command</label><input id="command" placeholder="ollama run llama3.2"><label>Model</label><input id="model" list="modelOptions" placeholder="Select or type a model"><datalist id="modelOptions"></datalist><button class="secondary" onclick="models()">Discover Ollama models</button><span id="models" class="muted"></span></div><div><label>Request format</label><select id="format"><option value="ollama">Ollama native chat (vision)</option><option value="openai">OpenAI chat completions</option><option value="generic">Generic JSON</option></select><label>Timeout seconds</label><input id="timeout" type="number" min="1"><label>Bearer token (leave blank to keep current)</label><input id="token" type="password"><label><input id="echo" type="checkbox" style="width:auto"> Echo mode</label><label><input id="vision" type="checkbox" style="width:auto"> Include board camera snapshot during active games</label></div></div><label>System prompt</label><textarea id="prompt" placeholder="Stable instructions for the AI player..."></textarea><button onclick="save()">Save and apply</button><span id="saveResult" class="muted"></span></section>
<section><h2>Conversation log</h2><button class="secondary" onclick="loadConversations()">Refresh</button><div id="conversations"></div></section>
<script>
const $=id=>document.getElementById(id); const adminToken=prompt('TTS admin token (TTS_ADMIN_TOKEN):')||''; const json=async(url,opt={})=>{opt.headers={...(opt.headers||{}),Authorization:'Bearer '+adminToken};let r=await fetch(url,opt);let d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d};
async function refresh(){let d=await json('/admin/api/status');$('status').textContent=JSON.stringify(d,null,2);let c=d.config;$('kind').value=c.kind||'queue';$('url').value=c.url||'';$('command').value=c.command||'';$('model').value=c.model||'';$('format').value=c.format||'openai';$('timeout').value=c.timeout||60;$('echo').checked=!!c.echo;$('vision').checked=c.vision!==false;$('prompt').value=c.system_prompt||'';}
async function server(action){try{await json('/admin/api/server/'+action,{method:'POST'});await refresh()}catch(e){alert(e)}}
async function save(){let b={kind:$('kind').value,url:$('url').value,command:$('command').value,model:$('model').value,format:$('format').value,timeout:Number($('timeout').value),echo:$('echo').checked,vision:$('vision').checked,system_prompt:$('prompt').value};try{await json('/admin/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});$('saveResult').textContent='Saved and applied';await refresh()}catch(e){$('saveResult').textContent=e}}
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


def _public_ai_text(text: str) -> str:
    """Remove machine commands from the chat message after they are parsed."""
    return re.sub(
        r"(?im)^\s*(?:MOVE|ROTATE|LOCK|UNLOCK|SPAWN|PLACE|SPAWN_BUILTIN|BROADCAST|DESTROY)\[[^\]\r\n]*\]\s*$",
        "",
        text,
    ).strip()


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
        self.controller_provider: Callable[[], dict[str, Any]] | None = None
        self.command_execution: CommandExecution | None = None
        self._turn_lock = threading.RLock()
        self._context_local = threading.local()
        catalog_path = os.getenv("TTS_OBJECT_CATALOG", "").strip()
        # Do not implicitly import or discover the former V6 catalog. Scene
        # awareness comes exclusively from live TTS objects and screenshots.
        self.catalog = CatalogIndex(catalog_path or None)
        self.prompt_builder = DndPromptBuilder(Path(__file__).resolve().parent / "game_rules", self.catalog)
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
        self.command_execution = CommandExecution(request, propose)

    def _gameplay_context(self, payload: dict[str, Any], message: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        intent = classify_intent(message)
        context = self.context_provider() if self.context_provider else {}
        context = context if isinstance(context, dict) else {}
        context = self.scene_intelligence.enrich(context, message, intent)
        controller = self.controller_provider() if self.controller_provider else {}
        game = str(controller.get("active_game", ""))
        prompt = self.prompt_builder.build(game=game, intent=intent, context=context)
        return prompt, context, [{"intent": intent.value, "game": game}]

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
            "ollama_num_ctx": self.ollama_num_ctx,
            "token_configured": bool(self.token),
        }

    def save_config(self, values: dict[str, Any]) -> None:
        allowed = {"kind", "url", "command", "model", "format", "timeout", "echo", "system_prompt", "conversation_id", "vision", "ollama_num_ctx"}
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
                converted.append({"role": message.get("role", "user"), "content": str(content)})
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
            content = str(item.get("content", ""))
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
        context_text = str(context.get("text", "")).strip() if isinstance(context, dict) else ""
        if context_text:
            messages.append({
                "role": "system",
                "content": "Current Tabletop Simulator state (authoritative for this turn):\n" + context_text,
            })
        user_content: Any = message
        if isinstance(context, dict) and context.get("image_base64"):
            user_content = [
                {"type": "text", "text": message},
                {"type": "image_url", "image_url": {
                    "url": f"data:{context.get('mime_type', 'image/jpeg')};base64,{context['image_base64']}"
                }},
            ]
        messages.append({"role": "user", "content": user_content})
        return conversation_id, messages

    def _finalize_result(self, result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # Serialize command application so two player messages cannot mutate
        # the same board between observation and post-action verification.
        with self._turn_lock:
            text = str(result.get("text", ""))
            commands = parse_ai_commands(text)
            if commands:
                # Commands are consumed by the server, not spoken into the
                # TTS chat. Keep any narration while hiding MOVE[...] etc.
                result["text"] = _public_ai_text(text)
            blocked: list[dict[str, Any]] = []
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
            if self.command_execution is not None and dispatchable:
                controller = self.controller_provider() if self.controller_provider else {}
                execution = self.command_execution.execute(
                    dispatchable,
                    running=str(controller.get("state", "")) == "running",
                    active_game=str(controller.get("active_game", "")),
                )
                execution.setdefault("blocked", []).extend(blocked)
                result["execution"] = execution
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
        return {"text": "", "commands": [], "queued": True, "id": item["id"]}

    def _complete_command(self, payload: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
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
            result = self._complete_command(payload, messages)
            if result.get("text"):
                self.history.append(conversation_id, [{"role": "user", "content": message}, {"role": "assistant", "content": result["text"]}])
            result = self._finalize_result(result, payload)
            _record_trace("ai_response", direction="ai_backend_to_gateway", response=result)
            return result
        if not self.url:
            if self.echo:
                result = {"text": message, "commands": []}
                self.history.append(conversation_id, [{"role": "user", "content": message}, {"role": "assistant", "content": message}])
                _record_trace("ai_response", direction="ai_backend_to_gateway", response=result)
                return self._finalize_result(result, payload)
            raise RuntimeError("No AI backend configured. Set AI_BACKEND_URL, AI_BACKEND_COMMAND, or AI_BACKEND_KIND=queue.")

        native_ollama = self.format == "ollama" or self.url.rstrip("/").endswith("/api/chat")
        if native_ollama:
            request_payload = {
                "model": self.model,
                "messages": self._ollama_messages(messages),
                "stream": False,
            }
            if self.ollama_num_ctx:
                request_payload["options"] = {"num_ctx": self.ollama_num_ctx}
        elif self.format == "generic":
            request_payload: dict[str, Any] = payload
            request_payload["messages"] = messages
        else:
            request_payload = {"messages": messages, "stream": False}
            if self.model:
                request_payload["model"] = self.model

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
                isinstance(item.get("content"), list)
                and any(part.get("type") == "image_url" for part in item["content"] if isinstance(part, dict))
                for item in messages
            ),
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

        text = _extract_text(result)
        _record_trace(
            "ai_backend_inbound",
            direction="ai_backend_to_gateway",
            backend="http",
            url=self.url,
            response=result,
        )
        if text:
            self.history.append(conversation_id, [{"role": "user", "content": message}, {"role": "assistant", "content": text}])
        _record_trace("ai_response", direction="ai_backend_to_gateway", response={"text": text, "backend_response": result})
        return self._finalize_result({"text": text, "commands": [], "backend_response": result}, payload)


class GatewayHandler(BaseHTTPRequestHandler):
    backend = ChatBackend()
    controller = AIController(
        Path(__file__).resolve().parent / "game_rules",
        SessionStore(),
    )
    backend.context_provider = controller.context
    backend.controller_provider = controller.context

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
        if not _require_transport_auth(self):
            return
        path = urlsplit(self.path).path.rstrip("/")
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
        gateway_port = port or int(os.getenv("TTS_HTTP_PORT", "8765"))
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

    def start(self) -> None:
        _record_trace("process_thread_start", component="ai_http_gateway", host=self.host, port=self.port)
        self._thread.start()

    def close(self) -> None:
        _record_trace("process_stop_requested", component="ai_http_gateway", host=self.host, port=self.port)
        self.server.shutdown()
        self.server.server_close()
