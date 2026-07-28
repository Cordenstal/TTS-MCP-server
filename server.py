from __future__ import annotations

import asyncio
import base64
import functools
import json
import os
import queue
import re
import socket
import sys
from statistics import median
import threading
import time
import uuid
from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import mss
from PIL import Image as PILImage
from PIL import ImageGrab as PILImageGrab
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Image as MCPImage

from http_gateway import BackendConfigStore, HttpGateway
from session_store import SessionStore
from action_plan import expectation_failures, validate_action_plan
from semantic_index import rank_scene_objects
from runtime_trace import (
    TRACE_ENABLED as _TRACE_ENABLED,
    TRACE_LOG_PATH as _TRACE_LOG_PATH,
    record as _record_trace,
    recent as _recent_trace,
    snapshot as _trace_value,
)
from save_file import apply_operations, inspect_save, resolve_save_path
from windows_gui import load_save_via_gui
from gameplay_runtime import checkers_capture_holding_position, should_capture_game_vision
from killteam_runtime import (
    KillTeamConfig,
    KillTeamError,
    KillTeamRuntime,
    SAVE_131_FIXTURE_PROFILE,
    TTSKillTeamBridge,
)


class TTSBridgeError(RuntimeError):
    """Base error raised by the Tabletop Simulator bridge."""


class TTSConnectionError(TTSBridgeError):
    """Raised when Tabletop Simulator or the local callback listener is unavailable."""


class TTSCommandError(TTSBridgeError):
    """Raised when the in-game Lua bridge rejects a command."""


PROJECT_ROOT = Path(__file__).resolve().parent
GAME_RULES_ROOT = PROJECT_ROOT / "game_rules"
session_store = SessionStore()
backend_config_store = BackendConfigStore()


