from __future__ import annotations

import asyncio
import copy
from typing import Any
import unittest
from unittest.mock import patch
import json

from tts_mcp.app.http_gateway import ChatBackend, _public_ai_text
from tts_mcp.runtime.gameplay_runtime import ParsedCommand


def _load_tts_server():
    try:
        from tts_mcp.app import server as tts_server
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest("mcp dependency unavailable in this test environment") from exc
    return tts_server


class PublicAITextTests(unittest.TestCase):
    def test_removes_raw_board_state_but_keeps_natural_language(self) -> None:
        text = (
            "I checked the board.\n"
            "{\"guid\":\"abcdef\",\"position\":{\"x\":1},\"rotation\":{\"y\":90}}\n"
            "White Pawn: position=(1, 2, 3), rotation=(0, 90, 0)\n"
            "The game is ready."
        )

        result = _public_ai_text(text)

        self.assertIn("I checked the board.", result)
        self.assertIn("The game is ready.", result)
        self.assertNotIn("abcdef", result)
        self.assertNotIn("rotation", result.lower())

    def test_removes_machine_commands_from_player_text(self) -> None:
        result = _public_ai_text("I will move now.\nMOVE[abcdef,1,2,3]")

        self.assertEqual(result, "I will move now.")

    def test_sanitizes_responses_without_commands(self) -> None:
        backend = ChatBackend()
        result = backend._finalize_result({
            "text": "Board state:\n{\"guid\":\"abcdef\",\"position\":{\"x\":1}}"
        }, {})

        self.assertEqual(result["text"], "Board state:")

    def test_rejects_empty_and_json_only_player_text(self) -> None:
        self.assertEqual(_public_ai_text(" \n\t "), "")
        self.assertEqual(_public_ai_text('{\n  "text": "hello"\n}'), "")

    def test_removes_blank_lines_from_player_text(self) -> None:
        self.assertEqual(_public_ai_text("First line.\n\n\nSecond line."), "First line.\nSecond line.")

    def test_removes_excessive_spacing_from_player_text(self) -> None:
        text = "First line.\n" + (" " * 120) + "Second line.\t\tDone."

        self.assertEqual(_public_ai_text(text), "First line.\nSecond line. Done.")

    def test_authoritative_scene_state_is_not_injected_automatically(self) -> None:
        backend = ChatBackend()
        backend.context_provider = lambda: {
            "text": 'CHECKERS LIVE PIECES (authoritative):\n{"guid":"piece-1","position":{"x":1,"z":2}}',
            "image_base64": "ZmFrZQ==",
            "mime_type": "image/jpeg",
        }
        backend.controller_provider = lambda: {"active_game": "checkers"}

        _, messages = backend._messages({}, "What is the current board state?")
        user_content = messages[-1]["content"]
        user_text = user_content if isinstance(user_content, str) else "\n".join(
            str(part.get("text", ""))
            for part in user_content
            if isinstance(part, dict) and part.get("type") == "text"
        )

        self.assertNotIn("piece-1", user_text)
        self.assertIn("What is the current board state?", user_text)

    def test_chat_messages_start_without_automatic_scene_context(self) -> None:
        backend = ChatBackend()
        backend.context_provider = lambda: (_ for _ in ()).throw(
            AssertionError("ordinary chat must not inspect the scene")
        )
        backend.controller_provider = lambda: {"active_game": "checkers"}

        _, messages = backend._messages({}, "Hello there")

        user_content = messages[-1]["content"]
        self.assertEqual(user_content, "Hello there")
        self.assertFalse(any("Current Tabletop Simulator state" in str(item.get("content", "")) for item in messages))

    def test_http_backend_can_call_bounded_read_only_tool_before_answering(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "format": "openai",
            "model": "test-model",
        })
        backend.controller_provider = lambda: {}
        tool_calls = []
        backend.configure_observation_tools({
            "tts_search_scene": lambda args: tool_calls.append(args) or {
                "reference": args["reference"],
                "count": 1,
                "candidates": [{"guid": "abcdef", "name": "Red Pawn"}],
            }
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({
                "choices": [{"message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "tts_search_scene",
                            "arguments": '{"reference":"red pawn"}',
                        },
                    }],
                }}]
            })),
            Response(json.dumps({
                "choices": [{"message": {
                    "role": "assistant",
                    "content": "I found the red pawn.",
                }}]
            })),
        ])

        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
            result = backend.complete({"message": "Where is the red pawn?", "conversation_id": "tool-test"})

        self.assertEqual(result["text"], "I found the red pawn.")
        self.assertEqual(tool_calls, [{"reference": "red pawn", "max_results": 10}])
        self.assertEqual(request.call_count, 2)
        first_payload = json.loads(request.call_args_list[0].args[0].data.decode("utf-8"))
        second_payload = json.loads(request.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("tools", first_payload)
        self.assertNotIn("Current Tabletop Simulator state", json.dumps(first_payload))
        self.assertIn('"role":"tool"', json.dumps(second_payload, separators=(",", ":")))

    def test_unknown_or_mutating_tool_calls_are_rejected(self) -> None:
        backend = ChatBackend()
        with self.assertRaises(ValueError):
            backend._validate_observation_call({
                "name": "tts_move_object",
                "arguments": {"guid": "abcdef"},
            })

    def test_generic_http_backend_uses_strict_json_tool_fallback(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:9000/chat",
            "format": "generic",
        })
        backend.controller_provider = lambda: {}
        backend.configure_observation_tools({
            "tts_get_object": lambda args: {"guid": args["guid"], "name": "Red Pawn"}
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({"text": json.dumps({
                "tool_call": {"name": "tts_get_object", "arguments": {"guid": "abcdef"}}
            })})),
            Response(json.dumps({"text": "That is the red pawn."})),
        ])
        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "What is abcdef?", "conversation_id": "fallback-test"})

        self.assertEqual(result["text"], "That is the red pawn.")

    def test_requested_screenshot_is_attached_only_after_tool_call(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "format": "openai",
        })
        backend.controller_provider = lambda: {}
        backend.configure_observation_tools({
            "tts_capture_view": lambda args: {"image_base64": "ZmFrZQ==", "mime_type": "image/jpeg"}
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({"choices": [{"message": {
                "tool_calls": [{"id": "capture-1", "type": "function", "function": {
                    "name": "tts_capture_view", "arguments": "{}"
                }}]
            }}]})),
            Response(json.dumps({"choices": [{"message": {"content": "I can see the table."}}]})),
        ])
        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
            result = backend.complete({"message": "Look at the current table.", "conversation_id": "image-test"})

        self.assertEqual(result["text"], "I can see the table.")
        second_payload = json.loads(request.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("data:image/jpeg;base64,ZmFrZQ==", json.dumps(second_payload))

    def test_ollama_tool_screenshot_is_preserved_on_follow_up_request(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })
        backend.controller_provider = lambda: {}
        backend.configure_observation_tools({
            "tts_capture_view": lambda args: {
                "image_base64": "ZmFrZQ==",
                "mime_type": "image/jpeg",
            }
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({"message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "capture-ollama", "function": {
                    "name": "tts_capture_view", "arguments": "{}"
                }}],
            }})),
            Response(json.dumps({"message": {
                "role": "assistant", "content": "I inspected the board."
            }})),
        ])
        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
            result = backend.complete({"message": "Inspect the board.", "conversation_id": "ollama-image-test"})

        self.assertEqual(result["text"], "I inspected the board.")
        second_payload = json.loads(request.call_args_list[1].args[0].data.decode("utf-8"))
        second_messages = second_payload["messages"]
        self.assertTrue(any(message.get("images") == ["ZmFrZQ=="] for message in second_messages))

    def test_only_one_visual_observation_is_executed_per_turn(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "format": "openai",
        })
        captures = []
        backend.configure_observation_tools({
            "tts_capture_view": lambda _args: captures.append(True) or {
                "image_base64": "ZmFrZQ==",
                "mime_type": "image/jpeg",
            }
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({"choices": [{"message": {
                "role": "assistant",
                "tool_calls": [
                    {"id": "capture-1", "type": "function", "function": {"name": "tts_capture_view", "arguments": "{}"}},
                    {"id": "capture-2", "type": "function", "function": {"name": "tts_capture_view", "arguments": "{}"}},
                ],
            }}]})),
            Response(json.dumps({"choices": [{"message": {"content": "I reviewed one current view."}}]})),
        ])
        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "Review the board visually.", "conversation_id": "image-budget-test"})

        self.assertEqual(result["text"], "I reviewed one current view.")
        self.assertEqual(len(captures), 1)

    def test_failed_visual_observation_does_not_consume_visual_budget(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })
        captures = []
        backend.configure_observation_tools({
            "tts_capture_view": lambda _args: captures.append(True) or {
                "ok": False,
                "error": "capture unavailable",
            }
        })

        result, image_count = backend._invoke_observation_with_image_budget(
            {"name": "tts_capture_view", "arguments": {}}, 0
        )

        self.assertFalse(result["ok"])
        self.assertEqual(image_count, 0)
        self.assertEqual(len(captures), 1)

    def test_observation_failure_cannot_be_reported_as_verified_missing_lua(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })
        backend.controller_provider = lambda: {}
        backend.configure_observation_tools({
            "tts_list_objects": lambda _args: {
                "ok": False,
                "error": "TTS observation callback timed out",
            }
        })

        class Response:
            def __init__(self, body: dict):
                self.body = json.dumps(body).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response({"message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "list-1", "function": {
                    "name": "tts_list_objects", "arguments": "{}"
                }}],
            }}),
            Response({"message": {
                "role": "assistant",
                "content": (
                    "I'm still unable to see the board. The necessary helper script "
                    "(`tts_mcp_global.lua`) isn't active in your Global scripts folder."
                ),
            }}),
        ])

        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "Make your move.", "conversation_id": "observation-failure-test"})

        self.assertNotIn("tts_mcp_global.lua", result["text"])
        self.assertIn("couldn't inspect", result["text"].lower())
        self.assertIn("TTS observation callback timed out", result["text"])

    def test_failed_execution_is_reported_without_dispatching_more_actions(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": ""}
        calls = []

        def request(action: str, args: dict) -> dict:
            calls.append((action, args))
            if action == "get_object":
                return {"guid": args["guid"], "position": {"x": 9, "y": 2, "z": 9}}
            return {"ok": True}

        backend.configure_gameplay(
            controller_provider=lambda: {"state": "running", "active_game": ""},
            request=request,
            propose=lambda _: "unused",
        )
        result = backend._finalize_result(
            {"text": "I will move. MOVE[abcdef,1,2,3] MOVE[123456,4,5,6]"},
            {},
        )

        self.assertIn("couldn't complete", result["text"].lower())
        self.assertTrue(result["execution"]["stopped"])
        self.assertFalse(any(action == "move_object" and args["guid"] == "123456" for action, args in calls))

    def test_killteam_your_turn_request_invokes_autonomous_tactical_turn(self) -> None:
        backend = ChatBackend()
        request_calls = []
        turn_completed = []

        def request(action: str, args: dict) -> dict:
            request_calls.append((action, args))
            return {
                "status": "passed",
                "trigger": args.get("trigger", ""),
                "actions": [
                    {"action": "activate_operative", "result": {"operative_id": "plague-warrior-01"}},
                    {"action": "shoot", "result": {"target_id": "target-01", "weapon_id": "boltgun"}},
                    {"action": "end_activation", "result": {"status": "ended"}},
                ],
                "initiative_side": "opponent",
                "initiative_token": {"status": "moved"},
                "turn_owner": "opponent",
                "turn_status": "passed",
                "turn_sequence": 1,
                "revision": 7,
            }

        backend.configure_gameplay(
            controller_provider=lambda: {"state": "running", "active_game": "killteam"},
            request=request,
            propose=lambda _: "unused",
            turn_completed=lambda side: turn_completed.append(side),
        )

        result = backend.complete({"message": "Your turn", "conversation_id": "killteam-turn-test"})

        self.assertTrue(result["autonomous"])
        self.assertTrue(result["initiative_passed"])
        self.assertIn("passed initiative", result["text"].lower())
        self.assertEqual(request_calls, [("killteam_take_tactical_turn", {"trigger": "Your turn"})])
        self.assertEqual(turn_completed, ["ai"])

    def test_large_move_failure_gets_model_visible_ollama_image_review(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })
        backend.controller_provider = lambda: {"state": "running", "active_game": ""}
        backend.configure_observation_tools({
            "tts_capture_view": lambda _args: {
                "image_base64": "ZmFrZQ==",
                "mime_type": "image/jpeg",
            }
        })

        def request(action: str, args: dict) -> dict:
            if action == "get_object":
                return {"guid": args["guid"], "position": {"x": 2, "y": 2, "z": 9}}
            return {"ok": True}

        backend.configure_gameplay(
            controller_provider=lambda: {"state": "running", "active_game": ""},
            request=request,
            propose=lambda _: "unused",
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"message": {"content": "The piece is visibly away from the target square."}}).encode()

        with patch("tts_mcp.app.http_gateway.urlopen", return_value=Response()) as outbound:
            result = backend._finalize_result({"text": "MOVE[abcdef,1,2,3]"}, {})

        self.assertIn("Visual review", result["text"])
        payload = json.loads(outbound.call_args.args[0].data.decode("utf-8"))
        self.assertTrue(any(message.get("images") == ["ZmFrZQ=="] for message in payload["messages"]))

    def test_observation_registry_exposes_direct_object_listing(self) -> None:
        from tts_mcp.app.http_gateway import OBSERVATION_TOOL_NAMES

        self.assertIn("tts_list_objects", OBSERVATION_TOOL_NAMES)

    def test_observation_registry_exposes_bridge_ping(self) -> None:
        from tts_mcp.app.http_gateway import OBSERVATION_TOOL_NAMES

        self.assertIn("tts_ping", OBSERVATION_TOOL_NAMES)

    def test_observation_registry_exposes_killteam_setup_and_observe(self) -> None:
        from tts_mcp.app.http_gateway import OBSERVATION_TOOL_NAMES

        self.assertIn("tts_killteam_setup", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_setup_ping", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_setup_list_objects", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_observe", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_probe_collection", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_probe_line_of_sight", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_get_roster", OBSERVATION_TOOL_NAMES)
        self.assertIn("tts_killteam_plan_objective_move", OBSERVATION_TOOL_NAMES)

    def test_ai_can_dispatch_killteam_line_of_sight_probe(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_killteam_probe_line_of_sight": lambda args: calls.append(args) or {
                "visible": False,
                "visibility_fraction": 0.0,
                "blocker_guids": ["wall-1"],
            },
        })

        result = backend._invoke_observation({
            "name": "tts_killteam_probe_line_of_sight",
            "arguments": {
                "attacker_id": "plague-warrior-01",
                "target_id": "target-01",
                "eye_local": {"x": 0, "y": 1.2, "z": 0},
            },
        })

        self.assertTrue(result["ok"])
        self.assertFalse(result["visible"])
        self.assertEqual(calls, [{
            "attacker_id": "plague-warrior-01",
            "target_id": "target-01",
            "eye_local": {"x": 0.0, "y": 1.2, "z": 0.0},
        }])

    def test_ai_can_dispatch_dedicated_killteam_roster_observation(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_killteam_get_roster": lambda args: calls.append(args) or {
                "container_guid": "e5adb7",
                "items": [{"name": "Plague Marine Heavy Gunner"}],
            },
        })

        result = backend._invoke_observation({
            "name": "tts_killteam_get_roster",
            "arguments": {},
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["container_guid"], "e5adb7")
        self.assertEqual(calls, [{}])

    def test_ai_can_dispatch_dedicated_killteam_setup_observations(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_killteam_setup_ping": lambda args: calls.append(("ping", args)) or {
                "bridge_version": "2026-07-29-setup-placement-v1",
            },
            "tts_killteam_setup_list_objects": lambda args: calls.append(("list", args)) or {
                "objects": [{"guid": "model-1"}],
            },
        })

        ping = backend._invoke_observation({
            "name": "tts_killteam_setup_ping",
            "arguments": {},
        })
        listing = backend._invoke_observation({
            "name": "tts_killteam_setup_list_objects",
            "arguments": {"name_contains": "warrior", "max_results": 5},
        })

        self.assertTrue(ping["ok"])
        self.assertTrue(listing["ok"])
        self.assertEqual(calls, [
            ("ping", {}),
            ("list", {
                "name_contains": "warrior",
                "tag": "",
                "max_results": 5,
                "compact": True,
            }),
        ])

    def test_setup_turn_exposes_only_placement_context_tools(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam"}

        names = {
            item["function"]["name"]
            for item in backend._observation_tool_specs(setup_turn=True)
        }

        self.assertEqual(names, {
            "tts_killteam_setup_ping",
            "tts_killteam_setup_context",
        })
        with self.assertRaises(ValueError):
            backend._validate_observation_call(
                {"name": "tts_killteam_plan_setup_board", "arguments": {}},
                setup_turn=True,
            )

    def test_setup_context_receives_persisted_placed_guids_for_planning(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "killteam_setup_history": {"placed_guids": ["placed-b", "placed-a", "placed-a"]},
        }
        calls: list[dict] = []
        backend.configure_observation_tools({
            "tts_killteam_setup_context": lambda args: calls.append(dict(args)) or {
                "categories": {"operatives": []},
                "setup_plan": {"batch_size": 2, "recommended_batch": [], "candidates": []},
            },
        })

        result = backend._invoke_observation(
            {"name": "tts_killteam_setup_context", "arguments": {}},
            setup_turn=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [{"max_results": 200, "exclude_guids": ["placed-a", "placed-b"]}])

    def test_ai_can_dispatch_killteam_objective_move_planner(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_killteam_plan_objective_move": lambda args: calls.append(args) or {
                "status": "planned",
                "move_command": "MOVE[ai-1,2.5,1.0,0.0]",
                "target_position": {"x": 2.5, "y": 1.0, "z": 0.0},
            },
        })

        result = backend._invoke_observation({
            "name": "tts_killteam_plan_objective_move",
            "arguments": {"operative_id": "plague-warrior-01"},
        })

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [{"operative_id": "plague-warrior-01"}])
        self.assertEqual(result["move_command"], "MOVE[ai-1,2.5,1.0,0.0]")

    def test_killteam_backend_uses_role_filtered_observation_tools(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam"}

        names = {
            item["function"]["name"]
            for item in backend._observation_tool_specs()
        }

        self.assertIn("tts_killteam_setup", names)
        self.assertIn("tts_killteam_setup_ping", names)
        self.assertIn("tts_killteam_setup_list_objects", names)
        self.assertIn("tts_killteam_observe", names)
        self.assertIn("tts_killteam_probe_line_of_sight", names)
        self.assertIn("tts_ping", names)
        self.assertNotIn("tts_list_objects", names)
        self.assertNotIn("tts_get_object", names)

    def test_ai_can_dispatch_bridge_ping(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_ping": lambda args: calls.append(args) or {
                "bridge_version": "2026-07-26-observation-v4",
                "object_count": 226,
            },
        })

        result = backend._invoke_observation({
            "name": "tts_ping",
            "arguments": {},
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["bridge_version"], "2026-07-26-observation-v4")
        self.assertEqual(calls, [{}])

    def test_killteam_rejects_an_unadvertised_generic_observation_tool(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam"}
        calls = []
        backend.configure_observation_tools({
            "tts_list_objects": lambda args: calls.append(args) or {"objects": []},
        })

        result = backend._invoke_observation({
            "name": "tts_list_objects",
            "arguments": {"max_results": 200},
        })

        self.assertFalse(result["ok"])
        self.assertIn("not available", result["error"])
        self.assertIn("tts_killteam_setup", result["error"])
        self.assertEqual(calls, [])

    def test_ai_can_dispatch_killteam_setup_and_observe_tools(self) -> None:
        backend = ChatBackend()
        calls = []
        backend.configure_observation_tools({
            "tts_killteam_setup": lambda args: calls.append(("setup", args)) or {"status": "ready"},
            "tts_killteam_observe": lambda args: calls.append(("observe", args)) or {
                "observation_id": 1,
                "operatives": {"target-01": {"team": "opponent"}},
            },
        })

        setup = backend._invoke_observation({
            "name": "tts_killteam_setup",
            "arguments": {"ai_team": "ai"},
        })
        observation = backend._invoke_observation({
            "name": "tts_killteam_observe",
            "arguments": {},
        })

        self.assertTrue(setup["ok"])
        self.assertTrue(observation["ok"])
        self.assertEqual(calls, [
            ("setup", {
                "ai_team": "ai",
                "units_per_inch": 1.0,
                "ai_dice_count": 1,
                "opponent_dice_count": 1,
            }),
            ("observe", {}),
        ])

    def test_killteam_observe_failure_is_traced_with_tool_name_and_error(self) -> None:
        backend = ChatBackend()
        traces: list[tuple[str, dict[str, object]]] = []

        def record(event: str, **fields: object) -> str:
            traces.append((event, dict(fields)))
            return "trace-id"

        def observe(_args: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("bridge not ready")

        backend.configure_observation_tools({
            "tts_killteam_observe": observe,
        })

        with patch("tts_mcp.app.http_gateway._record_trace", side_effect=record):
            result = backend._invoke_observation({
                "id": "call-17",
                "name": "tts_killteam_observe",
                "arguments": {},
            })

        self.assertFalse(result["ok"])
        self.assertIn("tts_killteam_observe failed: bridge not ready", result["error"])
        self.assertTrue(any(
            event == "ai_observation_tool_error"
            and fields.get("tool") == "tts_killteam_observe"
            and "bridge not ready" in str(fields.get("error", ""))
            and fields.get("call_id") == "call-17"
            for event, fields in traces
        ))

    def test_killteam_observation_keeps_bounded_terrain_evidence(self) -> None:
        backend = ChatBackend()
        terrain = [{"guid": f"terrain-{index}"} for index in range(75)]
        backend.configure_observation_tools({
            "tts_killteam_observe": lambda _args: {"terrain": terrain, "truncated": False},
        })

        result = backend._invoke_observation({
            "name": "tts_killteam_observe",
            "arguments": {},
        })

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["terrain"]), 75)

    def test_ai_can_dispatch_direct_object_listing_tool(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "format": "openai",
        })
        calls = []
        backend.configure_observation_tools({
            "tts_list_objects": lambda args: calls.append(args) or {
                "objects": [{"guid": "abcdef", "name": "Black Checker"}],
                "count": 1,
            }
        })

        class Response:
            def __init__(self, body: str):
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = iter([
            Response(json.dumps({"choices": [{"message": {
                "role": "assistant",
                "tool_calls": [{"id": "list-1", "type": "function", "function": {
                    "name": "tts_list_objects", "arguments": "{\"max_results\":20}"
                }}]
            }}]})),
            Response(json.dumps({"choices": [{"message": {"content": "I found the checker."}}]})),
        ])
        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "List the board objects.", "conversation_id": "list-test"})

        self.assertEqual(result["text"], "I found the checker.")
        self.assertEqual(calls, [{"max_results": 20, "compact": True}])

    def test_checkers_object_list_keeps_all_pieces_and_tagged_squares_compact(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "checkers"}
        pieces = [
            {
                "guid": f"b{index:05d}", "name": "Black Checker", "type": "Checker",
                "position": {"x": float(index), "y": 1.7, "z": 2.8}, "locked": False,
                "bounds": {"size": {"x": 1, "y": 1, "z": 1}}, "velocity": {"x": 99},
            }
            for index in range(12)
        ]
        squares = [
            {
                "guid": f"z{index:05d}", "name": "", "type": "LayoutZone",
                "tags": [f"{chr(65 + (index % 8))}{1 + (index // 8)}"],
                "position": {"x": float(index), "y": 4.0, "z": float(index // 8)},
                "bounds": {"size": {"x": 20, "y": 20, "z": 20}},
            }
            for index in range(64)
        ]
        backend.configure_observation_tools({
            "tts_list_objects": lambda _args: {"count": 76, "objects": pieces + squares}
        })

        result = backend._invoke_observation({"id": "list-1", "name": "tts_list_objects", "arguments": {}})

        self.assertEqual(len(result["checkers"]["pieces"]), 12)
        self.assertEqual(len(result["checkers"]["squares"]), 64)
        self.assertEqual(result["checkers"]["squares"][-1]["tag"], "H8")
        self.assertNotIn("bounds", result["checkers"]["pieces"][0])
        self.assertNotIn("objects", result)

    def test_checkers_object_list_exposes_only_legal_black_opening_moves(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "checkers"}
        squares = [
            {
                "guid": f"z{index:05d}", "type": "LayoutZone",
                "tags": [f"{chr(65 + file)}{rank}"],
                "position": {"x": float(file * 2), "y": 4.0, "z": float((rank - 4) * 2)},
            }
            for rank in range(1, 9)
            for file in range(8)
            for index in [((rank - 1) * 8) + file]
        ]
        # b-back has an apparently diagonal destination, but b-front already
        # occupies it. Only b-front may make the opening move.
        objects = [
            {"guid": "b00000", "name": "Black Checker", "type": "Checker", "position": {"x": 0.0, "y": 1.7, "z": 4.0}},
            {"guid": "b00001", "name": "Black Checker", "type": "Checker", "position": {"x": 2.0, "y": 1.7, "z": 2.0}},
            *squares,
        ]
        backend.configure_observation_tools({
            "tts_list_objects": lambda _args: {"count": len(objects), "objects": objects}
        })

        result = backend._invoke_observation({"id": "list-1", "name": "tts_list_objects", "arguments": {}})
        moves = result["checkers"]["legal_black_moves"]

        self.assertFalse(any(move["guid"] == "b00000" for move in moves))
        self.assertTrue(any(move["guid"] == "b00001" and move["target"]["z"] == 0.0 for move in moves))

    def test_checkers_object_list_excludes_captured_off_board_checkers_from_moves(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "checkers"}
        squares = [
            {
                "guid": f"z{index:05d}", "type": "LayoutZone",
                "tags": [f"{chr(65 + file)}{rank}"],
                "position": {"x": float(file * 2), "y": 0.0, "z": float((rank - 4) * 2)},
            }
            for rank in range(1, 9)
            for file in range(8)
            for index in [((rank - 1) * 8) + file]
        ]
        objects = [
            {"guid": "onboard", "name": "Black Checker", "type": "Checker", "position": {"x": 2.0, "y": 1.7, "z": 4.0}},
            # Captured pieces are stored outside the board and must not block
            # squares or become legal sources on later turns.
            {"guid": "captured", "name": "Black Checker", "type": "Checker", "position": {"x": 20.0, "y": 1.7, "z": 2.0}},
            *squares,
        ]
        backend.configure_observation_tools({
            "tts_list_objects": lambda _args: {"count": len(objects), "objects": objects}
        })

        result = backend._invoke_observation({"id": "list-off-board", "name": "tts_list_objects", "arguments": {}})
        moves = result["checkers"]["legal_black_moves"]

        self.assertTrue(any(move["guid"] == "onboard" for move in moves))
        self.assertFalse(any(move["guid"] == "captured" for move in moves))

    def test_checkers_object_list_treats_a_stacked_king_as_one_source(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "checkers"}
        squares = [
            {
                "guid": f"z{index:05d}", "type": "LayoutZone",
                "tags": [f"{chr(65 + file)}{rank}"],
                "position": {"x": float(file * 2), "y": 0.0, "z": float((rank - 4) * 2)},
            }
            for rank in range(1, 9)
            for file in range(8)
            for index in [((rank - 1) * 8) + file]
        ]
        objects = [
            {"guid": "kingbase", "name": "Black Checker", "type": "Checker", "position": {"x": 2.0, "y": 1.7, "z": 2.0}},
            {"guid": "kingtop", "name": "Black Checker", "type": "Checker", "position": {"x": 2.0, "y": 2.2, "z": 2.0}},
            *squares,
        ]
        backend.configure_observation_tools({
            "tts_list_objects": lambda _args: {"count": len(objects), "objects": objects}
        })

        result = backend._invoke_observation({"id": "list-king", "name": "tts_list_objects", "arguments": {}})
        moves = result["checkers"]["legal_black_moves"]

        self.assertTrue(moves)
        self.assertTrue(all(move["guid"] == "kingbase" for move in moves))
        self.assertEqual({move["target"]["z"] for move in moves}, {0.0, 4.0})

    def test_invalid_model_checkers_move_is_blocked_instead_of_being_replaced(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": "checkers"}
        selected: list[dict] = []

        class Executor:
            def execute(self, commands, **_kwargs):
                selected.extend(command.args for command in commands)
                return {"executed": [{"action": "move_object", "status": "executed"}], "approval_required": [], "stopped": False}

        backend.command_execution = Executor()
        result = backend._finalize_result({
            "text": "I will move a checker.\nMOVE[f6d7a4,-0.844,1.74,0.937]",
            "_checkers_legal_moves": [{
                "guid": "dccefd",
                "from": "H6",
                "target": {"tag": "G5", "x": -4.6384, "y": 1.7405, "z": 0.9375},
                "kind": "step",
            }],
        }, {})

        self.assertEqual(selected, [])
        self.assertTrue(result["execution"]["stopped"])
        self.assertIn("deterministic checkers", result["text"].lower())

    def test_retry_uses_deterministic_checkers_search_and_not_the_model(self) -> None:
        backend = ChatBackend()
        controller = {"state": "running", "active_game": "checkers"}
        backend.controller_provider = lambda: controller
        columns = {letter: float(index) for index, letter in enumerate("ABCDEFGH")}
        ranks = {rank: float(rank - 1) for rank in range(1, 9)}
        black = {"guid": "black-1", "name": "Black Checker", "type": "Checker", "position": {"x": 0.0, "y": 1.0, "z": 5.0}}
        red = {"guid": "red-1", "name": "Red Checker", "type": "Checker", "position": {"x": 1.0, "y": 1.0, "z": 2.0}}
        objects = [black, red]
        objects.extend(
            {
                "guid": f"zone-{letter}{rank}",
                "type": "LayoutZone",
                "tags": [f"{letter}{rank}"],
                "position": {"x": columns[letter], "y": 0.0, "z": ranks[rank]},
            }
            for letter in columns
            for rank in ranks
        )
        observations = []

        def list_objects(_args: dict) -> dict:
            return {"objects": objects, "count": len(objects)}

        backend.configure_observation_tools({"tts_list_objects": list_objects})

        def request(action: str, args: dict) -> dict:
            if action == "list_objects":
                return list_objects(args)
            if action == "get_object":
                return dict(black)
            if action == "move_object":
                black["position"].update(args["position"])
                return {"ok": True}
            raise AssertionError(f"unexpected action: {action}")

        backend.configure_gameplay(
            controller_provider=lambda: controller,
            request=request,
            propose=lambda _: "unused",
            game_position_provider=lambda: None,
            game_position_saver=lambda position: observations.append(position),
            turn_completed=lambda actor: None,
        )

        result = backend.complete({"message": "Try again"})

        self.assertEqual(result["text"], "Black moves A6 → B5.")
        self.assertTrue(result["autonomous"])
        self.assertEqual(black["position"], {"x": 1.0, "y": 1.0, "z": 4.0})
        self.assertTrue(observations)
        self.assertEqual(observations[-1]["turn"], "red")
        self.assertNotIn("MOVE[", result["text"])

    def test_checkers_turn_trigger_does_not_capture_a_question_about_the_move(self) -> None:
        self.assertTrue(ChatBackend._is_checkers_turn_request("Your move."))
        self.assertTrue(ChatBackend._is_checkers_turn_request("Black, your move"))
        self.assertTrue(ChatBackend._is_checkers_turn_request("Make an opening move"))
        self.assertTrue(ChatBackend._is_checkers_turn_request("Try again"))
        self.assertFalse(ChatBackend._is_checkers_turn_request("What is your move?"))

    def test_generic_model_move_is_blocked_while_checkers_is_active(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": "checkers"}
        executed: list[dict] = []

        class Executor:
            def execute(self, commands, **_kwargs):
                executed.extend(command.args for command in commands)
                return {"executed": [], "approval_required": [], "stopped": False}

        backend.command_execution = Executor()

        result = backend._finalize_result({"text": "MOVE[abcdef,1,2,3]"}, {})

        self.assertEqual(executed, [])
        self.assertTrue(result["execution"]["stopped"])
        self.assertIn("deterministic checkers", result["text"].lower())

    def test_generic_model_capture_is_blocked_even_when_it_matches_a_legal_move(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": "checkers"}
        selected: list[dict] = []

        class Executor:
            def execute(self, commands, **_kwargs):
                selected.extend(command.args for command in commands)
                return {"executed": [{"action": "move_object", "status": "executed"}], "approval_required": [], "stopped": False}

        backend.command_execution = Executor()
        result = backend._finalize_result({
            "text": "MOVE[f6d7a4,-0.844,1.74,0.937]",
            "_checkers_mandatory_capture": True,
            "_checkers_legal_moves": [{
                "guid": "black1",
                "from": "D4",
                "target": {"tag": "B2", "x": -4.0, "y": 1.7405, "z": -2.0},
                "kind": "capture",
            }],
        }, {})

        self.assertEqual(selected, [])
        self.assertTrue(result["execution"]["stopped"])
        self.assertIn("deterministic checkers", result["text"].lower())

    def test_generic_model_move_is_allowed_while_killteam_is_active(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": "killteam"}
        executed: list[dict] = []

        class Executor:
            def execute(self, commands, **_kwargs):
                executed.extend(command.args for command in commands)
                return {"executed": [{"action": "move_object", "status": "executed"}], "approval_required": [], "stopped": False}

        backend.command_execution = Executor()

        result = backend._finalize_result({"text": "MOVE[abcdef,1,2,3]"}, {})

        self.assertEqual(executed, [{"guid": "abcdef", "x": 1.0, "y": 2.0, "z": 3.0}])
        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(result["execution"]["executed"][0]["action"], "move_object")
        self.assertEqual(result["execution"]["blocked"], [])

    def test_killteam_deploy_test_routes_directly_to_the_placement_model(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"state": "running", "active_game": "killteam"}
        requested: list[tuple[str, dict]] = []

        class Executor:
            def request(self, action, args):
                requested.append((action, args))
                return {
                    "status": "verified",
                    "model_name": "Plague Marine",
                    "target_tag": "blue test marker",
                }

        backend.command_execution = Executor()

        result = backend.handle_killteam_setup_board_command("KILLTEAM_DEPLOY_TEST", is_host=True)

        self.assertEqual(requested, [("killteam_deploy_test_model", {})])
        self.assertIsNotNone(result)
        self.assertIn("Placement test complete", result["text"])
        self.assertEqual(result["killteam_deploy_test"]["status"], "verified")

    def test_command_only_move_bypasses_the_model_and_executes_locally(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "format": "openai",
            "model": "test-model",
        })
        backend.controller_provider = lambda: {"state": "running", "active_game": "killteam"}
        executed: list[dict] = []

        class Executor:
            def execute(self, commands, **_kwargs):
                executed.extend(command.args for command in commands)
                return {"executed": [{"action": "move_object", "status": "executed"}], "approval_required": [], "stopped": False}

        backend.command_execution = Executor()

        with patch("tts_mcp.app.http_gateway.urlopen", side_effect=AssertionError("AI backend should not be called for a direct MOVE command")):
            result = backend.complete({"message": "MOVE[96fe20,-18.0858974456787,1.489675760269165,-8.608673095703125]"})

        self.assertEqual(executed, [{"guid": "96fe20", "x": -18.0858974456787, "y": 1.489675760269165, "z": -8.608673095703125}])
        self.assertIn("Executing command.", result["text"])
        self.assertEqual(result["execution"]["executed"][0]["action"], "move_object")
        self.assertFalse(result["execution"]["stopped"])

    def test_ollama_disables_thinking_for_bounded_gameplay_replies(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"message":{"content":"Ready."}}'

        with patch("tts_mcp.app.http_gateway.urlopen", return_value=Response()) as request:
            backend.complete({"message": "hello", "conversation_id": "think-test"})

        payload = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertFalse(payload["think"])

    def test_truncated_empty_backend_reply_is_reported_instead_of_silently_ignored(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:26b-a4b-it-qat",
        })

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"message":{"content":""},"done":true,"done_reason":"length"}'

        with patch("tts_mcp.app.http_gateway.urlopen", return_value=Response()):
            result = backend.complete({"message": "Make a move", "conversation_id": "truncated-test"})

        self.assertIn("response limit", result["text"])
        self.assertEqual(result["commands"], [])

    def test_ollama_requests_keep_model_loaded_for_configured_duration(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3-vl:latest",
            "ollama_keep_alive": "30m",
        })

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"message":{"content":"ready"}}'

        with patch("tts_mcp.app.http_gateway.urlopen", return_value=Response()) as request:
            backend.complete({"message": "hello", "conversation_id": "keep-alive-test"})

        payload = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["keep_alive"], "30m")

    def test_observation_review_budget_defaults_to_300_seconds(self) -> None:
        backend = ChatBackend()
        self.assertEqual(backend.observation_timeout, 300.0)

    def test_observation_review_budget_is_capped_at_300_seconds(self) -> None:
        backend = ChatBackend()
        backend.reload({"observation_timeout": 999})
        self.assertEqual(backend.observation_timeout, 300.0)


