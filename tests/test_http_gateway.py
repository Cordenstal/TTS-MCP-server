from __future__ import annotations

import unittest
from unittest.mock import patch
import json

from http_gateway import ChatBackend, _public_ai_text


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

        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
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
        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
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
        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
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
            "model": "gemma4:12b",
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
        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)) as request:
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
        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "Review the board visually.", "conversation_id": "image-budget-test"})

        self.assertEqual(result["text"], "I reviewed one current view.")
        self.assertEqual(len(captures), 1)

    def test_failed_visual_observation_does_not_consume_visual_budget(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:12b",
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
            "model": "gemma4:12b",
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

        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
            result = backend.complete({"message": "Make your move.", "conversation_id": "observation-failure-test"})

        self.assertNotIn("tts_mcp_global.lua", result["text"])
        self.assertIn("couldn't inspect", result["text"].lower())

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

    def test_large_move_failure_gets_model_visible_ollama_image_review(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:12b",
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

        with patch("http_gateway.urlopen", return_value=Response()) as outbound:
            result = backend._finalize_result({"text": "MOVE[abcdef,1,2,3]"}, {})

        self.assertIn("Visual review", result["text"])
        payload = json.loads(outbound.call_args.args[0].data.decode("utf-8"))
        self.assertTrue(any(message.get("images") == ["ZmFrZQ=="] for message in payload["messages"]))

    def test_observation_registry_exposes_direct_object_listing(self) -> None:
        from http_gateway import OBSERVATION_TOOL_NAMES

        self.assertIn("tts_list_objects", OBSERVATION_TOOL_NAMES)

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
        with patch("http_gateway.urlopen", side_effect=lambda *args, **kwargs: next(responses)):
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

    def test_ollama_disables_thinking_for_bounded_gameplay_replies(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:12b",
        })

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"message":{"content":"Ready."}}'

        with patch("http_gateway.urlopen", return_value=Response()) as request:
            backend.complete({"message": "hello", "conversation_id": "think-test"})

        payload = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertFalse(payload["think"])

    def test_truncated_empty_backend_reply_is_reported_instead_of_silently_ignored(self) -> None:
        backend = ChatBackend()
        backend.reload({
            "kind": "http",
            "url": "http://127.0.0.1:11434/api/chat",
            "format": "ollama",
            "model": "gemma4:12b",
        })

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"message":{"content":""},"done":true,"done_reason":"length"}'

        with patch("http_gateway.urlopen", return_value=Response()):
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

        with patch("http_gateway.urlopen", return_value=Response()) as request:
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


if __name__ == "__main__":
    unittest.main()