class TTSBridge:
    """Client for Tabletop Simulator's External Editor API.

    TTS receives JSON over localhost:39999 and sends responses/events to a
    callback server on localhost:39998.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        send_port: int = 39999,
        receive_port: int = 39998,
        timeout: float = 300.0,
    ) -> None:
        self.host = host
        self.send_port = send_port
        self.receive_port = receive_port
        self.timeout = timeout

        self._listener_guard = threading.Lock()
        self._listener_ready = threading.Event()
        self._listener_stop = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._listener_error: Exception | None = None
        self._server_socket: socket.socket | None = None

        self._pending_guard = threading.Lock()
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}

        self._scripts_guard = threading.Lock()
        self._scripts_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        self._events_guard = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._chat_events: deque[dict[str, Any]] = deque(maxlen=200)
        self._chat_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)

    def ensure_listener(self) -> None:
        with self._listener_guard:
            if self._listener_thread and self._listener_thread.is_alive():
                return

            self._listener_ready.clear()
            self._listener_stop.clear()
            self._listener_error = None
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                name="tts-external-editor-listener",
                daemon=True,
            )
            _record_trace(
                "process_thread_start",
                component="tts_callback_listener",
                host=self.host,
                port=self.receive_port,
            )
            self._listener_thread.start()

        if not self._listener_ready.wait(timeout=3.0):
            raise TTSConnectionError(
                f"Timed out starting callback listener on {self.host}:{self.receive_port}."
            )
        if self._listener_error is not None:
            raise TTSConnectionError(
                f"Could not listen on {self.host}:{self.receive_port}: "
                f"{self._listener_error}. Close Atom or another TTS editor plugin "
                "that may already own port 39998."
            ) from self._listener_error

    def close(self) -> None:
        self._listener_stop.set()
        server_socket = self._server_socket
        if server_socket is not None:
            try:
                server_socket.close()
            except OSError:
                pass

    def _listen_loop(self) -> None:
        server: socket.socket | None = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.receive_port))
            server.listen(16)
            server.settimeout(0.5)
            self._server_socket = server
            self._listener_ready.set()

            while not self._listener_stop.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._listener_stop.is_set():
                        break
                    raise

                with connection:
                    message = self._read_json_message(connection)
                    if message is not None:
                        self._handle_message(message)
        except Exception as exc:
            self._listener_error = exc
            self._listener_ready.set()
        finally:
            self._server_socket = None
            if server is not None:
                try:
                    server.close()
                except OSError:
                    pass

    @staticmethod
    def _read_json_message(connection: socket.socket) -> dict[str, Any] | None:
        connection.settimeout(1.0)
        payload = bytearray()

        while len(payload) < 32 * 1024 * 1024:
            try:
                chunk = connection.recv(65536)
            except socket.timeout:
                break

            if not chunk:
                break
            payload.extend(chunk)

            # TTS generally sends one complete JSON object per connection.
            try:
                decoded = payload.decode("utf-8-sig")
                value = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

            if isinstance(value, dict):
                return value
            return None

        if not payload:
            return None

        try:
            value = json.loads(payload.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _record_event(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "received_at_unix": time.time(),
            "event_type": event_type,
            "data": data,
        }
        with self._events_guard:
            self._events.append(event)
        session_store.record_event(event_type, data)

    def deliver_response(self, response: dict[str, Any], *, transport: str) -> bool:
        """Release a pending bridge request from an approved private transport."""
        request_id = response.get("requestId")
        if not isinstance(request_id, str) or not request_id:
            return False
        with self._pending_guard:
            waiter = self._pending.get(request_id)
        if waiter is None:
            _record_trace(
                "tts_response_unmatched",
                trace_id=request_id[:12],
                transport=transport,
            )
            return False
        try:
            waiter.put_nowait(response)
        except queue.Full:
            return False
        _record_trace(
            "tts_response_delivered",
            trace_id=request_id[:12],
            transport=transport,
        )
        return True

    def _handle_message(self, message: dict[str, Any]) -> None:
        _record_trace(
            "tts_inbound",
            direction="tts_to_python",
            message_id=message.get("messageID"),
            payload=message,
        )
        # TTS normally sends an integer, but tolerate a stringified message ID
        # from alternate External Editor implementations.
        message_id = str(message.get("messageID", ""))

        if message_id == "4":
            self._record_event("custom_message_raw", message)
            custom = message.get("customMessage")
            if isinstance(custom, str):
                try:
                    decoded_custom = json.loads(custom)
                except json.JSONDecodeError:
                    decoded_custom = None
                if isinstance(decoded_custom, dict):
                    custom = decoded_custom
            if isinstance(custom, dict):
                self.deliver_response(custom, transport="external_editor")
                if custom.get("event") == "chat_message":
                    _record_trace(
                        "tts_chat_event",
                        direction="tts_to_python",
                        message_id=message_id,
                        message=str(custom.get("message") or "")[:12000],
                    )
                    with self._events_guard:
                        self._chat_events.append(custom)
                    try:
                        self._chat_queue.put_nowait(custom)
                    except queue.Full:
                        try:
                            self._chat_queue.get_nowait()
                            self._chat_queue.put_nowait(custom)
                        except queue.Empty:
                            pass
                self._record_event("custom_message", custom)
            else:
                self._record_event("malformed_custom_message", message)
            return

        if message_id == "1":
            self._scripts_queue.put(message)
            self._record_event(
                "scripts_loaded",
                {"script_count": len(message.get("scriptStates", []))},
            )
            return

        if message_id == "2":
            printed = str(message.get("message", ""))
            # Mirror every TTS print into the bridge trace. This includes
            # normal/system chat and Lua-side print output; it is diagnostic
            # output only and is not sent back into the game chat.
            _record_trace(
                "tts_print",
                direction="tts_to_python",
                message_id=message_id,
                message=printed,
            )
            response_prefix = "[tts-mcp-response]"
            if printed.startswith(response_prefix):
                try:
                    response = json.loads(printed[len(response_prefix):])
                except json.JSONDecodeError:
                    response = None
                if isinstance(response, dict):
                    self.deliver_response(response, transport="legacy_print")
                    self._record_event("mcp_response_print", response)
                    return
            chat_prefix = "[tts-mcp-chat]"
            if printed.startswith(chat_prefix):
                try:
                    chat = json.loads(printed[len(chat_prefix):])
                except json.JSONDecodeError:
                    chat = None
                if isinstance(chat, dict):
                    with self._events_guard:
                        self._chat_events.append(chat)
                    try:
                        self._chat_queue.put_nowait(chat)
                    except queue.Full:
                        try:
                            self._chat_queue.get_nowait()
                            self._chat_queue.put_nowait(chat)
                        except queue.Empty:
                            pass
                    self._record_event("chat_message", chat)
            self._record_event("tts_print", {"message": printed})
        elif message_id == "3":
            _record_trace(
                "tts_lua_error",
                direction="tts_to_python",
                message_id=message_id,
                error=message.get("error", ""),
                guid=message.get("guid"),
                prefix=message.get("errorMessagePrefix", ""),
            )
            self._record_event(
                "tts_lua_error",
                {
                    "error": message.get("error", ""),
                    "guid": message.get("guid"),
                    "prefix": message.get("errorMessagePrefix", ""),
                },
            )
        elif message_id == "6":
            self._record_event("game_saved", {})
        elif message_id == "7":
            self._record_event("object_created", {"guid": message.get("guid")})
        else:
            self._record_event("external_editor_message", message)

    def _send(self, message: dict[str, Any]) -> None:
        _record_trace(
            "tts_outbound",
            direction="python_to_tts",
            message_id=message.get("messageID"),
            payload=message,
        )
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        try:
            with socket.create_connection(
                (self.host, self.send_port), timeout=self.timeout
            ) as connection:
                connection.sendall(payload)
                try:
                    connection.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
        except OSError as exc:
            raise TTSConnectionError(
                f"Could not connect to Tabletop Simulator at "
                f"{self.host}:{self.send_port}. Start TTS, load a game, and "
                "enable/open its scripting environment."
            ) from exc

    def request(
        self,
        action: str,
        args: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        self.ensure_listener()
        request_id = uuid.uuid4().hex
        waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)

        with self._pending_guard:
            self._pending[request_id] = waiter

        _record_trace(
            "tts_request_start",
            trace_id=request_id[:12],
            action=action,
            args=args or {},
            timeout=timeout or self.timeout,
        )

        try:
            request_args = dict(args or {})
            custom_message = {
                "channel": "tts-mcp",
                "requestId": request_id,
                "action": action,
                "args": request_args,
            }
            # Certain External Editor builds lose nested customMessage values
            # while preserving direct properties. Keep the canonical args map
            # and mirror its fields for the Lua bridge's compatibility merge.
            for key, value in request_args.items():
                if key not in {"channel", "requestId", "action", "args"}:
                    custom_message[key] = value
            if action == "killteam_list_objects":
                scalar_collections = (
                    ("query_tags_json", "query_tag", 32),
                    ("required_guids_json", "required_guid", 32),
                    ("snap_point_tags_json", "snap_point_tag", 16),
                )
                for json_field, scalar_prefix, limit in scalar_collections:
                    try:
                        values = json.loads(str(request_args.get(json_field, "[]")))
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"{json_field} must be a JSON array"
                        ) from exc
                    if not isinstance(values, list) or len(values) > limit:
                        raise ValueError(
                            f"{json_field} must contain at most {limit} values"
                        )
                    custom_message[f"{scalar_prefix}_count"] = len(values)
                    for index, value in enumerate(values, start=1):
                        custom_message[f"{scalar_prefix}_{index}"] = str(value)
            # Tabletop Simulator's External Editor can expose nested objects
            # in customMessage as managed MoonSharp wrappers.  Its Lua object
            # APIs reject those wrappers as vectors ("Specified cast is not
            # valid").  Keep movement scalar-only at this boundary; the Lua
            # bridge rebuilds a native {x, y, z} table before calling TTS.
            if action == "move_object":
                position = request_args.get("position") or {}
                custom_message["guid"] = str(request_args.get("guid") or "")
                custom_message["x"] = float(position["x"])
                custom_message["y"] = float(position["y"])
                custom_message["z"] = float(position["z"])
            self._send(
                {
                    "messageID": 2,
                    # TTS invokes onExternalMessage only for object-form custom
                    # messages. The Lua boundary normalizes managed scalar
                    # values before JSON decoding or object API calls.
                    "customMessage": custom_message,
                }
            )
            try:
                response = waiter.get(timeout=timeout or self.timeout)
            except queue.Empty as exc:
                _record_trace(
                    "tts_request_timeout",
                    trace_id=request_id[:12],
                    action=action,
                    elapsed_ms=round((timeout or self.timeout) * 1000, 2),
                )
                recent = self.recent_events(5)
                raise TTSConnectionError(
                    f"TTS did not answer action '{action}'. The bridge response timed out; "
                    "this does not establish whether the Global Lua script is installed. "
                    f"Recent callback events: {json.dumps(recent, default=str)}"
                ) from exc
        finally:
            with self._pending_guard:
                self._pending.pop(request_id, None)

        if not response.get("ok", False):
            _record_trace(
                "tts_request_error",
                trace_id=request_id[:12],
                action=action,
                response=response,
            )
            raise TTSCommandError(str(response.get("error", "Unknown TTS bridge error")))
        _record_trace(
            "tts_request_complete",
            trace_id=request_id[:12],
            action=action,
            response=response,
        )
        return response.get("result")

    def get_scripts(self, timeout: float | None = None) -> list[dict[str, Any]]:
        """Request Lua scripts and UI XML through message ID 0."""
        self.ensure_listener()
        with self._scripts_guard:
            while True:
                try:
                    self._scripts_queue.get_nowait()
                except queue.Empty:
                    break

            self._send({"messageID": 0})
            try:
                response = self._scripts_queue.get(timeout=timeout or self.timeout)
            except queue.Empty as exc:
                raise TTSConnectionError(
                    "TTS did not return its scripts over the External Editor API."
                ) from exc

        states = response.get("scriptStates", [])
        return states if isinstance(states, list) else []

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._events_guard:
            return list(self._events)[-safe_limit:]

    def recent_chat(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_listener()
        safe_limit = max(1, min(limit, 200))
        with self._events_guard:
            return list(self._chat_events)[-safe_limit:]

    def wait_for_chat(self, timeout: float = 30.0) -> dict[str, Any]:
        # Chat notifications arrive asynchronously over the callback socket.
        # Start that socket before waiting; otherwise the first wait call can
        # silently miss the player's message.
        self.ensure_listener()
        try:
            return self._chat_queue.get(timeout=max(0.0, min(timeout, 300.0)))
        except queue.Empty as exc:
            raise TTSConnectionError(
                f"No Tabletop Simulator chat message arrived within {timeout:g} seconds."
            ) from exc


bridge = TTSBridge()
_killteam_lock = threading.RLock()
_killteam_runtime = KillTeamRuntime(TTSKillTeamBridge(bridge.request))

mcp = FastMCP(
    "tabletop-simulator",
    instructions=(
        "Use read tools before write tools. Identify objects by GUID. "
        "Ask for confirmation before destroying objects or making broad changes. "
        "Coordinates are Tabletop Simulator world coordinates in x, y, z order. "
        "The Tabletop Simulator game and this MCP server must run on the same host."
    ),
)


# Wrap every registered MCP tool once, so the trace shows the actual tool
# activation even when that tool does not call Tabletop Simulator.
_mcp_tool_decorator = mcp.tool


def _traced_mcp_tool(*decorator_args: Any, **decorator_kwargs: Any) -> Any:
    register = _mcp_tool_decorator(*decorator_args, **decorator_kwargs)

    def decorate(function: Any) -> Any:
        if asyncio.iscoroutinefunction(function):
            async def traced_async(*args: Any, **kwargs: Any) -> Any:
                started = time.monotonic()
                trace_id = _record_trace(
                    "mcp_tool_start",
                    tool=function.__name__,
                    args=_trace_value(kwargs),
                )
                try:
                    result = await function(*args, **kwargs)
                except Exception as exc:
                    _record_trace(
                        "mcp_tool_error",
                        trace_id=trace_id,
                        tool=function.__name__,
                        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                _record_trace(
                    "mcp_tool_complete",
                    trace_id=trace_id,
                    tool=function.__name__,
                    elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                )
                return result

            traced = functools.wraps(function)(traced_async)
        else:
            def traced_sync(*args: Any, **kwargs: Any) -> Any:
                started = time.monotonic()
                trace_id = _record_trace(
                    "mcp_tool_start",
                    tool=function.__name__,
                    args=_trace_value(kwargs),
                )
                try:
                    result = function(*args, **kwargs)
                except Exception as exc:
                    _record_trace(
                        "mcp_tool_error",
                        trace_id=trace_id,
                        tool=function.__name__,
                        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                _record_trace(
                    "mcp_tool_complete",
                    trace_id=trace_id,
                    tool=function.__name__,
                    elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                )
                return result

            traced = functools.wraps(function)(traced_sync)
        return register(traced)

    return decorate


mcp.tool = _traced_mcp_tool


CAPABILITY_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "tts_list_objects",
        "category": "observation",
        "mutates": False,
        "confirmation": "none",
        "verification": "result contains bounded object summaries",
    },
    {
        "name": "tts_get_scene_summary",
        "category": "observation",
        "mutates": False,
        "confirmation": "none",
        "verification": "use as the authoritative scene snapshot",
    },
    {
        "name": "tts_find_nearest_objects",
        "category": "spatial",
        "mutates": False,
        "confirmation": "none",
        "verification": "result includes distance from the query origin",
    },
    {
        "name": "tts_find_objects_in_region",
        "category": "spatial",
        "mutates": False,
        "confirmation": "none",
        "verification": "object bounds intersect the requested region",
    },
    {
        "name": "tts_measure_distance",
        "category": "spatial",
        "mutates": False,
        "confirmation": "none",
        "verification": "result includes world-coordinate distance",
    },
    {
        "name": "tts_get_relative_transform",
        "category": "spatial",
        "mutates": False,
        "confirmation": "none",
        "verification": "result includes position and rotation deltas",
    },
    {
        "name": "tts_search_scene",
        "category": "semantic",
        "mutates": False,
        "confirmation": "none",
        "verification": "ranked candidates include evidence and GUIDs",
    },
    {
        "name": "tts_resolve_object_reference",
        "category": "semantic",
        "mutates": False,
        "confirmation": "none",
        "verification": "only use resolved=true; disambiguate ties",
    },
    {
        "name": "tts_register_scene_alias",
        "category": "semantic",
        "mutates": True,
        "confirmation": "explicit alias registration",
        "verification": "GUID is checked before registration",
    },
    {
        "name": "tts_list_scene_aliases",
        "category": "semantic",
        "mutates": False,
        "confirmation": "none",
        "verification": "returns persisted aliases and optional game scope",
    },
    {
        "name": "tts_remove_scene_alias",
        "category": "semantic",
        "mutates": True,
        "confirmation": "explicit alias removal",
        "verification": "removed flag confirms deletion",
    },
    {
        "name": "tts_inspect_container",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "bounded contents and container summary",
    },
    {
        "name": "tts_get_zone_objects",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "zone occupancy returned from TTS",
    },
    {
        "name": "tts_get_snap_points",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "snap-point definitions returned",
    },
    {
        "name": "tts_take_from_container",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "normal intent; verify spawned object",
        "verification": "deferred result contains taken object summary",
    },
    {
        "name": "tts_put_object_into_container",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "normal intent; verify container state",
        "verification": "returned container summary",
    },
    {
        "name": "tts_validate_scene_requirements",
        "category": "validation",
        "mutates": False,
        "confirmation": "none",
        "verification": "returns every failed requirement",
    },
    {
        "name": "tts_validate_zone_occupancy",
        "category": "validation",
        "mutates": False,
        "confirmation": "none",
        "verification": "returns count, tags, and zone contents",
    },
    {
        "name": "tts_place_adjacent_to",
        "category": "placement",
        "mutates": True,
        "confirmation": "normal intent; verify post-state",
        "verification": "bounds-derived position and returned object summary",
    },
    {
        "name": "tts_place_in_zone",
        "category": "placement",
        "mutates": True,
        "confirmation": "normal intent; verify zone occupancy",
        "verification": "returned object state then zone query",
    },
    {
        "name": "tts_place_in_tagged_zone",
        "category": "placement",
        "mutates": True,
        "confirmation": "normal intent; resolve unique destination tag",
        "verification": "preserved board height, returned zone, and settled object state",
    },
    {
        "name": "tts_align_to_object",
        "category": "placement",
        "mutates": True,
        "confirmation": "normal intent; verify post-state",
        "verification": "returned target state after move/rotation",
    },
    {
        "name": "tts_move_object",
        "category": "mutation",
        "mutates": True,
        "confirmation": "normal intent; verify post-state",
        "verification": "returned object summary and optional screenshot",
    },
    {
        "name": "tts_move_checkers_piece",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "normal intent; validate live checkers move",
        "verification": "validated diagonal, final coordinate, and settled state",
    },
    {
        "name": "tts_killteam_setup",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "explicit setup boundary; fails closed on ambiguity",
        "verification": "tagged roster, dice, roller, counters, terrain, and visibility are validated",
    },
    {
        "name": "tts_killteam_observe",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "fresh role-filtered state with observation and map revisions",
    },
    {
        "name": "tts_killteam_get_roster",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "bounded contents of the configured dedicated AI roster container",
    },
    {
        "name": "tts_killteam_probe_line_of_sight",
        "category": "game-domain",
        "mutates": False,
        "confirmation": "none",
        "verification": "bounded nine-ray evidence with first blockers, visibility fraction, and collider uncertainty",
    },
    {
        "name": "tts_killteam_place_operative",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "semantic placement; exact GUID remains adapter-internal",
        "verification": "validated path and exact post-position",
    },
    {
        "name": "tts_killteam_deploy_test_model",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "explicit zero-argument tagged movement smoke test",
        "verification": "tag-resolved model and marker with x/z readback within 0.25 units",
    },
    {
        "name": "tts_killteam_search_deployment_names",
        "category": "observation",
        "mutates": False,
        "confirmation": "none",
        "verification": "zero-argument in-TTS name filter returns at most 20 compact matches",
    },
    {
        "name": "tts_killteam_activate_operative",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "legal activation transition",
        "verification": "active operative and AP returned",
    },
    {
        "name": "tts_killteam_shoot",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "legal ranged action; physical dice are authoritative",
        "verification": "LOS/range, attack and defense dice, damage, wounds, and state revision",
    },
    {
        "name": "tts_killteam_begin_setup_validation",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "explicit Save 131 validation start",
        "verification": "exact snap placement, nine-ray LOS, and Blue attack roll before pausing for Red",
    },
    {
        "name": "tts_killteam_complete_setup_validation",
        "category": "game-domain",
        "mutates": True,
        "confirmation": "explicit Red or host defense-roll acknowledgment",
        "verification": "settled Red dice and operative-script wound readback",
    },
    {
        "name": "tts_rotate_object",
        "category": "mutation",
        "mutates": True,
        "confirmation": "normal intent; verify post-state",
        "verification": "returned object summary and optional screenshot",
    },
    {
        "name": "tts_spawn_builtin",
        "category": "mutation",
        "mutates": True,
        "confirmation": "confirm broad or numerous spawns",
        "verification": "returned spawned-object summary",
    },
    {
        "name": "tts_destroy_object",
        "category": "destructive",
        "mutates": True,
        "confirmation": "explicit user confirmation required",
        "verification": "audit event and prior object summary",
    },
    {
        "name": "tts_capture_view",
        "category": "visual",
        "mutates": False,
        "confirmation": "none",
        "verification": "inspect capture metadata and image freshness",
    },
    {
        "name": "tts_capture_view_info",
        "category": "visual",
        "mutates": False,
        "confirmation": "none",
        "verification": "healthy capture metadata and timestamp",
    },
    {
        "name": "tts_calibrate_view",
        "category": "visual",
        "mutates": False,
        "confirmation": "none",
        "verification": "rectangle health plus monitor inventory",
    },
    {
        "name": "tts_focus_object_and_capture",
        "category": "visual",
        "mutates": True,
        "confirmation": "none; camera-only mutation",
        "verification": "object bounds determine target and camera distance",
    },
    {
        "name": "tts_wait_for_object_settle",
        "category": "observation",
        "mutates": False,
        "confirmation": "none",
        "verification": "returns final object state and settled flag",
    },
    {
        "name": "tts_execute_action_plan",
        "category": "planning",
        "mutates": True,
        "confirmation": "destructive steps require allow_irreversible=true",
        "verification": "per-step result; use scene summary afterward",
    },
    {
        "name": "tts_inspect_save_file",
        "category": "save-file",
        "mutates": False,
        "confirmation": "none",
        "verification": "JSON parses and returns file hash/object count",
    },
    {
        "name": "tts_edit_save_file",
        "category": "save-file",
        "mutates": True,
        "confirmation": "allow_irreversible=true required to write; backup is created",
        "verification": "pre/post hashes and backup path are returned",
    },
    {
        "name": "tts_load_save_file",
        "category": "save-file",
        "mutates": True,
        "confirmation": "explicit GUI coordinates and allow_irreversible=true required",
        "verification": "GUI action result plus post-load bridge event check",
    },
]

_ACTION_PLAN_RESULTS: dict[str, dict[str, Any]] = {}
_ACTION_PLAN_RESULT_KEYS: deque[str] = deque()
_SCENE_ALIASES: dict[str, str] = {}


async def call_tts(action: str, args: dict[str, Any] | None = None) -> Any:
    started = time.monotonic()
    trace_id = _record_trace("tts_action_start", action=action, args=args or {})
    try:
        result = await asyncio.to_thread(bridge.request, action, args)
    except Exception as exc:
        _record_trace(
            "tts_action_error",
            trace_id=trace_id,
            action=action,
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    _record_trace(
        "tts_action_complete",
        trace_id=trace_id,
        action=action,
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
    )
    return result


@mcp.tool()
async def tts_describe_capabilities(category: str = "") -> dict[str, Any]:
    """Describe available tool safety classes and verification expectations."""
    wanted = category.strip().lower()
    capabilities = [
        item for item in CAPABILITY_MANIFEST
        if not wanted or item["category"] == wanted
    ]
    return {
        "categories": sorted({item["category"] for item in CAPABILITY_MANIFEST}),
        "count": len(capabilities),
        "capabilities": capabilities,
    }


def _safe_game_rules_path(game_name: str, relative_path: str = "") -> Path:
    normalized_game = game_name.strip()
    if not normalized_game or normalized_game in {".", ".."}:
        raise ValueError("game_name must be a non-empty game directory name")
    game_root = (GAME_RULES_ROOT / normalized_game).resolve()
    rules_root = GAME_RULES_ROOT.resolve()
    if game_root.parent != rules_root:
        raise ValueError("game_name must resolve to a direct child of game_rules")
    target = (game_root / relative_path).resolve()
    if target != game_root and game_root not in target.parents:
        raise ValueError("rules path must remain inside the selected game directory")
    return target


def _object_identity(obj: dict[str, Any]) -> str:
    return " ".join(
        str(obj.get(key, ""))
        for key in ("name", "type", "description")
    ).strip().lower()


def _is_square_zone(obj: dict[str, Any]) -> bool:
    identity = _object_identity(obj)
    return any(
        marker in identity
        for marker in ("layoutzone", "scriptingtrigger", "fogofwar", "zone", "trigger")
    )


def _find_unique_tagged_zone(objects: list[dict[str, Any]], zone_tag: str) -> dict[str, Any]:
    wanted_tag = zone_tag.strip().lower()
    if not wanted_tag:
        raise ValueError("zone_tag must not be empty")
    tagged = [
        obj for obj in objects
        if isinstance(obj, dict)
        and wanted_tag in {str(tag).strip().lower() for tag in obj.get("tags") or []}
    ]
    zone_candidates = [obj for obj in tagged if _is_square_zone(obj)]
    matches = zone_candidates or tagged
    if len(matches) != 1:
        raise ValueError(
            f"zone tag {zone_tag!r} must resolve to exactly one live zone; found {len(matches)}"
        )
    return matches[0]


def _validate_chess_objects(objects: list[dict[str, Any]]) -> list[str]:
    files = {f"{letter}{rank}" for letter in "abcdefgh" for rank in range(1, 9)}
    seen_squares: dict[str, list[str]] = {}
    failures: list[str] = []
    valid_colors = {"white", "black"}
    valid_types = {"king", "queen", "rook", "bishop", "knight", "pawn"}

    for obj in objects:
        guid = str(obj.get("guid", "?"))
        tags = obj.get("tags") or []
        if not isinstance(tags, list):
            continue
        square_tags: set[str] = set()
        for raw_tag in tags:
            tag = str(raw_tag).strip().lower()
            parts = tag.split()
            if tag in files and _is_square_zone(obj):
                square_tags.add(tag)
                continue
            if not parts or parts[0] not in {"chess-square", "chess-piece"}:
                continue
            if parts[0] == "chess-square":
                if len(parts) != 2 or parts[1] not in files:
                    failures.append(f"{guid}: malformed or unknown chess-square tag '{raw_tag}'")
                    continue
                square_tags.add(parts[1])
            elif len(parts) != 3 or parts[1] not in valid_colors or parts[2] not in valid_types:
                failures.append(f"{guid}: malformed or unknown chess-piece tag '{raw_tag}'")
        for square in square_tags:
            seen_squares.setdefault(square, []).append(guid)

    for square in sorted(files):
        guids = seen_squares.get(square, [])
        if not guids:
            failures.append(f"missing chess-square tag '{square}'")
        elif len(guids) > 1:
            failures.append(f"duplicate chess-square tag '{square}' on GUIDs {', '.join(guids)}")
    return failures


@mcp.tool()
async def tts_list_game_rules(game_name: str = "") -> dict[str, Any]:
    """List read-only Markdown/text rules and context files for a game."""
    if not GAME_RULES_ROOT.exists():
        return {"game_name": game_name, "found": False, "files": []}
    if not game_name.strip():
        games = sorted(path.name for path in GAME_RULES_ROOT.iterdir() if path.is_dir())
        return {"found": True, "games": games}

    game_root = _safe_game_rules_path(game_name)
    if not game_root.is_dir():
        return {"game_name": game_name, "found": False, "files": []}
    files = sorted(
        str(path.relative_to(game_root)).replace("\\", "/")
        for path in game_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    )
    return {"game_name": game_name, "found": True, "files": files}


@mcp.tool()
async def tts_read_game_rule(game_name: str, relative_path: str) -> dict[str, Any]:
    """Read one Markdown/plain-text game rule file through a path-scoped tool."""
    target = _safe_game_rules_path(game_name, relative_path)
    if not target.is_file() or target.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Only existing .md and .txt rules files may be read")
    content = target.read_text(encoding="utf-8")
    return {
        "game_name": game_name,
        "path": str(target.relative_to(GAME_RULES_ROOT)).replace("\\", "/"),
        "content": content,
    }


@mcp.tool()
async def tts_validate_chess_mapping() -> dict[str, Any]:
    """Validate case-insensitive chess-square and chess-piece tags in the live table."""
    result = await call_tts("list_objects", {"max_results": 1000})
    objects = result.get("objects", []) if isinstance(result, dict) else []
    failures = _validate_chess_objects(objects if isinstance(objects, list) else [])
    session_store.record_event(
        "chess_mapping_validation",
        {"failure_count": len(failures), "failures": failures},
    )
    return {
        "valid": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "object_count": len(objects) if isinstance(objects, list) else 0,
    }


@mcp.tool()
async def tts_get_session(save_name: str) -> dict[str, Any]:
    """Read one persistent AI session by TTS save-file name."""
    session = await asyncio.to_thread(session_store.get_session, save_name)
    return {"found": session is not None, "session": session}


@mcp.tool()
async def tts_checkpoint_session(
    save_name: str,
    game_name: str,
    state: dict[str, Any],
    turn_number: int | None = None,
) -> dict[str, Any]:
    """Persist a completed-turn AI session checkpoint in SQLite."""
    session = await asyncio.to_thread(
        session_store.checkpoint,
        save_name,
        game_name,
        state,
        turn_number=turn_number,
    )
    return {"saved": True, "session": session}


@mcp.tool()
async def tts_audit_events(
    save_name: str = "",
    turn_number: int | None = None,
    event_type: str = "",
    since_unix: float | None = None,
    until_unix: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Read filtered persistent AI/TTS audit events."""
    events = await asyncio.to_thread(
        session_store.audit_events,
        save_name=save_name,
        turn_number=turn_number,
        event_type=event_type,
        since_unix=since_unix,
        until_unix=until_unix,
        limit=limit,
    )
    return {"count": len(events), "events": events}