class KillTeamDefenseAcknowledgmentTests(unittest.TestCase):
    def test_red_acknowledgment_completes_pending_validation_without_model_claim(self) -> None:
        calls = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {
                "status": "resolved",
                "damage": 3,
                "target_wounds": 4,
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_defense_acknowledgment(
            "Defense roll complete",
            player_identity="Red",
            is_host=False,
        )

        self.assertEqual(calls, [(
            "killteam_complete_setup_validation",
            {"acknowledged_by": "Red"},
        )])
        self.assertEqual(
            result["text"],
            "Red's defense roll is resolved: 3 damage; 4 wounds remain.",
        )

    def test_non_red_non_host_cannot_acknowledge_red_defense(self) -> None:
        calls = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {},
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_defense_acknowledgment(
            "Defense roll complete",
            player_identity="Blue",
            is_host=False,
        )

        self.assertEqual(calls, [])
        self.assertIn("Only Red or the host", result["text"])


class KillTeamSetupBoardCommandTests(unittest.TestCase):
    def test_autorun_setup_is_left_for_the_ai_placement_turn(self) -> None:
        backend = ChatBackend()
        calls: list[tuple[str, dict]] = []
        backend.configure_gameplay(
            controller_provider=lambda: {"active_game": "killteam", "state": "running"},
            request=lambda action, args: calls.append((action, args)) or {
                "executed": [{
                    "action": "killteam_autorun_setup",
                    "status": "executed",
                    "result": {"final_state": {"stage": "deployment"}},
                }],
                "approval_required": [],
                "stopped": False,
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_AUTORUN_SETUP",
            is_host=False,
        )

        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_autorun_setup_does_not_report_a_runtime_batch_stop(self) -> None:
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {"active_game": "killteam", "state": "running"},
            request=lambda action, args: {
                "executed": [{
                    "action": action,
                    "status": "failed",
                    "reason": "no legal setup slot",
                }],
                "approval_required": [],
                "blocked": [],
                "stopped": True,
                "stop_reason": "no legal setup slot",
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_AUTORUN_SETUP",
            is_host=False,
        )

        self.assertIsNone(result)

    def test_autorun_setup_falls_back_without_gameplay_execution(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_AUTORUN_SETUP",
            is_host=False,
        )

        self.assertIsNone(result)

    def test_backend_autorun_macro_is_not_executed(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}
        calls: list[tuple[str, dict]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {"execute": lambda _self, commands, **_kwargs: calls.append(("execute", {}))},
        )()

        result = backend._finalize_result(
            {"text": "KILLTEAM_AUTORUN_SETUP"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["parsed_commands"], [
            {"action": "killteam_autorun_setup", "args": {}, "destructive": False},
        ])
        self.assertIn("blocked", result["execution"])
        self.assertIn("rejected", result["text"].lower())

    def test_backend_rejects_multiple_setup_placements(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}
        calls: list[tuple[str, dict]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {"execute": lambda _self, commands, **_kwargs: calls.append(("execute", {}))},
        )()

        result = backend._finalize_result(
            {
                "text": (
                    "MOVE[362d46, 1, 2, 3]\n"
                    "MOVE[a1b2c3, 4, 5, 6]"
                )
            },
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual(calls, [])
        self.assertIn("blocked", result["execution"])
        self.assertEqual(len(result["parsed_commands"]), 2)
        self.assertIn("rejected", result["text"].lower())

    def test_backend_executes_setup_batch_and_records_each_placement(self) -> None:
        backend = ChatBackend()
        saved: list[dict] = []
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        backend._setup_history_saver = lambda placement: saved.append(dict(placement))
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: {
                    "executed": [
                        {
                            "action": command.action,
                            "status": "executed",
                            "result": {"guid": command.args["guid"], "position": command.args},
                        }
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 2, "batch_target": 2}

        result = backend._finalize_result(
            {"text": "MOVE[a1b2c3,1,4.25,2]\nMOVE[d4e5f6,5,1.5,6]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual([item["action"] for item in result["execution"]["executed"]], [
            "killteam_setup_place_model",
            "killteam_setup_place_model",
        ])
        self.assertEqual([item["guid"] for item in saved], ["a1b2c3", "d4e5f6"])
        self.assertEqual([item["batch_size"] for item in saved], [2, 2])

    def test_backend_completes_underfilled_second_round_from_authoritative_batch(self) -> None:
        backend = ChatBackend()
        controller = {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {
                "placed_guids": ["0e43c7", "7506bd"],
                "batch_size": 2,
            },
        }
        backend.controller_provider = lambda: controller
        candidates = [
            {
                "candidate_id": "setup-883c89-00",
                "guid": "883c89",
                "source_position": {"x": 19.06101, "y": 1.5067, "z": -37.56811},
                "position": {"x": -32.36769, "y": 1.5067, "z": -9.50513},
                "footprint": {"min_x": -32.99356, "max_x": -31.74182, "min_z": -10.131, "max_z": -8.87926},
            },
            {
                "candidate_id": "setup-96fe20-01",
                "guid": "96fe20",
                "source_position": {"x": -19.42437, "y": 1.50487, "z": -15.42729},
                "position": {"x": -3.79303, "y": 1.50487, "z": -6.78668},
                "footprint": {"min_x": -4.41887, "max_x": -3.16719, "min_z": -7.41252, "max_z": -6.16084},
            },
        ]
        backend._enrich_setup_context(
            {
                "categories": {
                    "operatives": [
                        {"guid": candidate["guid"], "position": candidate["source_position"]}
                        for candidate in candidates
                    ] + [
                        {"guid": "remaining-a", "position": {"x": 30, "y": 1.5, "z": -30}},
                        {"guid": "remaining-b", "position": {"x": 31, "y": 1.5, "z": -31}},
                    ],
                },
                "setup_plan": {
                    "batch_size": 2,
                    "recommended_batch": candidates,
                    "candidates": candidates,
                },
            },
            controller,
        )
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [
                        {"action": command.action, "status": "executed", "result": {"guid": command.args["guid"]}}
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        traces: list[tuple[str, dict]] = []

        with patch(
            "tts_mcp.app.http_gateway._record_trace",
            side_effect=lambda kind, **payload: traces.append((kind, payload)),
        ):
            result = backend._finalize_result(
                {"text": "SETUP_MOVE[setup-883c89-00]"},
                {"message": "Place your next model"},
            )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(
            [command.args["guid"] for command in dispatched[0]],
            ["883c89", "96fe20"],
        )
        completion = [payload for kind, payload in traces if kind == "ai_setup_batch_completed"]
        self.assertEqual(len(completion), 1)
        self.assertEqual(completion[0]["model_candidate_ids"], ["setup-883c89-00"])
        self.assertEqual(completion[0]["supplied_candidate_ids"], ["setup-96fe20-01"])

    def test_backend_completes_empty_setup_response_only_with_fresh_exact_batch(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        backend._context_local.setup_batch = {"batch_size": 1, "batch_target": 1}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
        }
        backend._context_local.setup_batch_candidate_ids = {"setup-a-00"}
        backend._context_local.setup_batch_candidate_order = ["setup-a-00"]
        backend._context_local.setup_context_ready = True
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()

        result = backend._finalize_result(
            {"text": "I could not produce a placement."},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual([command.args["guid"] for command in dispatched[0]], ["a1b2c3"])

    def test_backend_preserves_first_setup_placement_when_second_fails(self) -> None:
        backend = ChatBackend()
        saved: list[dict] = []
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        backend._setup_history_saver = lambda placement: saved.append(dict(placement))
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: {
                    "executed": [
                        {"action": "killteam_setup_place_model", "status": "executed", "result": {"guid": commands[0].args["guid"]}},
                        {"action": "killteam_setup_place_model", "status": "failed", "reason": "overlap"},
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": True,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 2, "batch_target": 2}

        result = backend._finalize_result(
            {"text": "MOVE[a1b2c3,1,4.25,2]\nMOVE[d4e5f6,5,1.5,6]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual([item["guid"] for item in saved], ["a1b2c3"])
        self.assertTrue(result["execution"]["stopped"])

    def test_backend_rejects_setup_guid_coordinate_cross_pair_before_dispatch(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        calls: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {"execute": lambda _self, commands, **_kwargs: calls.append(commands)},
        )()
        backend._context_local.setup_batch = {"batch_size": 2, "batch_target": 2}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
            "setup-b-00": {
                "candidate_id": "setup-b-00",
                "guid": "d4e5f6",
                "source_position": {"x": 20, "y": 1.5, "z": 20},
                "position": {"x": 5, "y": 1.5, "z": 6},
                "footprint": {"min_x": 4.5, "max_x": 5.5, "min_z": 5.5, "max_z": 6.5},
            },
        }

        result = backend._finalize_result(
            {"text": "MOVE[a1b2c3,5,1.5,6]\nMOVE[d4e5f6,5,1.5,6]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual(calls, [])
        self.assertTrue(result["execution"]["stopped"])
        self.assertIn("did not match", result["text"])
        self.assertEqual(result["execution"]["blocked"][0]["candidate_validation"]["guid"], "a1b2c3")

    def test_backend_normalizes_setup_y_from_matching_candidate(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [
                        {"action": command.action, "status": "executed", "result": {"guid": command.args["guid"]}}
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 1, "batch_target": 1}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
        }

        result = backend._finalize_result(
            {"text": "MOVE[a1b2c3,1,1.5,2]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(dispatched[0][0].args, {"guid": "a1b2c3", "x": 1.0, "y": 4.25, "z": 2.0})

    def test_backend_resolves_setup_candidate_id_without_coordinate_transcription(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [
                        {"action": command.action, "status": "executed", "result": {"guid": command.args["guid"]}}
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 1, "batch_target": 1}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": -3.793, "y": 1.50982, "z": -9.50521},
                "footprint": {"min_x": -4.3, "max_x": -3.3, "min_z": -10.0, "max_z": -9.0},
            },
        }

        result = backend._finalize_result(
            {"text": "SETUP_MOVE[setup-a-00]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(dispatched[0][0].args, {
            "guid": "a1b2c3",
            "x": -3.793,
            "y": 1.50982,
            "z": -9.50521,
        })

    def test_setup_rejects_candidates_outside_the_recommended_batch(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        calls: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {"execute": lambda _self, commands, **_kwargs: calls.append(commands)},
        )()
        backend._context_local.setup_batch = {"batch_size": 2, "batch_target": 2}
        backend._context_local.setup_batch_candidate_ids = {"setup-a-00"}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
            "setup-b-00": {
                "candidate_id": "setup-b-00",
                "guid": "d4e5f6",
                "source_position": {"x": 20, "y": 1.5, "z": 20},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
        }

        result = backend._finalize_result(
            {"text": "SETUP_MOVE[setup-b-00]\nSETUP_MOVE[setup-c-00]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertEqual(calls, [])
        self.assertTrue(result["execution"]["stopped"])
        validation = result["execution"]["blocked"][0]["candidate_validation"]
        self.assertEqual(validation["reason"], "setup candidate is not in the recommended legal batch")
        self.assertEqual(validation["allowed_candidate_ids"], ["setup-a-00"])

    def test_natural_language_setup_resume_uses_the_placement_bridge(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [
                        {"action": command.action, "status": "executed", "result": {"guid": command.args["guid"]}}
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 1, "batch_target": 1}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
        }

        result = backend._finalize_result(
            {"text": "SETUP_MOVE[setup-a-00]"},
            {"message": "Place your next model"},
        )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(dispatched[0][0].action, "killteam_setup_place_model")
        self.assertEqual(dispatched[0][0].args["guid"], "a1b2c3")

    def test_setup_guid_aliases_and_invalid_ids_repair_to_the_legal_batch(self) -> None:
        backend = ChatBackend()
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "paused",
            "killteam_setup_history": {},
        }
        dispatched: list[list[ParsedCommand]] = []
        backend.command_execution = type(
            "Executor",
            (),
            {
                "execute": lambda _self, commands, **_kwargs: dispatched.append(commands) or {
                    "executed": [
                        {"action": command.action, "status": "executed", "result": {"guid": command.args["guid"]}}
                        for command in commands
                    ],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                },
            },
        )()
        backend._context_local.setup_batch = {"batch_size": 2, "batch_target": 2}
        backend._context_local.setup_batch_candidate_ids = {"setup-a-00", "setup-b-00"}
        backend._context_local.setup_candidates = {
            "setup-a-00": {
                "candidate_id": "setup-a-00",
                "guid": "a1b2c3",
                "source_position": {"x": 10, "y": 1.5, "z": 10},
                "position": {"x": 1, "y": 4.25, "z": 2},
                "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 1.5, "max_z": 2.5},
            },
            "setup-b-00": {
                "candidate_id": "setup-b-00",
                "guid": "d4e5f6",
                "source_position": {"x": 20, "y": 1.5, "z": 20},
                "position": {"x": 5, "y": 1.5, "z": 6},
                "footprint": {"min_x": 4.5, "max_x": 5.5, "min_z": 5.5, "max_z": 6.5},
            },
        }

        result = backend._finalize_result(
            {"text": "SETUP_MOVE[not-a-candidate]\nSETUP_MOVE[d4e5f6]"},
            {"message": "KILLTEAM_AUTORUN_SETUP"},
        )

        self.assertFalse(result["execution"]["stopped"])
        self.assertEqual(
            [command.args["guid"] for command in dispatched[0]],
            ["a1b2c3", "d4e5f6"],
        )

    def test_setup_context_reconciles_a_pending_physical_commit(self) -> None:
        backend = ChatBackend()
        saved: list[dict] = []
        backend._setup_history_saver = lambda placement: saved.append(dict(placement))
        result = backend._enrich_setup_context(
            {
                "categories": {
                    "operatives": [
                        {
                            "guid": "a1b2c3",
                            "position": {"x": -3.793, "y": 1.50982, "z": -9.50521},
                        },
                    ],
                },
                "setup_plan": {
                    "batch_size": 2,
                    "candidates": [],
                    "recommended_batch": [],
                },
            },
            {
                "killteam_setup_history": {
                    "placements": [],
                    "pending_placements": [{
                        "guid": "a1b2c3",
                        "target_position": {"x": -3.793, "y": 1.60023, "z": -9.50521},
                        "batch_size": 2,
                    }],
                },
            },
        )

        self.assertEqual(result["setup_batch"]["placed_guids"], ["a1b2c3"])
        self.assertEqual(result["setup_batch"]["remaining_models"], 0)
        self.assertTrue(saved[0]["reconciled_from_pending"])

    def test_setup_context_refills_batch_after_planner_recommends_placed_models(self) -> None:
        backend = ChatBackend()
        result = backend._enrich_setup_context(
            {
                "categories": {
                    "operatives": [
                        {"guid": "placed-a", "position": {"x": 0, "y": 1.5, "z": 0}},
                        {"guid": "placed-b", "position": {"x": 0, "y": 1.5, "z": 0}},
                        {"guid": "new-model-a", "position": {"x": 0, "y": 1.5, "z": 0}},
                        {"guid": "new-model-b", "position": {"x": 0, "y": 1.5, "z": 0}},
                    ],
                },
                "setup_plan": {
                    "batch_size": 2,
                    "recommended_batch": [
                        {
                            "guid": "placed-a",
                            "candidate_id": "setup-placed-a-00",
                            "position": {"x": 0, "y": 1.5, "z": 0},
                        },
                        {
                            "guid": "placed-b",
                            "candidate_id": "setup-placed-b-00",
                            "position": {"x": 0, "y": 1.5, "z": 0},
                        },
                    ],
                    "candidates": [
                        {
                            "guid": "new-model-a",
                            "candidate_id": "setup-new-model-a-00",
                            "position": {"x": 1, "y": 4.25, "z": 2},
                            "footprint": {"min_x": 0, "max_x": 1, "min_z": 1, "max_z": 2},
                        },
                        {
                            "guid": "new-model-b",
                            "candidate_id": "setup-new-model-b-00",
                            "position": {"x": 5, "y": 1.5, "z": 6},
                            "footprint": {"min_x": 4, "max_x": 5, "min_z": 5, "max_z": 6},
                        },
                    ],
                },
            },
            {"killteam_setup_history": {"placed_guids": ["placed-a", "placed-b"]}},
        )

        self.assertEqual(
            [item["candidate_id"] for item in result["setup_plan"]["recommended_batch"]],
            ["setup-new-model-a-00", "setup-new-model-b-00"],
        )
        self.assertEqual(result["setup_batch"]["batch_target"], 2)

    def test_setup_context_refill_uses_remaining_count_for_final_partial_batch(self) -> None:
        backend = ChatBackend()
        result = backend._enrich_setup_context(
            {
                "categories": {
                    "operatives": [
                        {"guid": f"model-{index}", "position": {"x": 0, "y": 1.5, "z": 0}}
                        for index in range(6)
                    ],
                },
                "setup_plan": {
                    "batch_size": 2,
                    "recommended_batch": [],
                    "candidates": [{
                        "guid": "model-5",
                        "candidate_id": "setup-model-5-00",
                        "position": {"x": 8, "y": 1.5, "z": 8},
                        "footprint": {"min_x": 7, "max_x": 9, "min_z": 7, "max_z": 9},
                    }],
                },
            },
            {
                "killteam_setup_history": {
                    "placed_guids": [f"model-{index}" for index in range(5)],
                    "batch_size": 2,
                },
            },
        )

        self.assertEqual(result["setup_batch"]["batch_target"], 1)
        self.assertEqual(
            [item["candidate_id"] for item in result["setup_plan"]["recommended_batch"]],
            ["setup-model-5-00"],
        )

    def test_setup_ping_returns_reload_verification_payload(self) -> None:
        tts_server = _load_tts_server()
        traces: list[tuple[str, dict]] = []
        with (
            patch.object(tts_server, "_killteam_setup_call", return_value={
                "bridge_version": "2026-07-29-setup-placement-v1",
                "object_count": 226,
            }),
            patch.object(tts_server, "verify_killteam_setup_bridge_source", return_value={
                "bridge_version": "2026-07-29-setup-placement-v1",
                "disk_hash": "disk-hash",
                "loaded_hash": "disk-hash",
                "loaded_script_identity": "Global",
                "reload_verified": True,
                "script_state_count": 1,
                "verification_error": "",
                "verification_source": "fresh",
            }),
            patch.object(tts_server, "_record_trace", side_effect=lambda kind, **payload: traces.append((kind, payload))),
        ):
            result = asyncio.run(tts_server.tts_killteam_setup_ping())

        self.assertTrue(result["reload_verified"])
        self.assertEqual(result["loaded_hash"], "disk-hash")
        self.assertEqual(result["disk_hash"], "disk-hash")
        self.assertEqual(result["verification_source"], "fresh")
        self.assertEqual(result["loaded_script_identity"], "Global")
        self.assertEqual(result["bridge_version"], "2026-07-29-setup-placement-v1")
        reload_traces = [payload for kind, payload in traces if kind == "killteam_setup_reload_check"]
        self.assertEqual(len(reload_traces), 1)
        self.assertTrue(reload_traces[0]["reload_verified"])

    def test_setup_ping_fails_closed_on_reload_mismatch_and_traces_reason(self) -> None:
        tts_server = _load_tts_server()
        traces: list[tuple[str, dict]] = []
        with (
            patch.object(tts_server, "_killteam_setup_call", return_value={
                "bridge_version": "2026-07-29-setup-placement-v1",
                "object_count": 226,
            }),
            patch.object(tts_server, "verify_killteam_setup_bridge_source", return_value={
                "bridge_version": "2026-07-29-setup-placement-v1",
                "disk_hash": "disk-hash",
                "loaded_hash": "loaded-hash",
                "loaded_script_identity": "Global",
                "reload_verified": False,
                "script_state_count": 1,
                "verification_error": "Global script body does not match the on-disk setup bridge",
                "verification_source": "fresh",
            }),
            patch.object(tts_server, "_record_trace", side_effect=lambda kind, **payload: traces.append((kind, payload))),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(tts_server.tts_killteam_setup_ping())

        reload_traces = [payload for kind, payload in traces if kind == "killteam_setup_reload_check"]
        self.assertEqual(len(reload_traces), 1)
        self.assertFalse(reload_traces[0]["reload_verified"])
        self.assertIn("does not match", reload_traces[0]["verification_error"])

    def test_setup_prose_reply_is_retried_before_placement(self) -> None:
        backend = ChatBackend()
        backend.enabled = True
        backend.kind = "http"
        backend.format = "ollama"
        backend.url = "http://127.0.0.1:11434/api/chat"
        backend.model = "gemma4:26b-a4b-it-qat"
        backend.observation_max_calls = 4
        backend.observation_timeout = 30.0
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}

        observation_calls: list[tuple[str, dict]] = []

        backend.configure_observation_tools({
            "tts_killteam_setup_ping": lambda args: observation_calls.append(("ping", dict(args))) or {
                "bridge_version": "2026-07-29-setup-placement-v1",
            },
            "tts_killteam_setup_context": lambda args: observation_calls.append(("context", dict(args))) or {
                "objects": [{
                    "guid": "362d46",
                    "name": "Plague Marine Warrior",
                    "tags": ["Operative"],
                    "position": {"x": -1.0, "y": 1.0, "z": 3.0},
                }],
                "categories": {"operatives": [{"guid": "362d46"}]},
                "setup_plan": {
                    "batch_size": 1,
                    "recommended_batch": [{
                        "candidate_id": "setup-362d46-00",
                        "guid": "362d46",
                        "source_position": {"x": -1.0, "y": 1.0, "z": 3.0},
                        "position": {"x": 1.0, "y": 1.0, "z": 3.0},
                        "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 2.5, "max_z": 3.5},
                    }],
                    "candidates": [{
                        "candidate_id": "setup-362d46-00",
                        "guid": "362d46",
                        "source_position": {"x": -1.0, "y": 1.0, "z": 3.0},
                        "position": {"x": 1.0, "y": 1.0, "z": 3.0},
                        "footprint": {"min_x": 0.5, "max_x": 1.5, "min_z": 2.5, "max_z": 3.5},
                    }],
                },
            },
        })

        class Executor:
            def __init__(self) -> None:
                self.calls: list[tuple[list, dict]] = []

            def execute(self, commands, **kwargs):
                self.calls.append((list(commands), dict(kwargs)))
                command = commands[0]
                return {
                    "executed": [{
                        "action": command.action,
                        "status": "executed",
                        "result": {
                            "status": "verified",
                            "guid": command.args["guid"],
                            "position": {
                                "x": float(command.args["x"]),
                                "y": float(command.args["y"]),
                                "z": float(command.args["z"]),
                            },
                        },
                    }],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                }

        backend.command_execution = Executor()
        traces: list[str] = []
        responses = [
            {"message": {"role": "assistant", "content": "I will check the bridge first."}},
            {"message": {"role": "assistant", "tool_calls": [
                {
                    "id": "ping-1",
                    "function": {
                        "name": "tts_killteam_setup_ping",
                        "arguments": "{}",
                    },
                },
                {
                    "id": "context-1",
                    "function": {
                        "name": "tts_killteam_setup_context",
                        "arguments": "{\"max_results\":50}",
                    },
                },
            ]}},
            {"message": {"role": "assistant", "content": "MOVE[362d46, 1, 1, 3]"}},
        ]

        with (
            patch("tts_mcp.app.http_gateway._record_trace", side_effect=lambda kind, **payload: traces.append(kind)),
            patch.object(backend, "_http_request", side_effect=responses),
        ):
            result = backend.complete({"message": "KILLTEAM_AUTORUN_SETUP"})

        self.assertEqual([name for name, _args in observation_calls], ["ping", "context"])
        self.assertIn("ai_setup_retry_requested", traces)
        self.assertIn("ai_commands_processed", traces)
        self.assertEqual(result["parsed_commands"], [
            {"action": "move_object", "args": {"guid": "362d46", "x": 1.0, "y": 1.0, "z": 3.0}, "destructive": False},
        ])
        self.assertEqual(result["execution"]["executed"][0]["status"], "executed")
        self.assertEqual(result["execution"]["executed"][0]["action"], "killteam_setup_place_model")
        self.assertEqual(backend.command_execution.calls[0][0][0].action, "killteam_setup_place_model")

    def test_setup_prose_reply_after_observation_budget_exhaustion_uses_move_prompt(self) -> None:
        backend = ChatBackend()
        backend.enabled = True
        backend.kind = "http"
        backend.format = "ollama"
        backend.url = "http://127.0.0.1:11434/api/chat"
        backend.model = "gemma4:26b-a4b-it-qat"
        backend.observation_max_calls = 1
        backend.observation_timeout = 30.0
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}

        observation_calls: list[tuple[str, dict]] = []
        backend.configure_observation_tools({
            "tts_killteam_setup_ping": lambda args: observation_calls.append(("ping", dict(args))) or {
                "bridge_version": "2026-07-29-setup-placement-v1",
            },
        })

        class Executor:
            def __init__(self) -> None:
                self.calls: list[tuple[list, dict]] = []

            def execute(self, commands, **kwargs):
                self.calls.append((list(commands), dict(kwargs)))
                command = commands[0]
                return {
                    "executed": [{
                        "action": command.action,
                        "status": "executed",
                        "result": {
                            "status": "verified",
                            "guid": command.args["guid"],
                            "position": {
                                "x": float(command.args["x"]),
                                "y": float(command.args["y"]),
                                "z": float(command.args["z"]),
                            },
                        },
                    }],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                }

        backend.command_execution = Executor()
        traces: list[str] = []
        requests: list[dict[str, Any]] = []
        responses = iter([
            {"message": {"role": "assistant", "tool_calls": [{
                "id": "ping-1",
                "function": {
                    "name": "tts_killteam_setup_ping",
                    "arguments": "{}",
                },
            }]}},
            {"message": {"role": "assistant", "content": "I need more information to determine the correct placement for this turn."}},
            {"message": {"role": "assistant", "content": "MOVE[362d46, 1, 1, 3]"}},
        ])

        def fake_http_request(payload, messages, include_tools=True, setup_turn=False):
            requests.append({
                "include_tools": include_tools,
                "setup_turn": setup_turn,
                "messages": copy.deepcopy(messages),
            })
            return next(responses)

        with (
            patch("tts_mcp.app.http_gateway._record_trace", side_effect=lambda kind, **payload: traces.append(kind)),
            patch.object(backend, "_http_request", side_effect=fake_http_request),
        ):
            result = backend.complete({"message": "KILLTEAM_AUTORUN_SETUP"})

        self.assertEqual([name for name, _args in observation_calls], ["ping"])
        self.assertIn("ai_setup_retry_requested", traces)
        self.assertIn("ai_commands_processed", traces)
        self.assertEqual(len(requests), 3)
        self.assertFalse(requests[1]["include_tools"])
        self.assertIn("The setup observation budget is exhausted", json.dumps(requests[1]["messages"]))
        self.assertNotIn("please provide further instructions", json.dumps(requests[1]["messages"]).lower())

    def test_setup_placeholder_move_does_not_call_full_setup_planner(self) -> None:
        backend = ChatBackend()
        backend.enabled = True
        backend.kind = "http"
        backend.format = "ollama"
        backend.url = "http://127.0.0.1:11434/api/chat"
        backend.model = "gemma4:26b-a4b-it-qat"
        backend.observation_max_calls = 4
        backend.observation_timeout = 30.0
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "running",
            "killteam_setup_history": {"placements": []},
        }

        plan_calls: list[dict] = []
        backend.configure_observation_tools({
            "tts_killteam_plan_setup_board": lambda args: plan_calls.append(dict(args)) or {
                "placements": [{
                    "model_guid": "96fe20",
                    "target_position": {"x": -32.25, "y": 6.0, "z": -10.25},
                }],
            },
        })

        class Executor:
            def __init__(self) -> None:
                self.calls: list[tuple[list, dict]] = []

            def execute(self, commands, **kwargs):
                self.calls.append((list(commands), dict(kwargs)))
                command = commands[0]
                return {
                    "executed": [{
                        "action": command.action,
                        "status": "executed",
                        "result": {
                            "status": "verified",
                            "guid": command.args["guid"],
                            "position": {
                                "x": float(command.args["x"]),
                                "y": float(command.args["y"]),
                                "z": float(command.args["z"]),
                            },
                        },
                    }],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                }

        backend.command_execution = Executor()
        traces: list[str] = []
        responses = [
            {"message": {"role": "assistant", "content": "I have the evidence I need."}},
            {"message": {"role": "assistant", "content": "MOVE[96fe20,x,y,z]"}},
        ]

        with (
            patch("tts_mcp.app.http_gateway._record_trace", side_effect=lambda kind, **payload: traces.append(kind)),
            patch.object(backend, "_http_request", side_effect=responses),
        ):
            result = backend.complete({"message": "KILLTEAM_AUTORUN_SETUP"})

        self.assertNotIn("ai_setup_placeholder_resolved", traces)
        self.assertEqual(plan_calls, [])
        self.assertIn("rejected", result["text"].lower())
        self.assertNotIn("further instructions", result["text"].lower())
        self.assertEqual(backend.command_execution.calls, [])

    def test_setup_prose_reply_exhausts_retry_budget_without_asking_for_more_instructions(self) -> None:
        backend = ChatBackend()
        backend.enabled = True
        backend.kind = "http"
        backend.format = "ollama"
        backend.url = "http://127.0.0.1:11434/api/chat"
        backend.model = "gemma4:26b-a4b-it-qat"
        backend.observation_max_calls = 4
        backend.observation_timeout = 30.0
        backend.controller_provider = lambda: {"active_game": "killteam", "state": "running"}

        requests: list[dict[str, Any]] = []
        responses = [
            {"message": {"role": "assistant", "content": "I need more information."}},
            {"message": {"role": "assistant", "content": "I need more information."}},
            {"message": {"role": "assistant", "content": "I need more information."}},
            {"message": {"role": "assistant", "content": "I need more information."}},
        ]

        def fake_http_request(payload, messages, include_tools=True, setup_turn=False):
            requests.append({
                "include_tools": include_tools,
                "setup_turn": setup_turn,
                "messages": copy.deepcopy(messages),
            })
            return responses.pop(0)

        with patch.object(backend, "_http_request", side_effect=fake_http_request):
            result = backend.complete({"message": "KILLTEAM_AUTORUN_SETUP"})

        self.assertEqual(len(requests), 4)
        self.assertEqual(result["text"], "I could not complete the setup automatically.")
        self.assertNotIn("instructions", result["text"].lower())
        for request in requests[1:]:
            self.assertNotIn("please provide further instructions", json.dumps(request["messages"]).lower())

    def test_complete_start_fresh_runs_killteam_autorun_setup(self) -> None:
        backend = ChatBackend()
        payload = {"message": "!ai start fresh killteam", "conversation_id": "fresh-test"}
        controller_result = {
            "text": "[AI] Autonomous play started fresh for killteam as Player 2/Blue.",
            "commands": [],
            "fresh_start": True,
            "selected_game": "killteam",
            "autostart_setup": True,
        }
        setup_result = {
            "text": "Setup underway.",
            "commands": [],
            "execution": {"status": "running"},
        }

        with (
            patch.object(backend, "reset", return_value="fresh-test") as reset,
            patch.object(backend, "complete", return_value=setup_result) as complete,
        ):
            result = backend.complete_start_fresh(payload, controller_result)

        reset.assert_called_once_with("fresh-test")
        complete.assert_called_once()
        self.assertEqual(complete.call_args.args[0]["message"], "KILLTEAM_AUTORUN_SETUP")
        self.assertEqual(result["text"], "Setup underway.")
        self.assertTrue(result["startup"]["fresh_start"])
        self.assertEqual(result["startup"]["controller"]["selected_game"], "killteam")

    def test_setup_empty_reply_does_not_call_full_setup_planner(self) -> None:
        backend = ChatBackend()
        backend.enabled = True
        backend.kind = "http"
        backend.format = "ollama"
        backend.url = "http://127.0.0.1:11434/api/chat"
        backend.model = "gemma4:26b-a4b-it-qat"
        backend.observation_max_calls = 4
        backend.observation_timeout = 30.0
        backend.controller_provider = lambda: {
            "active_game": "killteam",
            "state": "running",
            "killteam_setup_history": {"placements": []},
        }

        plan_calls: list[dict] = []
        backend.configure_observation_tools({
            "tts_killteam_plan_setup_board": lambda args: plan_calls.append(dict(args)) or {
                "placements": [{
                    "model_guid": "96fe20",
                    "target_position": {"x": -32.25, "y": 6.0, "z": -10.25},
                }],
            },
        })

        class Executor:
            def __init__(self) -> None:
                self.calls: list[tuple[list, dict]] = []

            def execute(self, commands, **kwargs):
                self.calls.append((list(commands), dict(kwargs)))
                command = commands[0]
                return {
                    "executed": [{
                        "action": command.action,
                        "status": "executed",
                        "result": {
                            "status": "verified",
                            "guid": command.args["guid"],
                            "position": {
                                "x": float(command.args["x"]),
                                "y": float(command.args["y"]),
                                "z": float(command.args["z"]),
                            },
                        },
                    }],
                    "approval_required": [],
                    "blocked": [],
                    "stopped": False,
                }

        backend.command_execution = Executor()
        traces: list[str] = []
        responses = [
            {"message": {"role": "assistant", "content": ""}},
            {"message": {"role": "assistant", "content": "I could not produce a placement."}},
        ]

        with (
            patch("tts_mcp.app.http_gateway._record_trace", side_effect=lambda kind, **payload: traces.append(kind)),
            patch.object(backend, "_http_request", side_effect=responses),
        ):
            result = backend.complete({"message": "KILLTEAM_AUTORUN_SETUP"})

        self.assertNotIn("ai_setup_placeholder_resolved", traces)
        self.assertEqual(plan_calls, [])
        self.assertIn("rejected", result["text"].lower())
        self.assertEqual(backend.command_execution.calls, [])

    def test_setup_autorun_is_not_routed_to_runtime_macro(self) -> None:
        calls: list[tuple[str, dict]] = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {
                "executed": [{
                    "action": "killteam_autorun_setup",
                    "status": "executed",
                    "result": {
                        "final_state": {
                            "stage": "deployment",
                            "current_side": "ai",
                        },
                        "steps": [{"action": "tts_killteam_observe", "status": "executed"}],
                    },
                }],
                "approval_required": [],
                "stopped": False,
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_AUTORUN_SETUP",
            is_host=False,
        )

        self.assertEqual(calls, [])
        self.assertIsNone(result)

    def test_plan_command_requests_runtime_plan(self) -> None:
        calls = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {
                "status": "planned",
                "plan_id": "abc123",
                "placements": [{"model_guid": "96fe20"}],
                "renames": [],
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_PLAN_SETUP",
            is_host=False,
        )

        self.assertEqual(calls, [("killteam_plan_setup_board", {"clearance": 0.25})])
        self.assertIn("abc123", result["text"])
        self.assertEqual(result["killteam_setup_plan"]["plan_id"], "abc123")

    def test_execute_command_is_host_only(self) -> None:
        calls = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {},
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_EXECUTE_SETUP[abc123]",
            is_host=False,
        )

        self.assertEqual(calls, [])
        self.assertIn("Only the host", result["text"])

    def test_host_execute_command_requests_frozen_plan(self) -> None:
        calls = []
        backend = ChatBackend()
        backend.configure_gameplay(
            controller_provider=lambda: {
                "active_game": "killteam",
                "state": "running",
            },
            request=lambda action, args: calls.append((action, args)) or {
                "status": "executed",
                "completed": [{"model_guid": "96fe20"}],
            },
            propose=lambda _proposal: "unused",
        )

        result = backend.handle_killteam_setup_board_command(
            "KILLTEAM_EXECUTE_SETUP[abc123]",
            is_host=True,
        )

        self.assertEqual(calls, [("killteam_execute_setup_board", {"plan_id": "abc123"})])
        self.assertIn("executed", result["text"])


if __name__ == "__main__":
    unittest.main()