@mcp.tool()
async def tts_ping() -> dict[str, Any]:
    """Check that Tabletop Simulator and the installed Global Lua bridge respond."""
    result = await call_tts("ping")
    return {"connected": True, "result": result}


def _killteam_call(method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Serialize Kill Team mutations and preserve the game-rule seam."""
    with _killteam_lock:
        try:
            return getattr(_killteam_runtime, method)(*args, **kwargs)
        except KillTeamError as exc:
            session_store.record_event(
                "killteam_action_error",
                {"method": method, "error_type": type(exc).__name__, "error": str(exc)},
            )
            raise


def _killteam_setup_sync(
    *,
    ai_team: str = "ai",
    units_per_inch: float = 1.0,
    ai_dice_count: int = 1,
    opponent_dice_count: int = 1,
    roster_container_guid: str = "e5adb7",
    fixture_profile: str = SAVE_131_FIXTURE_PROFILE.name,
) -> dict[str, Any]:
    """Start a fresh Kill Team scene epoch and validate it through TTS."""
    global _killteam_runtime
    if not ai_team.strip():
        raise ValueError("ai_team must not be empty")
    if units_per_inch <= 0:
        raise ValueError("units_per_inch must be positive")
    if ai_dice_count <= 0 or opponent_dice_count <= 0:
        raise ValueError("dice counts must be positive")
    if not roster_container_guid.strip():
        raise ValueError("roster_container_guid must not be empty")
    with _killteam_lock:
        _killteam_runtime = KillTeamRuntime(
            TTSKillTeamBridge(bridge.request),
            KillTeamConfig(
                ai_team=ai_team.strip().lower(),
                units_per_inch=float(units_per_inch),
                ai_dice_count=int(ai_dice_count),
                opponent_dice_count=int(opponent_dice_count),
                roster_container_guid=roster_container_guid.strip().lower(),
                fixture_profile=fixture_profile.strip(),
            ),
        )
    return _killteam_call("setup")


@mcp.tool()
async def tts_killteam_setup(
    ai_team: str = "ai",
    units_per_inch: float = 1.0,
    ai_dice_count: int = 1,
    opponent_dice_count: int = 1,
    roster_container_guid: str = "e5adb7",
    fixture_profile: str = SAVE_131_FIXTURE_PROFILE.name,
) -> dict[str, Any]:
    """Validate Save 131's native Kill Team setup and build role-filtered state."""
    return await asyncio.to_thread(
        _killteam_setup_sync,
        ai_team=ai_team,
        units_per_inch=units_per_inch,
        ai_dice_count=ai_dice_count,
        opponent_dice_count=opponent_dice_count,
        roster_container_guid=roster_container_guid,
        fixture_profile=fixture_profile,
    )


@mcp.tool()
async def tts_killteam_observe() -> dict[str, Any]:
    """Return the current role-filtered Kill Team observation."""
    return await asyncio.to_thread(_killteam_call, "observe")


@mcp.tool()
async def tts_killteam_get_roster() -> dict[str, Any]:
    """Inspect the bounded dedicated AI roster container."""
    return await asyncio.to_thread(_killteam_call, "get_roster")


@mcp.tool()
async def tts_killteam_probe_line_of_sight(
    attacker_id: str,
    target_id: str,
    eye_local: dict[str, float] | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """Return sampled physical LOS evidence for an AI operative and visible target."""
    if not attacker_id.strip() or not target_id.strip():
        raise ValueError("attacker_id and target_id are required")
    normalized_eye = None
    if eye_local is not None:
        if not isinstance(eye_local, dict):
            raise ValueError("eye_local must contain x, y, and z")
        try:
            normalized_eye = {axis: float(eye_local[axis]) for axis in ("x", "y", "z")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("eye_local must contain numeric x, y, and z") from exc
    return await asyncio.to_thread(
        _killteam_call,
        "probe_line_of_sight",
        attacker_id.strip(),
        target_id.strip(),
        eye_local=normalized_eye,
        debug=bool(debug),
    )


@mcp.tool()
async def tts_killteam_place_operative(
    operative_id: str,
    path: list[dict[str, float]],
    action_id: str = "",
) -> dict[str, Any]:
    """Place or move an AI operative along a validated horizontal path."""
    if not operative_id.strip() or not path:
        raise ValueError("operative_id and a non-empty path are required")
    return await asyncio.to_thread(
        _killteam_call,
        "place_operative",
        operative_id.strip(),
        path,
        action_id=action_id.strip() or None,
    )


@mcp.tool()
async def tts_killteam_deploy_test_model() -> dict[str, Any]:
    """Move the tagged Plague Marine to the tagged blue test marker and verify it."""
    return await asyncio.to_thread(_killteam_call, "deploy_test_model")


@mcp.tool()
async def tts_killteam_search_deployment_names() -> dict[str, Any]:
    """Find live named Kill Team models, dice, and roller objects without a scene dump."""
    return await asyncio.to_thread(
        bridge.request,
        "killteam_deployment_name_search",
        {},
    )


@mcp.tool()
async def tts_killteam_activate_operative(operative_id: str) -> dict[str, Any]:
    """Start the AI activation for one tagged operative."""
    if not operative_id.strip():
        raise ValueError("operative_id must not be empty")
    return await asyncio.to_thread(_killteam_call, "activate_operative", operative_id.strip())


@mcp.tool()
async def tts_killteam_shoot(
    attacker_id: str,
    target_id: str,
    weapon_id: str,
    action_id: str = "",
) -> dict[str, Any]:
    """Resolve one visible ranged attack through the tagged physical dice."""
    if not attacker_id.strip() or not target_id.strip() or not weapon_id.strip():
        raise ValueError("attacker_id, target_id, and weapon_id are required")
    return await asyncio.to_thread(
        _killteam_call,
        "shoot",
        attacker_id.strip(),
        target_id.strip(),
        weapon_id.strip(),
        action_id=action_id.strip() or None,
    )


@mcp.tool()
async def tts_killteam_begin_setup_validation(
    action_id: str = "",
) -> dict[str, Any]:
    """Place the Save 131 test model, prove LOS, roll Blue, and pause for Red."""
    return await asyncio.to_thread(
        _killteam_call,
        "begin_setup_validation",
        action_id=action_id.strip() or None,
    )


@mcp.tool()
async def tts_killteam_complete_setup_validation(
    acknowledged_by: str,
    action_id: str = "",
) -> dict[str, Any]:
    """After Red/host acknowledgment, read Red's roll and verify real wounds."""
    if not acknowledged_by.strip():
        raise ValueError("acknowledged_by is required")
    return await asyncio.to_thread(
        _killteam_call,
        "complete_setup_validation",
        acknowledged_by=acknowledged_by.strip(),
        action_id=action_id.strip() or None,
    )


@mcp.tool()
async def tts_list_objects(
    name_contains: str = "",
    tag: str = "",
    max_results: int = 200,
    compact: bool = True,
) -> dict[str, Any]:
    """List in-scene objects with GUIDs, names, types, transforms, lock state, and tags."""
    result = await call_tts(
        "list_objects",
        {
            "name_contains": name_contains,
            "tag": tag,
            "max_results": max(1, min(max_results, 1000)),
            "compact": compact,
        },
    )
    return result


@mcp.tool()
async def tts_find_nearest_objects(
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    reference_guid: str = "",
    name_contains: str = "",
    tag: str = "",
    max_results: int = 10,
) -> dict[str, Any]:
    """Find objects nearest a world point or an existing reference object."""
    if not reference_guid and (x is None or y is None or z is None):
        raise ValueError("Provide x, y, z or reference_guid")
    args: dict[str, Any] = {
        "name_contains": name_contains,
        "tag": tag,
        "max_results": max(1, min(max_results, 100)),
    }
    if reference_guid:
        args["guid"] = reference_guid
    else:
        args["position"] = {"x": x, "y": y, "z": z}
    return await call_tts("find_nearest_objects", args)


@mcp.tool()
async def tts_find_objects_in_region(
    minimum_x: float,
    minimum_y: float,
    minimum_z: float,
    maximum_x: float,
    maximum_y: float,
    maximum_z: float,
    name_contains: str = "",
    tag: str = "",
    max_results: int = 200,
) -> dict[str, Any]:
    """Find objects whose world-space bounds intersect an axis-aligned region."""
    return await call_tts(
        "find_objects_in_region",
        {
            "minimum": {"x": minimum_x, "y": minimum_y, "z": minimum_z},
            "maximum": {"x": maximum_x, "y": maximum_y, "z": maximum_z},
            "name_contains": name_contains,
            "tag": tag,
            "max_results": max(1, min(max_results, 1000)),
        },
    )


@mcp.tool()
async def tts_search_scene(reference: str, max_results: int = 10) -> dict[str, Any]:
    """Search live scene objects by name, tag, type, description, or GUID."""
    if not reference.strip():
        raise ValueError("reference must not be empty")
    result = await call_tts("list_objects", {"max_results": 1000})
    objects = result.get("objects", []) if isinstance(result, dict) else []
    ranked = rank_scene_objects(reference, objects if isinstance(objects, list) else [], max_results)
    return {
        "reference": reference,
        "count": len(ranked),
        "candidates": ranked,
    }


@mcp.tool()
async def tts_resolve_object_reference(reference: str, max_candidates: int = 5) -> dict[str, Any]:
    """Resolve a human object reference into ranked GUID candidates with evidence."""
    normalized = reference.strip().lower()
    if not normalized:
        raise ValueError("reference must not be empty")
    aliases = await asyncio.to_thread(session_store.list_semantic_aliases)
    alias = next((item for item in aliases if item["alias"] == normalized), None)
    alias_guid = alias["guid"] if alias else _SCENE_ALIASES.get(normalized)
    if alias_guid:
        object_state = await tts_get_object(alias_guid)
        return {
            "reference": reference,
            "resolved": True,
            "ambiguous": False,
            "resolution": "explicit alias",
            "candidates": [{
                "score": 100,
                "evidence": ["registered alias"],
                "alias": alias.get("alias") if alias else normalized,
                "role": alias.get("role", "") if alias else "",
                "object": object_state,
            }],
        }

    result = await tts_search_scene(reference, max_candidates)
    candidates = result["candidates"]
    top_score = candidates[0]["score"] if candidates else 0
    tied = len(candidates) > 1 and candidates[1]["score"] == top_score
    resolved = bool(candidates) and top_score >= 50 and not tied
    return {
        "reference": reference,
        "resolved": resolved,
        "ambiguous": bool(candidates) and (tied or not resolved),
        "resolution": "ranked scene search",
        "candidates": candidates,
    }


@mcp.tool()
async def tts_register_scene_alias(
    alias: str,
    guid: str,
    game_name: str = "",
    role: str = "",
) -> dict[str, Any]:
    """Register an explicit human-readable alias for an existing object GUID."""
    normalized = alias.strip().lower()
    if not normalized:
        raise ValueError("alias must not be empty")
    object_state = await tts_get_object(guid)
    _SCENE_ALIASES[normalized] = guid
    saved = await asyncio.to_thread(
        session_store.save_semantic_alias,
        alias,
        guid,
        game_name=game_name,
        role=role,
    )
    return {**saved, "object": object_state}


@mcp.tool()
async def tts_list_scene_aliases(game_name: str = "") -> dict[str, Any]:
    """List persisted semantic aliases, optionally scoped to a game."""
    aliases = await asyncio.to_thread(
        session_store.list_semantic_aliases,
        game_name=game_name,
    )
    return {"count": len(aliases), "aliases": aliases}


@mcp.tool()
async def tts_remove_scene_alias(alias: str, game_name: str = "") -> dict[str, Any]:
    """Remove a persisted semantic alias."""
    if not alias.strip():
        raise ValueError("alias must not be empty")
    removed = await asyncio.to_thread(
        session_store.delete_semantic_alias,
        alias,
        game_name=game_name,
    )
    _SCENE_ALIASES.pop(alias.strip().lower(), None)
    return {"removed": removed, "alias": alias.strip().lower(), "game_name": game_name.strip().lower()}


@mcp.tool()
async def tts_inspect_container(guid: str) -> dict[str, Any]:
    """Inspect bounded contents of a bag, deck, or chip container."""
    return await call_tts("inspect_container", {"guid": guid})


@mcp.tool()
async def tts_get_zone_objects(guid: str, ignore_tags: bool = False) -> dict[str, Any]:
    """List objects currently occupying a scripting zone."""
    return await call_tts(
        "get_zone_objects",
        {"guid": guid, "ignore_tags": ignore_tags},
    )


@mcp.tool()
async def tts_get_snap_points(guid: str) -> dict[str, Any]:
    """Return an object's configured snap points."""
    return await call_tts("get_snap_points", {"guid": guid})


@mcp.tool()
async def tts_take_from_container(
    container_guid: str,
    item_guid: str = "",
    index: int | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    flip: bool = False,
    smooth: bool = True,
) -> dict[str, Any]:
    """Take one item from a container by contained GUID or index."""
    if not item_guid and index is None:
        raise ValueError("Provide item_guid or index")
    args: dict[str, Any] = {
        "container_guid": container_guid,
        "flip": flip,
        "smooth": smooth,
    }
    if item_guid:
        args["item_guid"] = item_guid
    else:
        args["index"] = index
    if x is not None or y is not None or z is not None:
        if x is None or y is None or z is None:
            raise ValueError("x, y, and z must be provided together")
        args["position"] = {"x": x, "y": y, "z": z}
    return await call_tts("take_from_container", args)


@mcp.tool()
async def tts_put_object_into_container(
    container_guid: str,
    object_guid: str,
    index: int | None = None,
) -> dict[str, Any]:
    """Put an existing object into a bag, deck, or compatible stack."""
    args: dict[str, Any] = {
        "container_guid": container_guid,
        "object_guid": object_guid,
    }
    if index is not None:
        args["index"] = index
    return await call_tts("put_object_into_container", args)


@mcp.tool()
async def tts_validate_scene_requirements(
    requirements: list[dict[str, Any]],
    max_objects: int = 1000,
) -> dict[str, Any]:
    """Validate count/tag/name/type requirements against the live scene."""
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("requirements must be a non-empty list")
    if max_objects <= 0 or max_objects > 1000:
        raise ValueError("max_objects must be between 1 and 1000")
    result = await tts_list_objects(max_results=max_objects)
    objects = result.get("objects", [])
    failures: list[str] = []
    if result.get("truncated"):
        failures.append("scene listing was truncated; increase max_objects before trusting validation")
    checks: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"requirements[{index}] must be an object")
        matches = objects
        if requirement.get("tag"):
            wanted = str(requirement["tag"]).lower()
            matches = [
                obj for obj in matches
                if wanted in {str(tag).lower() for tag in obj.get("tags") or []}
            ]
        if requirement.get("name_contains"):
            wanted = str(requirement["name_contains"]).lower()
            matches = [obj for obj in matches if wanted in str(obj.get("name", "")).lower()]
        if requirement.get("type"):
            wanted = str(requirement["type"]).lower()
            matches = [obj for obj in matches if str(obj.get("type", "")).lower() == wanted]
        minimum = int(requirement.get("min_count", 1))
        maximum = requirement.get("max_count")
        passed = len(matches) >= minimum and (maximum is None or len(matches) <= int(maximum))
        check = {"requirement": requirement, "count": len(matches), "passed": passed}
        checks.append(check)
        if not passed:
            failures.append(f"requirement {index} matched {len(matches)} objects")
    return {"valid": not failures, "failure_count": len(failures), "failures": failures, "checks": checks}


@mcp.tool()
async def tts_validate_zone_occupancy(
    zone_guid: str,
    min_count: int = 0,
    max_count: int | None = None,
    required_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Validate object count and required tags for a scripting zone."""
    result = await tts_get_zone_objects(zone_guid)
    objects = result.get("objects", [])
    failures: list[str] = []
    if len(objects) < min_count:
        failures.append(f"zone contains {len(objects)} objects; minimum is {min_count}")
    if max_count is not None and len(objects) > max_count:
        failures.append(f"zone contains {len(objects)} objects; maximum is {max_count}")
    tags = {str(tag).lower() for obj in objects for tag in obj.get("tags") or []}
    missing_tags = sorted({str(tag).lower() for tag in required_tags or []} - tags)
    if missing_tags:
        failures.append("missing required tags: " + ", ".join(missing_tags))
    return {
        "valid": not failures,
        "zone_guid": zone_guid,
        "object_count": len(objects),
        "missing_tags": missing_tags,
        "failures": failures,
        "objects": objects,
    }


def _placement_axis(reference: dict[str, Any], side: str) -> tuple[float, float, float]:
    axes = reference.get({
        "left": "transform_right",
        "right": "transform_right",
        "front": "transform_forward",
        "back": "transform_forward",
        "above": "transform_up",
        "below": "transform_up",
    }.get(side, "transform_right")) or {}
    sign = -1.0 if side in {"left", "back", "below"} else 1.0
    return (
        float(axes.get("x", 0)) * sign,
        float(axes.get("y", 0)) * sign,
        float(axes.get("z", 0)) * sign,
    )


@mcp.tool()
async def tts_place_adjacent_to(
    target_guid: str,
    reference_guid: str,
    side: str = "right",
    gap: float = 0.1,
    smooth: bool = True,
) -> dict[str, Any]:
    """Place one object beside another using their bounds and reference axes."""
    if side not in {"left", "right", "front", "back", "above", "below"}:
        raise ValueError("side must be left, right, front, back, above, or below")
    target = await tts_get_object(target_guid)
    reference = await tts_get_object(reference_guid)
    reference_position = (reference.get("bounds") or {}).get("center") or reference.get("position") or {}
    reference_size = (reference.get("bounds") or {}).get("size") or {}
    target_size = (target.get("bounds") or {}).get("size") or {}
    axis = _placement_axis(reference, side)
    axis_name = "x" if abs(axis[0]) >= max(abs(axis[1]), abs(axis[2])) else ("y" if abs(axis[1]) >= abs(axis[2]) else "z")
    distance = (
        abs(float(reference_size.get(axis_name, 0))) / 2
        + abs(float(target_size.get(axis_name, 0))) / 2
        + max(0.0, gap)
    )
    position = {
        "x": float(reference_position.get("x", 0)) + axis[0] * distance,
        "y": float(reference_position.get("y", 0)) + axis[1] * distance,
        "z": float(reference_position.get("z", 0)) + axis[2] * distance,
    }
    return await tts_move_object(target_guid, **position, smooth=smooth)


@mcp.tool()
async def tts_place_in_zone(
    target_guid: str,
    zone_guid: str,
    offset_x: float = 0,
    offset_y: float = 0,
    offset_z: float = 0,
    smooth: bool = True,
) -> dict[str, Any]:
    """Place an object at a zone's bounds center and return its post-state."""
    zone = await tts_get_object(zone_guid)
    center = (zone.get("bounds") or {}).get("center") or zone.get("position") or {}
    return await tts_move_object(
        target_guid,
        x=float(center.get("x", 0)) + offset_x,
        y=float(center.get("y", 0)) + offset_y,
        z=float(center.get("z", 0)) + offset_z,
        smooth=smooth,
    )


@mcp.tool()
async def tts_place_in_tagged_zone(
    target_guid: str,
    zone_tag: str,
    offset_x: float = 0,
    offset_y: float = 0,
    offset_z: float = 0,
    smooth: bool = True,
    timeout_seconds: float = 5,
    poll_seconds: float = 0.1,
) -> dict[str, Any]:
    """Place an object at the unique live zone carrying ``zone_tag``.

    This is the destination primitive for board games with invisible tagged
    square zones, including the chess A1-H8 LayoutZone grid. The target's
    current Y is preserved because board LayoutZones commonly span vertically
    through the table and their bounds center is not the piece surface.
    """
    listing = await tts_list_objects(max_results=1000)
    objects = listing.get("objects", []) if isinstance(listing, dict) else []
    if not isinstance(objects, list):
        objects = []
    zone = _find_unique_tagged_zone(objects if isinstance(objects, list) else [], zone_tag)
    center = (zone.get("bounds") or {}).get("center") or zone.get("position") or {}
    target = next(
        (
            obj for obj in objects
            if isinstance(obj, dict)
            and str(obj.get("guid") or "").lower() == target_guid.strip().lower()
        ),
        None,
    )
    if target is None:
        raise ValueError(f"no live object exists with GUID {target_guid}")
    target_position = (target or {}).get("position") or {}
    target_y = float(target_position.get("y", center.get("y", 0))) + offset_y
    move = await tts_move_object(
        target_guid,
        x=float(center.get("x", 0)) + offset_x,
        y=target_y,
        z=float(center.get("z", 0)) + offset_z,
        smooth=smooth,
    )
    settled = await tts_wait_for_object_settle(
        target_guid,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    final_position = (settled.get("object") or {}).get("position") or {}
    expected = {
        "x": float(center.get("x", 0)) + offset_x,
        "y": target_y,
        "z": float(center.get("z", 0)) + offset_z,
    }
    final_error = max(
        abs(float(final_position.get(axis, 0)) - expected[axis])
        for axis in ("x", "y", "z")
    )
    if not settled.get("settled") or final_error > 0.2:
        raise RuntimeError(
            f"object {target_guid} did not settle at tagged zone {zone_tag!r}; "
            f"final_error={final_error:.3f}, settled={settled.get('settled')}"
        )
    return {
        "zone_tag": zone_tag.strip(),
        "zone": zone,
        "move": move,
        "settled": settled,
        "expected_position": expected,
        "final_error": final_error,
    }


@mcp.tool()
async def tts_align_to_object(
    target_guid: str,
    reference_guid: str,
    align_position: bool = False,
    align_rotation: bool = True,
    smooth: bool = True,
) -> dict[str, Any]:
    """Align an object's rotation and optionally position to another object."""
    reference = await tts_get_object(reference_guid)
    result: dict[str, Any] = {}
    if align_position:
        position = reference.get("position") or {}
        result["move"] = await tts_move_object(
            target_guid,
            x=float(position.get("x", 0)),
            y=float(position.get("y", 0)),
            z=float(position.get("z", 0)),
            smooth=smooth,
        )
    if align_rotation:
        rotation = reference.get("rotation") or {}
        result["rotate"] = await tts_rotate_object(
            target_guid,
            x=float(rotation.get("x", 0)),
            y=float(rotation.get("y", 0)),
            z=float(rotation.get("z", 0)),
            smooth=smooth,
        )
    result["object"] = await tts_get_object(target_guid)
    return result


@mcp.tool()
async def tts_measure_distance(
    first_guid: str = "",
    second_guid: str = "",
    first_x: float | None = None,
    first_y: float | None = None,
    first_z: float | None = None,
    second_x: float | None = None,
    second_y: float | None = None,
    second_z: float | None = None,
) -> dict[str, Any]:
    """Measure world distance between two GUIDs, points, or one of each."""
    args: dict[str, Any] = {}
    if first_guid:
        args["first_guid"] = first_guid
    elif first_x is not None and first_y is not None and first_z is not None:
        args["first_position"] = {"x": first_x, "y": first_y, "z": first_z}
    else:
        raise ValueError("Provide first_guid or first_x, first_y, first_z")

    if second_guid:
        args["second_guid"] = second_guid
    elif second_x is not None and second_y is not None and second_z is not None:
        args["second_position"] = {"x": second_x, "y": second_y, "z": second_z}
    else:
        raise ValueError("Provide second_guid or second_x, second_y, second_z")
    return await call_tts("measure_distance", args)


@mcp.tool()
async def tts_get_relative_transform(from_guid: str, to_guid: str) -> dict[str, Any]:
    """Return world position/rotation deltas and distance between two objects."""
    if not from_guid.strip() or not to_guid.strip():
        raise ValueError("from_guid and to_guid are required")
    return await call_tts(
        "relative_transform",
        {"from_guid": from_guid, "to_guid": to_guid},
    )


@mcp.tool()
async def tts_get_scene_summary(max_results: int = 1000) -> dict[str, Any]:
    """Return a bounded, AI-friendly snapshot of the complete visible scene."""
    result = await call_tts(
        "list_objects",
        {"max_results": max(1, min(max_results, 1000))},
    )
    objects = result.get("objects", []) if isinstance(result, dict) else []
    objects = objects if isinstance(objects, list) else []
    by_type: dict[str, int] = {}
    locked_count = 0
    tagged_count = 0
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        object_type = str(obj.get("type") or "unknown")
        by_type[object_type] = by_type.get(object_type, 0) + 1
        if obj.get("locked") is True:
            locked_count += 1
        if obj.get("tags"):
            tagged_count += 1
    return {
        "object_count": len(objects),
        "total_matching": result.get("total_matching", len(objects)) if isinstance(result, dict) else len(objects),
        "truncated": bool(result.get("truncated", False)) if isinstance(result, dict) else False,
        "locked_count": locked_count,
        "tagged_count": tagged_count,
        "types": dict(sorted(by_type.items())),
        "objects": objects,
    }


@mcp.tool()
async def tts_execute_action_plan(
    actions: list[dict[str, Any]],
    allow_irreversible: bool = False,
    continue_on_error: bool = False,
    dry_run: bool = False,
    verify_after_each: bool = True,
    settle_seconds: float = 0.0,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Execute a validated sequence of TTS mutations and return each post-state.

    Actions use the same names and argument shapes as the individual mutation
    tools. Destruction is rejected unless the caller explicitly opts in.
    """
    plan = validate_action_plan(actions, allow_irreversible=allow_irreversible)
    if settle_seconds < 0 or settle_seconds > 5:
        raise ValueError("settle_seconds must be between 0 and 5")
    idempotency_key = idempotency_key.strip()
    if idempotency_key:
        cached = _ACTION_PLAN_RESULTS.get(idempotency_key)
        if cached is not None:
            return {**cached, "replayed": True}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, item in enumerate(plan):
        preconditions = item["preconditions"]
        if preconditions:
            guid = preconditions.get("guid") or item["args"].get("guid")
            if not isinstance(guid, str) or not guid:
                raise ValueError(f"actions[{index}] preconditions require a GUID")
            actual = await call_tts("get_object", {"guid": guid})
            mismatches = expectation_failures(actual, preconditions)
            if mismatches:
                failure = {
                    "index": index,
                    "action": item["action"],
                    "ok": False,
                    "phase": "precondition",
                    "error": "; ".join(mismatches),
                }
                results.append(failure)
                failures.append(failure)
                if not continue_on_error:
                    break
                continue
        if dry_run:
            results.append({
                "index": index,
                "action": item["action"],
                "ok": True,
                "dry_run": True,
                "args": item["args"],
            })
            continue
        try:
            result = await call_tts(item["action"], item["args"])
            if settle_seconds:
                await asyncio.sleep(settle_seconds)
            postconditions = item["postconditions"]
            if verify_after_each and postconditions:
                guid = postconditions.get("guid") or item["args"].get("guid")
                if not isinstance(guid, str) or not guid:
                    raise ValueError(f"actions[{index}] postconditions require a GUID")
                actual = await call_tts("get_object", {"guid": guid})
                mismatches = expectation_failures(actual, postconditions)
                if mismatches:
                    raise TTSCommandError("postcondition failed: " + "; ".join(mismatches))
            results.append({
                "index": index,
                "action": item["action"],
                "ok": True,
                "result": result,
            })
        except (TTSBridgeError, ValueError, TypeError) as exc:
            failure = {
                "index": index,
                "action": item["action"],
                "ok": False,
                "error": str(exc),
            }
            results.append(failure)
            failures.append(failure)
            if not continue_on_error:
                break
    session_store.record_event(
        "action_plan",
        {
            "step_count": len(plan),
            "executed_count": len(results),
            "failure_count": len(failures),
        },
    )
    response = {
        "ok": not failures,
        "dry_run": dry_run,
        "planned_count": len(plan),
        "executed_count": len(results),
        "failure_count": len(failures),
        "results": results,
    }
    if idempotency_key:
        if idempotency_key not in _ACTION_PLAN_RESULTS:
            if len(_ACTION_PLAN_RESULT_KEYS) >= 200:
                expired = _ACTION_PLAN_RESULT_KEYS.popleft()
                _ACTION_PLAN_RESULTS.pop(expired, None)
            _ACTION_PLAN_RESULT_KEYS.append(idempotency_key)
        _ACTION_PLAN_RESULTS[idempotency_key] = response
    return response


@mcp.tool()
async def tts_inspect_save_file(save_path: str = "") -> dict[str, Any]:
    """Inspect a numbered local TTS JSON save without changing it."""
    return await asyncio.to_thread(inspect_save, save_path)


@mcp.tool()
async def tts_edit_save_file(
    operations: list[dict[str, Any]],
    save_path: str = "",
    allow_irreversible: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply bounded JSON-pointer edits to a numbered save, with a backup."""
    return await asyncio.to_thread(
        apply_operations,
        save_path,
        operations,
        allow_irreversible=allow_irreversible,
        dry_run=dry_run,
    )


@mcp.tool()
async def tts_load_save_file(
    save_path: str = "",
    games_button_x: int = -1,
    games_button_y: int = -1,
    save_load_button_x: int = -1,
    save_load_button_y: int = -1,
    search_box_x: int = -1,
    search_box_y: int = -1,
    result_row_x: int = -1,
    result_row_y: int = -1,
    confirm_button_x: int | None = None,
    confirm_button_y: int | None = None,
    title_contains: str = "Tabletop Simulator",
    settle_seconds: float = 8.0,
    allow_irreversible: bool = False,
) -> dict[str, Any]:
    """Load a numbered save through the configured TTS Windows GUI profile.

    Coordinates are relative to the detected TTS window. Because TTS renders
    its menu in Unity, callers must supply coordinates calibrated for the
    current layout/window size.
    """
    if not allow_irreversible:
        raise ValueError("set allow_irreversible=true to load a save and replace the live scene")
    points = {
        "games_button": (games_button_x, games_button_y),
        "save_load_button": (save_load_button_x, save_load_button_y),
        "search_box": (search_box_x, search_box_y),
        "result_row": (result_row_x, result_row_y),
    }
    if any(value < 0 for point in points.values() for value in point):
        raise ValueError("all four required GUI coordinate pairs must be supplied")
    if (confirm_button_x is None) != (confirm_button_y is None):
        raise ValueError("confirm_button_x and confirm_button_y must be supplied together")
    confirm = (
        (confirm_button_x, confirm_button_y)
        if confirm_button_x is not None and confirm_button_y is not None
        else None
    )
    path = resolve_save_path(save_path)
    before_hash = inspect_save(str(path))["sha256"]
    started = time.time()
    gui_result = await asyncio.to_thread(
        load_save_via_gui,
        path,
        games_button=points["games_button"],
        save_load_button=points["save_load_button"],
        search_box=points["search_box"],
        result_row=points["result_row"],
        confirm_button=confirm,
        title_contains=title_contains,
        settle_seconds=settle_seconds,
    )
    after = await asyncio.to_thread(inspect_save, str(path))
    events = await asyncio.to_thread(bridge.recent_events, 100)
    scripts_loaded_after = any(
        event.get("event_type") == "scripts_loaded"
        and float(event.get("received_at_unix", 0)) >= started
        for event in events
        if isinstance(event, dict)
    )
    session_store.record_event(
        "save_file_loaded_via_gui",
        {
            "path": str(path),
            "sha256": after["sha256"],
            "scripts_loaded_after": scripts_loaded_after,
        },
    )
    return {
        "path": str(path),
        "sha256_before": before_hash,
        "sha256_after": after["sha256"],
        "file_unchanged_during_load": before_hash == after["sha256"],
        "gui": gui_result,
        "scripts_loaded_after": scripts_loaded_after,
        "verification_note": (
            "TTS reported a script-state load callback after the GUI action. "
            "The External Editor protocol does not expose the loaded save filename."
            if scripts_loaded_after
            else "The GUI action completed, but no script-state load callback was observed."
        ),
    }


@mcp.tool()
async def tts_get_object(guid: str) -> dict[str, Any]:
    """Inspect one in-scene object by its six-character Tabletop Simulator GUID."""
    return await call_tts("get_object", {"guid": guid})


@mcp.tool()
async def tts_move_object(
    guid: str,
    x: float,
    y: float,
    z: float,
    smooth: bool = True,
    collide: bool = False,
    fast: bool = True,
) -> dict[str, Any]:
    """Move an object to an absolute world position without game-rule checks.

    For the bundled checkers save, use ``tts_move_checkers_piece`` when the
    move must be validated as a legal black-piece move.
    """
    return await call_tts(
        "move_object",
        {
            "guid": guid,
            "position": {"x": x, "y": y, "z": z},
            "smooth": smooth,
            "collide": collide,
            "fast": fast,
        },
    )


def _checker_identity(obj: dict[str, Any]) -> str:
    tags = obj.get("tags") or []
    tag_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags)
    return f"{obj.get('name', '')} {tag_text}".strip().lower()


def _checker_axis_step(values: list[float]) -> float:
    ordered = sorted(float(value) for value in values)
    differences = [
        second - first
        for first, second in zip(ordered, ordered[1:])
        if 0.75 <= second - first <= 3.0
    ]
    if not differences:
        raise ValueError("could not infer the live checkers square spacing")
    return float(median(differences))


def _checker_position(obj: dict[str, Any]) -> tuple[float, float, float]:
    position = obj.get("position") or {}
    try:
        return float(position["x"]), float(position["y"]), float(position["z"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"checker {obj.get('guid', '')} has no usable position") from exc


def _checker_is_king(source: dict[str, Any], pieces: list[dict[str, Any]]) -> bool:
    bounds = source.get("bounds") or {}
    size = bounds.get("size") or {}
    try:
        if float(size.get("y", 0)) >= 0.4:
            return True
    except (TypeError, ValueError):
        pass
    source_x, source_y, source_z = _checker_position(source)
    source_guid = str(source.get("guid") or "").lower()
    for candidate in pieces:
        if str(candidate.get("guid") or "").lower() == source_guid:
            continue
        x, y, z = _checker_position(candidate)
        if (x - source_x) ** 2 + (z - source_z) ** 2 <= 0.16 and 0.05 <= abs(y - source_y) <= 1.0:
            return True
    return False


def _checker_stack_companions(source: dict[str, Any], pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_x, source_y, source_z = _checker_position(source)
    source_guid = str(source.get("guid") or "").lower()
    companions: list[dict[str, Any]] = []
    for candidate in pieces:
        if str(candidate.get("guid") or "").lower() == source_guid:
            continue
        x, y, z = _checker_position(candidate)
        if (x - source_x) ** 2 + (z - source_z) ** 2 <= 0.16 and 0.05 <= abs(y - source_y) <= 1.0:
            companions.append(candidate)
    return companions


def _is_black_king_row(target_z: float, objects: list[dict[str, Any]]) -> bool:
    centers: list[float] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if not any(re.fullmatch(r"[A-H][1-8]", str(tag).strip(), re.I) for tag in obj.get("tags") or []):
            continue
        position = obj.get("position") or {}
        try:
            centers.append(float(position["z"]))
        except (KeyError, TypeError, ValueError):
            continue
    unique = sorted(set(centers))
    if len(unique) < 2:
        return False
    spacing = min(second - first for first, second in zip(unique, unique[1:]))
    return abs(float(target_z) - unique[0]) <= max(0.25, spacing * 0.30)


def _validate_checkers_target(
    source: dict[str, Any],
    pieces: list[dict[str, Any]],
    target_x: float,
    target_z: float,
) -> dict[str, Any]:
    """Validate and normalize a black-piece move on the save's live lattice."""
    identity = _checker_identity(source)
    if "checker" not in identity or "black" not in identity:
        raise ValueError("tts_move_checkers_piece only moves black Checker pieces")
    if source.get("locked") is True:
        raise ValueError("the black checker is locked")

    source_x, source_y, source_z = _checker_position(source)
    checker_positions = [_checker_position(piece) for piece in pieces]
    step_x = _checker_axis_step([position[0] for position in checker_positions])
    step_z = _checker_axis_step([position[2] for position in checker_positions])
    raw_dx = float(target_x) - source_x
    raw_dz = float(target_z) - source_z
    steps_x = round(raw_dx / step_x)
    steps_z = round(raw_dz / step_z)
    tolerance = max(0.32, min(step_x, step_z) * 0.22)

    if steps_x == 0 or steps_z == 0 or abs(steps_x) != abs(steps_z) or abs(steps_x) not in {1, 2}:
        raise ValueError("checkers moves must be one- or two-square diagonals; X-only moves are invalid")
    normalized_x = source_x + steps_x * step_x
    normalized_z = source_z + steps_z * step_z
    if abs(float(target_x) - normalized_x) > tolerance or abs(float(target_z) - normalized_z) > tolerance:
        raise ValueError("target is not a live checkers square center")

    def near(x: float, z: float, position: tuple[float, float, float]) -> bool:
        return abs(position[0] - x) <= tolerance and abs(position[2] - z) <= tolerance

    occupied = []
    for piece in pieces:
        if str(piece.get("guid") or "").lower() == str(source.get("guid") or "").lower():
            continue
        position = _checker_position(piece)
        if near(normalized_x, normalized_z, position):
            occupied.append(piece)
    if occupied:
        raise ValueError("target checkers square is occupied")

    is_king = _checker_is_king(source, pieces)
    if not is_king and steps_z >= 0:
        if steps_z != 2:
            raise ValueError("black men must advance toward negative world Z")

    if abs(steps_x) == 2:
        midpoint_x = source_x + steps_x * step_x / 2
        midpoint_z = source_z + steps_z * step_z / 2
        midpoint = next(
            (piece for piece in pieces if near(midpoint_x, midpoint_z, _checker_position(piece))),
            None,
        )
        if midpoint is None or "red" not in _checker_identity(midpoint):
            raise ValueError("a two-square checkers move must jump an opposing red checker")
        captured_guid = str(midpoint.get("guid") or "")
    else:
        captured_guid = ""

    return {
        "guid": source.get("guid"),
        "source": {"x": source_x, "y": source_y, "z": source_z},
        "target": {"x": normalized_x, "y": source_y, "z": normalized_z},
        "steps": {"x": steps_x, "z": steps_z},
        "king": is_king,
        "step": {"x": step_x, "z": step_z},
        "tolerance": tolerance,
        "captured_guid": captured_guid,
    }


@mcp.tool()
async def tts_move_checkers_piece(
    guid: str,
    target_zone_tag: str = "",
    target_x: float | None = None,
    target_z: float | None = None,
    timeout_seconds: float = 5,
    poll_seconds: float = 0.1,
) -> dict[str, Any]:
    """Validate and execute one black move, removing its jumped red checker."""
    zone: dict[str, Any] | None = None
    if target_zone_tag.strip():
        listing = await tts_list_objects(max_results=200)
        wanted_tag = target_zone_tag.strip().lower()
        tagged = [
            obj for obj in listing.get("objects", [])
            if isinstance(obj, dict)
            and wanted_tag in {str(tag).strip().lower() for tag in obj.get("tags") or []}
            and "checker" not in _checker_identity(obj)
        ]
        zone_candidates = [
            obj for obj in tagged
            if any(word in _checker_identity(obj) for word in ("zone", "trigger", "fogofwar"))
        ]
        matches = zone_candidates or tagged
        if len(matches) != 1:
            raise ValueError(
                f"zone tag {target_zone_tag!r} must resolve to exactly one live square zone; "
                f"found {len(matches)}"
            )
        zone = matches[0]
        bounds = zone.get("bounds") or {}
        target_position = bounds.get("center") or zone.get("position") or {}
        try:
            target_x = float(target_position["x"])
            target_z = float(target_position["z"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"zone {target_zone_tag!r} has no usable world position") from exc
    else:
        listing = await tts_list_objects(max_results=200)
        if target_x is None or target_z is None:
            raise ValueError("provide target_zone_tag or both target_x and target_z")

    pieces = [
        obj for obj in listing.get("objects", [])
        if isinstance(obj, dict) and "checker" in _checker_identity(obj)
    ]
    source = next(
        (obj for obj in pieces if str(obj.get("guid") or "").lower() == guid.strip().lower()),
        None,
    )
    if source is None:
        raise ValueError(f"no live checker exists with GUID {guid}")
    validated = _validate_checkers_target(source, pieces, target_x, target_z)
    king_companions = _checker_stack_companions(source, pieces)
    target = validated["target"]
    move = await tts_move_object(
        guid=str(source["guid"]),
        x=target["x"],
        y=target["y"],
        z=target["z"],
        smooth=True,
        collide=False,
        fast=True,
    )
    settled = await tts_wait_for_object_settle(
        str(source["guid"]),
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    final_object = settled.get("object") or {}
    final_position = final_object.get("position") or {}
    final_error = max(
        abs(float(final_position.get(axis, 0)) - float(target[axis]))
        for axis in ("x", "y", "z")
    )
    if not settled.get("settled") or final_error > validated["tolerance"]:
        raise RuntimeError(
            f"checker {guid} did not settle at the validated target; "
            f"final_error={final_error:.3f}, settled={settled.get('settled')}"
        )
    king_stack: list[dict[str, Any]] = []
    for companion in king_companions:
        _, companion_y, _ = _checker_position(companion)
        companion_guid = str(companion["guid"])
        companion_target = {"x": target["x"], "y": target["y"] + companion_y - validated["source"]["y"], "z": target["z"]}
        companion_move = await tts_move_object(
            guid=companion_guid,
            x=companion_target["x"],
            y=companion_target["y"],
            z=companion_target["z"],
            smooth=False,
            collide=False,
            fast=False,
        )
        companion_settled = await tts_wait_for_object_settle(companion_guid, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
        companion_position = (companion_settled.get("object") or {}).get("position") or {}
        companion_error = max(abs(float(companion_position.get(axis, 0)) - companion_target[axis]) for axis in ("x", "y", "z"))
        if not companion_settled.get("settled") or companion_error > validated["tolerance"]:
            raise RuntimeError(f"king marker {companion_guid} did not follow the crowned checker")
        king_stack.append({"guid": companion_guid, "move": companion_move, "settled": companion_settled})
    capture: dict[str, Any] | None = None
    captured_guid = str(validated.get("captured_guid") or "")
    if captured_guid:
        captured_checker = next(piece for piece in pieces if str(piece.get("guid") or "").lower() == captured_guid.lower())
        holding_position = checkers_capture_holding_position(captured_checker, listing.get("objects", []))
        capture_move = await tts_move_object(
            guid=captured_guid,
            x=holding_position["x"],
            y=holding_position["y"],
            z=holding_position["z"],
            smooth=False,
            collide=False,
            fast=False,
        )
        capture_settled = await tts_wait_for_object_settle(captured_guid, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
        capture_object = capture_settled.get("object") or {}
        capture_position = capture_object.get("position") or {}
        capture_error = max(abs(float(capture_position.get(axis, 0)) - holding_position[axis]) for axis in ("x", "y", "z"))
        if not capture_settled.get("settled") or capture_error > validated["tolerance"]:
            raise RuntimeError(f"captured checker {captured_guid} did not reach its off-board holding position")
        capture = {
            "guid": captured_guid,
            "off_board_position": holding_position,
            "move": capture_move,
            "settled": capture_settled,
            "final_error": capture_error,
        }
    crown: dict[str, Any] | None = None
    if not validated["king"] and _is_black_king_row(target["z"], listing.get("objects", [])):
        crown_position = {"x": target["x"], "y": target["y"] + 0.5, "z": target["z"]}
        spawned = await call_tts("spawn_catalog", {"guid": str(source["guid"]), "position": crown_position})
        marker = spawned.get("object") or {}
        marker_guid = str(marker.get("guid") or "")
        if not marker_guid:
            raise RuntimeError("king marker clone returned no GUID")
        marker_settled = await tts_wait_for_object_settle(marker_guid, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
        marker_position = (marker_settled.get("object") or {}).get("position") or {}
        marker_error = max(abs(float(marker_position.get(axis, 0)) - crown_position[axis]) for axis in ("x", "y", "z"))
        if not marker_settled.get("settled") or marker_error > validated["tolerance"]:
            raise RuntimeError("king marker did not settle on the crowned checker")
        crown = {"marker_guid": marker_guid, "position": crown_position, "result": spawned}
    return {
        "action": "move_checkers_piece",
        "validated": validated,
        "target_zone": zone,
        "move": move,
        "settled": settled,
        "final_error": final_error,
        "capture": capture,
        "king_stack": king_stack,
        "crown": crown,
    }


@mcp.tool()
async def tts_rotate_object(
    guid: str,
    x: float,
    y: float,
    z: float,
    smooth: bool = True,
    collide: bool = False,
    fast: bool = True,
) -> dict[str, Any]:
    """Rotate an object to absolute Euler angles in degrees."""
    return await call_tts(
        "rotate_object",
        {
            "guid": guid,
            "rotation": {"x": x, "y": y, "z": z},
            "smooth": smooth,
            "collide": collide,
            "fast": fast,
        },
    )


@mcp.tool()
async def tts_set_camera(
    player_color: str = "White",
    x: float = 0,
    y: float = 0,
    z: float = 0,
    pitch: float = 45,
    yaw: float = 180,
    distance: float = 30,
    mode: str = "ThirdPerson",
) -> dict[str, Any]:
    """Point a player's Tabletop Simulator camera at a world position."""
    return await call_tts(
        "set_camera",
        {
            "player_color": player_color,
            "position": {"x": x, "y": y, "z": z},
            "pitch": pitch,
            "yaw": yaw,
            "distance": distance,
            "mode": mode,
        },
    )


def _capture_view(
    left: int,
    top: int,
    width: int,
    height: int,
    max_width: int,
    jpeg_quality: int,
) -> MCPImage:
    image, _ = _capture_view_snapshot(left, top, width, height, max_width)
    buffer = BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=max(30, min(jpeg_quality, 95)),
        optimize=True,
    )
    return MCPImage(data=buffer.getvalue(), format="jpeg")


def _capture_view_snapshot(
    left: int,
    top: int,
    width: int,
    height: int,
    max_width: int,
) -> tuple[PILImage.Image, dict[str, Any]]:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if max_width <= 0:
        raise ValueError("max_width must be positive")

    try:
        with mss.mss() as capture:
            screenshot = capture.grab(
                {"left": left, "top": top, "width": width, "height": height}
            )
        image = PILImage.frombytes("RGB", screenshot.size, screenshot.rgb)
    except Exception as mss_error:
        # Pillow uses a separate Windows capture path and can succeed when
        # mss/BitBlt fails for a layered or multi-monitor TTS window.
        try:
            image = PILImageGrab.grab(
                bbox=(left, top, left + width, top + height),
                include_layered_windows=True,
            ).convert("RGB")
        except Exception as pillow_error:
            raise RuntimeError(
                "Screen capture was denied. Run Tabletop Simulator and the TTS MCP "
                "gateway at the same Windows privilege level (use quick_start_admin.bat "
                "when TTS is running as Administrator). "
                f"mss={mss_error}; Pillow={pillow_error}"
            ) from pillow_error
    pixels = list(image.resize((1, 1), PILImage.Resampling.BOX).getdata())[0]
    extrema = image.getextrema()
    contrast = sum(channel_max - channel_min for channel_min, channel_max in extrema)
    metadata = {
        "captured_at_unix": time.time(),
        "rectangle": {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        },
        "source_size": {"width": image.width, "height": image.height},
        "mean_rgb": {"r": pixels[0], "g": pixels[1], "b": pixels[2]},
        "contrast_score": contrast,
        "blank_frame_suspected": contrast < 3,
    }
    if image.width > max_width:
        new_height = round(image.height * max_width / image.width)
        image = image.resize((max_width, new_height), PILImage.Resampling.LANCZOS)
    metadata["output_size"] = {"width": image.width, "height": image.height}
    return image, metadata


def _ai_game_context() -> dict[str, Any]:
    """Build current game context for the HTTP AI gateway.

    This is deliberately best-effort: chat must still work when TTS is paused,
    unavailable, or the configured backend is text-only.
    """
    persisted = session_store.get_controller_state() or {}
    state = persisted.get("state", {}) if isinstance(persisted, dict) else {}
    game = str(state.get("active_game", "")).strip()
    lifecycle = str(state.get("state", "inactive"))
    lines = [f"Active game: {game or 'none'}", f"AI play state: {lifecycle}"]
    if state.get("current_turn"):
        lines.append(f"Current turn: {state['current_turn']}")
    context: dict[str, Any] = {"text": "\n".join(lines)}
    # Chat begins context-light. The gateway acquires scene evidence only via
    # its bounded read-only observation tool loop.
    return context
    # A selected game may still be inactive while the host is preparing the
    # table.  Location inspection remains useful in that state; only vision
    # capture and autonomous mutations require running/paused lifecycle state.
    if not game:
        return context

    try:
        # Use the compact response mode so the External Editor callback is not
        # dropped when a table contains many objects and rich metadata.
        result = bridge.request("list_objects", {
            "max_results": int(os.getenv("AI_SCENE_MAX_OBJECTS", "250")),
            "compact": True,
        })
        objects = result.get("objects", []) if isinstance(result, dict) else []
        # Keep structured, authoritative location data available to the
        # gameplay search layer. Do not expose volatile physics fields unless
        # they help answer where an object is.
        compact_objects: list[dict[str, Any]] = []
        for obj in objects if isinstance(objects, list) else []:
            compact_objects.append({
                "guid": obj.get("guid"),
                "name": obj.get("name"),
                "type": obj.get("type"),
                "tags": obj.get("tags") or [],
                "position": obj.get("position"),
                "rotation": obj.get("rotation"),
                "bounds": obj.get("bounds"),
                "locked": obj.get("locked"),
                "zone_guids": obj.get("zone_guids") or [],
                "container_items": obj.get("container_items") or [],
            })
        context["objects"] = compact_objects
        _record_trace(
            "ai_scene_objects",
            game=game,
            count=len(compact_objects),
            source="tts_top_level_objects",
        )
        tagged: list[str] = []
        for obj in compact_objects:
            tags = obj.get("tags") or []
            if not isinstance(tags, list) or not any(str(tag).lower().startswith(("chess-", "game-")) for tag in tags):
                continue
            tagged.append(json.dumps({
                "guid": obj.get("guid"),
                "name": obj.get("name"),
                "tags": tags,
                "position": obj.get("position"),
                "rotation": obj.get("rotation"),
                "locked": obj.get("locked"),
            }, ensure_ascii=False, separators=(",", ":")))
        lines.append("Live table location data is authoritative. Positions are world coordinates (x,y,z); bounds are world-space extents. Use GUIDs to disambiguate objects.")
        if game.strip().lower() == "chess":
            chess_zone_tags = sorted({
                str(tag).strip().upper()
                for obj in compact_objects
                if _is_square_zone(obj)
                for tag in obj.get("tags") or []
                if str(tag).strip().lower() in {f"{letter}{rank}" for letter in "abcdefgh" for rank in range(1, 9)}
            })
            if chess_zone_tags:
                lines.append(
                    "CHESS DESTINATION ZONES (authoritative): "
                    + ", ".join(chess_zone_tags)
                    + ". Move a piece by calling tts_place_in_tagged_zone with the piece GUID and the destination zone_tag; do not calculate world X/Z coordinates."
                )
        if game.strip().lower() == "checkers":
            checker_square_tags = sorted({
                str(tag).strip().upper()
                for obj in compact_objects
                if _is_square_zone(obj)
                for tag in obj.get("tags") or []
                if str(tag).strip().lower() in {f"{letter}{rank}" for letter in "abcdefgh" for rank in range(1, 9)}
            })
            if checker_square_tags:
                lines.append(
                    "CHECKERS DESTINATION ZONES (authoritative): "
                    + ", ".join(checker_square_tags)
                    + ". Call tts_move_checkers_piece with the piece GUID and target_zone_tag; do not calculate world X/Z coordinates."
                )
            checker_positions = [
                (
                    str(obj.get("guid") or ""),
                    obj.get("position") or {},
                )
                for obj in compact_objects
                if str(obj.get("type", "")).lower() == "checker"
            ]
            x_values = sorted({
                round(float(position["x"]), 4)
                for _, position in checker_positions
                if isinstance(position, dict) and "x" in position
            })
            z_values = sorted({
                round(float(position["z"]), 4)
                for _, position in checker_positions
                if isinstance(position, dict) and "z" in position
            })
            if not checker_square_tags and len(x_values) >= 2 and len(z_values) >= 2:
                x_steps = [b - a for a, b in zip(x_values, x_values[1:]) if b - a > 0.75]
                z_steps = [b - a for a, b in zip(z_values, z_values[1:]) if b - a > 0.75]
                if x_steps and z_steps:
                    step_x = min(x_steps)
                    step_z = min(z_steps)
                    lines.append(
                        "CHECKERS COORDINATE LATTICE (authoritative): use these live square-center spacings, "
                        f"x step={step_x:.4f}, z step={step_z:.4f}. Do not use sqrt(2) or visual pixel offsets. "
                        "A normal diagonal changes x and z by exactly one listed step; a capture changes both by two steps."
                    )
                    lines.append(
                        "Checker source positions (use exact live values; target must be another square center): "
                        + "; ".join(
                            f"{guid}=({float(position.get('x', 0)):.4f},{float(position.get('z', 0)):.4f})"
                            for guid, position in checker_positions
                            if isinstance(position, dict) and "x" in position and "z" in position
                        )
                    )
        if game.strip().lower() == "checkers":
            # Checkers needs only piece identity/position and the canonical
            # square centers. The previous full-scene and tagged-object dumps
            # repeated the same data and consumed a large fraction of the
            # local vision model's context window.
            lines.append("CHECKERS LIVE PIECES (authoritative; one row per occupied piece):")
            for obj in compact_objects:
                if str(obj.get("type", "")).lower() != "checker":
                    continue
                position = obj.get("position") or {}
                lines.append(json.dumps({
                    "guid": obj.get("guid"),
                    "name": obj.get("name"),
                    "position": {
                        "x": position.get("x"),
                        "y": position.get("y"),
                        "z": position.get("z"),
                    },
                    "locked": obj.get("locked"),
                    "zone_guids": obj.get("zone_guids") or [],
                }, ensure_ascii=False, separators=(",", ":")))
            lines.append("CHECKERS SQUARE CENTERS (authoritative destination tags; use the tag and its x/z center):")
            for obj in compact_objects:
                if not _is_square_zone(obj):
                    continue
                tags = [str(tag).strip().upper() for tag in obj.get("tags") or []]
                square_tags = [tag for tag in tags if re.fullmatch(r"[A-H][1-8]", tag)]
                position = obj.get("position") or {}
                for tag in square_tags:
                    lines.append(f"{tag}=({position.get('x')},{position.get('z')})")
        else:
            lines.append("All live top-level table objects (authoritative inventory; catalog entries are excluded):")
            for obj in compact_objects:
                lines.append(json.dumps({
                    "guid": obj.get("guid"),
                    "name": obj.get("name"),
                    "type": obj.get("type"),
                    "tags": obj.get("tags") or [],
                    "position": obj.get("position"),
                    "rotation": obj.get("rotation"),
                    "bounds": obj.get("bounds"),
                    "locked": obj.get("locked"),
                    "zone_guids": obj.get("zone_guids") or [],
                }, ensure_ascii=False, separators=(",", ":")))
            lines.append("Tagged board objects (use tags and positions as structured evidence):")
            lines.extend(tagged or ["none found"])
    except (OSError, RuntimeError, ValueError, TTSBridgeError) as exc:
        lines.append(f"Live board object inspection unavailable this turn: {exc}")

    # Vision is intentionally independent from list_objects. A TTS callback
    # timeout must not prevent the image from reaching a vision-capable model.
    try:
        vision_setting = backend_config_store.load().get("vision", os.getenv("AI_GAME_VISION", "1"))
        vision_enabled = str(vision_setting).strip().lower() in {"1", "true", "yes", "on"}
        vision_requested = should_capture_game_vision(message, game, lifecycle)
        if vision_enabled and vision_requested:
            if os.getenv("AI_VISION_SET_CAMERA", "1").strip().lower() in {"1", "true", "yes", "on"}:
                try:
                    bridge.request("set_camera", {
                        "player_color": os.getenv("AI_VISION_PLAYER_COLOR", "White"),
                        "position": {"x": float(os.getenv("AI_VISION_X", "0")), "y": float(os.getenv("AI_VISION_Y", "0")), "z": float(os.getenv("AI_VISION_Z", "0"))},
                        "pitch": float(os.getenv("AI_VISION_PITCH", "60")),
                        "yaw": float(os.getenv("AI_VISION_YAW", "180")),
                        "distance": float(os.getenv("AI_VISION_DISTANCE", "35")),
                        "mode": "ThirdPerson",
                    })
                except (OSError, RuntimeError, ValueError, TTSBridgeError) as exc:
                    lines.append(f"Camera reposition unavailable; capturing current view: {exc}")
            time.sleep(float(os.getenv("AI_VISION_SETTLE_SECONDS", "0.75")))
            image = _capture_view(
                int(os.getenv("AI_VISION_LEFT", "0")),
                int(os.getenv("AI_VISION_TOP", "0")),
                int(os.getenv("AI_VISION_WIDTH", "1920")),
                int(os.getenv("AI_VISION_HEIGHT", "1080")),
                int(os.getenv("AI_VISION_MAX_WIDTH", "1600")),
                int(os.getenv("AI_VISION_JPEG_QUALITY", "85")),
            )
            context["image_base64"] = base64.b64encode(image.data).decode("ascii")
            context["mime_type"] = "image/jpeg"
            _record_trace(
                "ai_vision_capture",
                game=game,
                lifecycle=lifecycle,
                attached=True,
                bytes=len(image.data),
                rectangle={
                    "left": int(os.getenv("AI_VISION_LEFT", "0")),
                    "top": int(os.getenv("AI_VISION_TOP", "0")),
                    "width": int(os.getenv("AI_VISION_WIDTH", "1920")),
                    "height": int(os.getenv("AI_VISION_HEIGHT", "1080")),
                },
            )
            lines.append("A fresh overhead camera snapshot is attached; reconcile it with the tagged object data.")
        elif vision_enabled:
            _record_trace(
                "ai_vision_skipped",
                game=game,
                lifecycle=lifecycle,
                reason="vision is reserved for explicit move preparation",
            )
    except Exception as exc:
        _record_trace("ai_vision_capture", game=game, lifecycle=lifecycle, attached=False, error=str(exc))
        lines.append(f"Vision snapshot unavailable this turn: {exc}")
    context["text"] = "\n".join(lines)
    return context


def _ai_observation_bridge_timeout() -> float:
    """Allow long-running TTS observations while keeping a bounded deadline."""
    try:
        return max(
            1.0,
            min(float(os.getenv("AI_OBSERVATION_TTS_TIMEOUT", "300")), 300.0),
        )
    except (TypeError, ValueError):
        return 300.0


def _ai_gameplay_request(action: str, args: dict[str, Any]) -> dict[str, Any]:
    """Route Kill Team chat placement through the semantic runtime."""
    if action == "killteam_place_operative":
        operative_id = str(args.get("operative_id", "")).strip()
        if not operative_id:
            raise ValueError("killteam placement requires operative_id")
        try:
            position = {axis: float(args[axis]) for axis in ("x", "y", "z")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("killteam placement requires numeric x, y, and z") from exc
        return _killteam_call("place_operative", operative_id, [position])
    if action == "killteam_deploy_test_model":
        return _killteam_call("deploy_test_model")
    if action == "killteam_begin_setup_validation":
        action_id = str(args.get("action_id", "")).strip()
        if not action_id:
            raise ValueError("Kill Team setup validation requires action_id")
        return _killteam_call(
            "begin_setup_validation",
            action_id=action_id,
        )
    if action == "killteam_complete_setup_validation":
        acknowledged_by = str(args.get("acknowledged_by", "")).strip()
        if acknowledged_by.casefold() not in {"red", "host"}:
            raise ValueError("Red or host acknowledgment is required")
        return _killteam_call(
            "complete_setup_validation",
            acknowledged_by=acknowledged_by,
        )
    return bridge.request(action, args)


def _ai_observation_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one gateway-approved read-only observation and compact its result."""
    if name == "tts_ping":
        return bridge.request(
            "ping",
            {},
            timeout=_ai_observation_bridge_timeout(),
        )
    if name == "tts_killteam_setup":
        return _killteam_setup_sync(
            ai_team=str(args.get("ai_team", "ai")),
            units_per_inch=float(args.get("units_per_inch", 1.0)),
            ai_dice_count=int(args.get("ai_dice_count", 1)),
            opponent_dice_count=int(args.get("opponent_dice_count", 1)),
        )
    if name == "tts_killteam_probe_collection":
        return bridge.request(
            "killteam_probe_collection",
            {
                "query_tags_json": json.dumps(
                    list(SAVE_131_FIXTURE_PROFILE.query_tags),
                    separators=(",", ":"),
                ),
                "required_guids_json": json.dumps(
                    list(SAVE_131_FIXTURE_PROFILE.required_guids),
                    separators=(",", ":"),
                ),
                "snap_point_tags_json": json.dumps(
                    [SAVE_131_FIXTURE_PROFILE.start_snap_tag],
                    separators=(",", ":"),
                ),
                "probe_stage": str(args.get("stage", "")),
                "probe_index": int(args.get("index", 1)),
                "probe_item_index": int(args.get("item_index", 1)),
            },
            timeout=_ai_observation_bridge_timeout(),
        )
    if name == "tts_killteam_observe":
        return _killteam_call("observe")
    if name == "tts_killteam_get_roster":
        return _killteam_call("get_roster")
    if name == "tts_killteam_probe_line_of_sight":
        eye_local = args.get("eye_local")
        return _killteam_call(
            "probe_line_of_sight",
            str(args["attacker_id"]).strip(),
            str(args["target_id"]).strip(),
            eye_local=eye_local,
            debug=False,
        )
    if name == "tts_get_object":
        return bridge.request(
            "get_object",
            {"guid": str(args["guid"]).strip()},
            timeout=_ai_observation_bridge_timeout(),
        )
    if name == "tts_list_objects":
        return bridge.request(
            "list_objects",
            {
                "name_contains": str(args.get("name_contains", "")),
                "tag": str(args.get("tag", "")),
                "max_results": max(1, min(int(args.get("max_results", 200)), 1000)),
                "compact": bool(args.get("compact", True)),
            },
            timeout=_ai_observation_bridge_timeout(),
        )
    if name == "tts_search_scene":
        reference = str(args.get("reference", "")).strip()
        listing = _ai_observation_tool("tts_list_objects", {"max_results": 1000, "compact": True})
        objects = listing.get("objects", []) if isinstance(listing, dict) else []
        ranked = rank_scene_objects(reference, objects if isinstance(objects, list) else [], int(args.get("max_results", 10)))
        return {"reference": reference, "count": len(ranked), "candidates": ranked}
    if name == "tts_find_nearest_objects":
        request_args: dict[str, Any] = {
            "name_contains": str(args.get("name_contains", "")),
            "tag": str(args.get("tag", "")),
            "max_results": max(1, min(int(args.get("max_results", 10)), 50)),
        }
        if str(args.get("reference_guid", "")).strip():
            request_args["guid"] = str(args["reference_guid"]).strip()
        else:
            request_args["position"] = {axis: float(args[axis]) for axis in ("x", "y", "z")}
        return bridge.request("find_nearest_objects", request_args, timeout=_ai_observation_bridge_timeout())
    if name == "tts_find_objects_in_region":
        request_args = {
            "minimum": {axis: float(args[f"minimum_{axis}"]) for axis in ("x", "y", "z")},
            "maximum": {axis: float(args[f"maximum_{axis}"]) for axis in ("x", "y", "z")},
            "name_contains": str(args.get("name_contains", "")),
            "tag": str(args.get("tag", "")),
            "max_results": max(1, min(int(args.get("max_results", 50)), 50)),
        }
        return bridge.request("find_objects_in_region", request_args, timeout=_ai_observation_bridge_timeout())
    if name == "tts_get_zone_objects":
        return bridge.request(
            "get_zone_objects",
            {
                "guid": str(args["guid"]).strip(),
                "ignore_tags": bool(args.get("ignore_tags", False)),
            },
            timeout=_ai_observation_bridge_timeout(),
        )
    if name == "tts_get_scene_summary":
        maximum = max(1, min(int(args.get("max_results", 50)), 50))
        result = _ai_observation_tool("tts_list_objects", {"max_results": maximum, "compact": True})
        objects = result.get("objects", []) if isinstance(result, dict) else []
        compact = [
            {
                key: obj.get(key)
                for key in ("guid", "name", "type", "tags", "position", "rotation", "bounds", "locked", "zone_guids")
            }
            for obj in objects[:maximum]
            if isinstance(obj, dict)
        ]
        return {"count": len(compact), "objects": compact, "truncated": bool(result.get("truncated")) if isinstance(result, dict) else False}
    if name == "tts_capture_view":
        image = _capture_view(
            int(args.get("left", 0)), int(args.get("top", 0)),
            int(args.get("width", 1920)), int(args.get("height", 1080)),
            int(args.get("max_width", 1600)), int(args.get("jpeg_quality", 85)),
        )
        return {"image_base64": base64.b64encode(image.data).decode("ascii"), "mime_type": "image/jpeg"}
    if name == "tts_capture_view_info":
        _, metadata = _capture_view_snapshot(
            int(args.get("left", 0)), int(args.get("top", 0)),
            int(args.get("width", 1920)), int(args.get("height", 1080)),
            int(args.get("max_width", 1600)),
        )
        metadata["healthy"] = not metadata["blank_frame_suspected"]
        return metadata
    raise ValueError(f"unsupported AI observation tool: {name}")


@mcp.tool()
def tts_capture_view(
    left: int = 0,
    top: int = 0,
    width: int = 1920,
    height: int = 1080,
    max_width: int = 1600,
    jpeg_quality: int = 85,
) -> MCPImage:
    """Capture a screen region containing the visible Tabletop Simulator view."""
    return _capture_view(left, top, width, height, max_width, jpeg_quality)


@mcp.tool()
def tts_capture_view_info(
    left: int = 0,
    top: int = 0,
    width: int = 1920,
    height: int = 1080,
    max_width: int = 1600,
) -> dict[str, Any]:
    """Capture a view and return health/geometry metadata without image content."""
    _, metadata = _capture_view_snapshot(left, top, width, height, max_width)
    metadata["healthy"] = not metadata["blank_frame_suspected"]
    return metadata


@mcp.tool()
def tts_calibrate_view(
    left: int = 0,
    top: int = 0,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Validate a screen rectangle and list available monitors for TTS capture."""
    with mss.mss() as capture:
        monitors = [
            {
                "index": index,
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
            }
            for index, monitor in enumerate(capture.monitors)
        ]
    metadata = tts_capture_view_info(left, top, width, height, max_width=width)
    return {
        "healthy": metadata["healthy"],
        "rectangle": metadata["rectangle"],
        "capture": metadata,
        "monitors": monitors,
        "instructions": (
            "Set the rectangle to the monitor/window containing the TTS view. "
            "A healthy capture should not be blank or uniformly colored."
        ),
    }


@mcp.tool()
async def tts_set_camera_and_capture(
    player_color: str = "White",
    x: float = 0,
    y: float = 0,
    z: float = 0,
    pitch: float = 60,
    yaw: float = 180,
    distance: float = 35,
    left: int = 0,
    top: int = 0,
    width: int = 1920,
    height: int = 1080,
    max_width: int = 1600,
    jpeg_quality: int = 85,
    settle_seconds: float = 0.75,
) -> MCPImage:
    """Move the TTS camera, wait for rendering to settle, and capture the view."""
    await tts_set_camera(
        player_color=player_color,
        x=x,
        y=y,
        z=z,
        pitch=pitch,
        yaw=yaw,
        distance=distance,
        mode="ThirdPerson",
    )
    await asyncio.sleep(max(0.0, min(settle_seconds, 5.0)))
    return await asyncio.to_thread(
        _capture_view, left, top, width, height, max_width, jpeg_quality
    )


@mcp.tool()
async def tts_focus_object_and_capture(
    guid: str,
    player_color: str = "White",
    pitch: float = 60,
    yaw: float = 180,
    distance_multiplier: float = 4,
    left: int = 0,
    top: int = 0,
    width: int = 1920,
    height: int = 1080,
    max_width: int = 1600,
    jpeg_quality: int = 85,
    settle_seconds: float = 0.75,
) -> MCPImage:
    """Aim the camera at an object using its bounds and capture a close view."""
    if distance_multiplier <= 0:
        raise ValueError("distance_multiplier must be positive")
    object_state = await tts_get_object(guid)
    target = object_state.get("bounds") or {}
    target_position = target.get("center") or object_state.get("position")
    if not isinstance(target_position, dict):
        raise ValueError(f"Object {guid} has no usable position")
    size = target.get("size") or {}
    largest_extent = max(
        abs(float(size.get(axis, 0) or 0)) for axis in ("x", "y", "z")
    )
    distance = max(8.0, largest_extent * distance_multiplier + 4.0)
    await tts_set_camera(
        player_color=player_color,
        x=float(target_position.get("x", 0)),
        y=float(target_position.get("y", 0)),
        z=float(target_position.get("z", 0)),
        pitch=pitch,
        yaw=yaw,
        distance=distance,
        mode="ThirdPerson",
    )
    await asyncio.sleep(max(0.0, min(settle_seconds, 5.0)))
    return await asyncio.to_thread(
        _capture_view, left, top, width, height, max_width, jpeg_quality
    )


@mcp.tool()
async def tts_wait_for_object_settle(
    guid: str,
    timeout_seconds: float = 5,
    poll_seconds: float = 0.1,
) -> dict[str, Any]:
    """Wait until an object stops smooth movement and report its final state."""
    timeout = max(0.0, min(timeout_seconds, 30.0))
    interval = max(0.05, min(poll_seconds, 1.0))
    started = time.monotonic()
    last_state: dict[str, Any] = {}
    previous_position: dict[str, float] | None = None
    stable_samples = 0
    while True:
        last_state = await tts_get_object(guid)
        if last_state.get("smooth_moving") is False:
            return {
                "settled": True,
                "elapsed_seconds": time.monotonic() - started,
                "object": last_state,
            }
        # Older bridge scripts may omit isSmoothMoving. In that case require
        # two consecutive unchanged position samples instead of treating the
        # first response as settled.
        if last_state.get("smooth_moving") is None:
            position = last_state.get("position") or {}
            try:
                current_position = {
                    axis: float(position[axis]) for axis in ("x", "y", "z")
                }
            except (KeyError, TypeError, ValueError):
                current_position = None
            if current_position is not None and previous_position is not None:
                if max(
                    abs(current_position[axis] - previous_position[axis])
                    for axis in ("x", "y", "z")
                ) <= 0.02:
                    stable_samples += 1
                else:
                    stable_samples = 0
                if stable_samples >= 2:
                    return {
                        "settled": True,
                        "elapsed_seconds": time.monotonic() - started,
                        "object": last_state,
                    }
            previous_position = current_position
        if time.monotonic() - started >= timeout:
            return {
                "settled": False,
                "elapsed_seconds": time.monotonic() - started,
                "object": last_state,
            }
        await asyncio.sleep(interval)


@mcp.tool()
async def tts_set_object_name(guid: str, name: str) -> dict[str, Any]:
    """Set an object's visible name."""
    return await call_tts("set_object_name", {"guid": guid, "name": name})


@mcp.tool()
async def tts_set_object_lock(guid: str, locked: bool) -> dict[str, Any]:
    """Lock or unlock an object."""
    return await call_tts("set_object_lock", {"guid": guid, "locked": locked})


@mcp.tool()
async def tts_spawn_builtin(
    object_type: str,
    x: float = 0,
    y: float = 3,
    z: float = 0,
    rotation_x: float = 0,
    rotation_y: float = 0,
    rotation_z: float = 0,
    scale_x: float = 1,
    scale_y: float = 1,
    scale_z: float = 1,
    name: str = "",
    locked: bool = False,
) -> dict[str, Any]:
    """Spawn a built-in TTS object type, such as BlockSquare, Chess_Pawn, or Die_6."""
    return await call_tts(
        "spawn_builtin",
        {
            "object_type": object_type,
            "position": {"x": x, "y": y, "z": z},
            "rotation": {
                "x": rotation_x,
                "y": rotation_y,
                "z": rotation_z,
            },
            "scale": {"x": scale_x, "y": scale_y, "z": scale_z},
            "name": name,
            "locked": locked,
        },
        # Spawning can require several simulation frames.
    )


@mcp.tool()
async def tts_destroy_object(guid: str) -> dict[str, Any]:
    """Destroy one object by GUID. This is irreversible unless the user undoes or reloads."""
    return await call_tts("destroy_object", {"guid": guid})


@mcp.tool()
async def tts_broadcast(message: str) -> dict[str, Any]:
    """Broadcast a text message to all players in the current game."""
    return await call_tts("broadcast", {"message": message})


@mcp.tool()
async def tts_get_scripts() -> dict[str, Any]:
    """Read Global/Object Lua scripts and UI XML exposed by TTS's editor API."""
    states = await asyncio.to_thread(bridge.get_scripts)
    return {"count": len(states), "script_states": states}


@mcp.tool()
async def tts_recent_events(limit: int = 50) -> dict[str, Any]:
    """Read recent TTS print, Lua error, save, object-created, and bridge events."""
    events = await asyncio.to_thread(bridge.recent_events, limit)
    return {"count": len(events), "events": events}


@mcp.tool()
def tts_recent_trace(limit: int = 100) -> dict[str, Any]:
    """Return recent MCP tool and outbound TTS activation trace records."""
    events = _recent_trace(limit)
    return {
        "count": len(events),
        "events": events,
        "trace_enabled": _TRACE_ENABLED,
        "trace_log": _TRACE_LOG_PATH,
    }


@mcp.tool()
async def tts_recent_chat(limit: int = 50) -> dict[str, Any]:
    """Read recent in-game chat messages received from Tabletop Simulator."""
    messages = await asyncio.to_thread(bridge.recent_chat, limit)
    return {"count": len(messages), "messages": messages}


@mcp.tool()
async def tts_wait_for_chat(timeout_seconds: float = 30) -> dict[str, Any]:
    """Wait for the next in-game chat message from Tabletop Simulator."""
    return await asyncio.to_thread(bridge.wait_for_chat, timeout_seconds)


@mcp.tool()
async def tts_ai_chat(
    message: str,
    conversation_id: str = "",
    timeout_seconds: float = 300,
) -> dict[str, Any]:
    """Send a prompt to the local AI gateway with an optional fresh conversation."""
    if not message.strip():
        raise ValueError("message must not be empty")
    timeout = max(5.0, min(float(timeout_seconds), 600.0))

    host = os.getenv("TTS_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("TTS_HTTP_PORT", "8765"))
    url = f"http://{host}:{port}/chat"
    payload: dict[str, Any] = {"message": message, "player": {"color": "Codex"}}
    if conversation_id.strip():
        payload["conversation_id"] = conversation_id.strip()
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    def send() -> dict[str, Any]:
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP AI gateway returned {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach HTTP AI gateway: {exc.reason}") from exc

        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError("HTTP AI gateway returned a non-object JSON response")
        return result

    return await asyncio.to_thread(send)


if __name__ == "__main__":
    http_gateway: HttpGateway | None = None
    _record_trace(
        "process_start",
        component="mcp_server",
        mode="gateway_only" if os.getenv("TTS_GATEWAY_ONLY", "").strip().lower() in {"1", "true", "yes", "on"} else "mcp_stdio",
    )
    try:
        http_gateway = HttpGateway(context_provider=_ai_game_context)
        # The gateway remains import-cycle free, while command execution still
        # goes through the same allowlisted External Editor bridge as MCP.
        http_gateway.configure_gameplay(_ai_gameplay_request)
        http_gateway.configure_observation_tools(_ai_observation_tool)
        http_gateway.configure_bridge_response(
            lambda response: bridge.deliver_response(response, transport="http")
        )
        http_gateway.start()
        if os.getenv("TTS_GATEWAY_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
            # Useful for checking TTS -> backend connectivity without feeding
            # interactive terminal input into the MCP stdio JSON-RPC stream.
            threading.Event().wait()
        else:
            mcp.run(transport="stdio")
    except OSError as exc:
        raise RuntimeError(
            "Could not start the TTS HTTP gateway on the configured host/port. "
            "Set TTS_HTTP_PORT to a free local port."
        ) from exc
    finally:
        if http_gateway is not None:
            http_gateway.close()
        bridge.close()
        _record_trace("process_stop", component="mcp_server")
