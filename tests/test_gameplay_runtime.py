from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gameplay_runtime import (
    CatalogIndex,
    CommandExecution,
    GamePromptBuilder,
    Intent,
    classify_intent,
    parse_ai_commands,
    ScenePlacementIntelligence,
    should_capture_game_vision,
)


class VisionGatingTests(unittest.TestCase):
    def test_vision_is_only_requested_for_an_explicit_running_move(self) -> None:
        self.assertFalse(should_capture_game_vision("What is on the table?", "checkers", "running"))
        self.assertFalse(should_capture_game_vision("!ai status", "checkers", "running"))
        self.assertTrue(should_capture_game_vision("Make your move", "checkers", "running"))
        self.assertTrue(should_capture_game_vision("Move the black checker", "checkers", "running"))
        self.assertFalse(should_capture_game_vision("Make your move", "checkers", "paused"))


class CheckersInstantMoveTests(unittest.TestCase):
    def test_checkers_move_is_sent_without_smooth_animation(self) -> None:
        position = {"x": -2.88, "y": 1.74, "z": 2.88}
        objects = [
            {"guid": "abcdef", "type": "Checker", "position": dict(position)},
            {"guid": "123456", "type": "Checker", "position": {"x": -4.80, "y": 1.74, "z": 2.88}},
            {"guid": "654321", "type": "Checker", "position": {"x": 0.96, "y": 1.74, "z": 2.88}},
            {"guid": "fedcba", "type": "Checker", "position": {"x": -4.80, "y": 1.74, "z": 0.96}},
        ]
        calls: list[tuple[str, dict]] = []

        def request(action: str, args: dict) -> dict:
            calls.append((action, args))
            if action == "get_object":
                return {"guid": "abcdef", "type": "Checker", "position": dict(position), "bounds": {"size": {"y": 0.25}}}
            if action == "list_objects":
                return {"objects": objects}
            if action == "move_object":
                position.update(args["position"])
                return {"ok": True}
            return {"ok": True}

        result = CommandExecution(request, lambda _: "unused").execute(
            parse_ai_commands("MOVE[abcdef, -1.4659, 1.74, 1.4658]"),
            running=True,
            active_game="checkers",
        )

        self.assertEqual(result["executed"][0]["status"], "executed")
        move = next(args for action, args in calls if action == "move_object")
        self.assertFalse(move["smooth"])

    def test_checkers_validation_uses_tagged_squares_when_piece_is_off_center(self) -> None:
        """Prior moves may leave a checker slightly off its original center."""
        columns = {
            "A": 6.7443,
            "B": 4.8472,
            "C": 2.9501,
            "D": 1.0530,
            "E": -0.8442,
            "F": -2.7413,
            "G": -4.6384,
            "H": -6.5356,
        }
        ranks = {
            1: -6.7440,
            2: -4.8236,
            3: -2.9032,
            4: -0.9828,
            5: 0.9375,
            6: 2.8579,
            7: 4.7783,
            8: 6.6987,
        }
        source = {
            "guid": "2f278c",
            "type": "Checker",
            "position": {"x": -6.5834, "y": 1.7406, "z": 2.8651},
        }
        objects = [
            source,
            # These intentionally make a misleading checker-derived lattice.
            {"guid": "nearby", "type": "Checker", "position": {"x": -5.3834, "y": 1.7406, "z": 4.0651}},
            {"guid": "other", "type": "Checker", "position": {"x": 1.0530, "y": 1.7406, "z": 4.7783}},
        ]
        objects.extend(
            {
                "guid": f"zone-{letter}{rank}",
                "type": "LayoutZone",
                "tags": [f"{letter}{rank}"],
                "position": {"x": x, "y": 0.0, "z": ranks[rank]},
            }
            for letter, x in columns.items()
            for rank in ranks
        )

        corrected, correction, error = CommandExecution._normalize_checkers_move(
            {"guid": "2f278c", "x": columns["G"], "y": 1.7406, "z": ranks[5]},
            source,
            objects,
        )

        self.assertIsNone(error)
        self.assertIsNone(correction)
        self.assertEqual(corrected["x"], columns["G"])
        self.assertEqual(corrected["z"], ranks[5])

    def test_checkers_capture_moves_the_verified_jumped_piece_off_board(self) -> None:
        source_position = {"x": 0.0, "y": 1.74, "z": 4.0}
        objects = [
            {"guid": "abcdef", "name": "Black Checker", "type": "Checker", "locked": False, "position": source_position},
            {"guid": "red123", "name": "Red Checker", "type": "Checker", "locked": False, "position": {"x": -2.0, "y": 1.74, "z": 2.0}},
        ]
        objects.extend(
            {
                "guid": f"zone-{letter}{rank}",
                "type": "LayoutZone",
                "tags": [f"{letter}{rank}"],
                "position": {"x": float((ord(letter) - ord("D")) * 2), "y": 0.0, "z": float((rank - 4) * 2)},
            }
            for letter in "ABCDEFGH"
            for rank in range(1, 9)
        )
        calls: list[tuple[str, dict]] = []

        def request(action: str, args: dict) -> dict:
            calls.append((action, args))
            if action == "list_objects":
                return {"objects": objects}
            if action == "get_object":
                return next(item for item in objects if item["guid"] == args["guid"])
            if action == "set_object_lock":
                next(item for item in objects if item["guid"] == args["guid"])["locked"] = args["locked"]
                return {"ok": True}
            if action == "move_object":
                next(item for item in objects if item["guid"] == args["guid"])["position"].update(args["position"])
                return {"ok": True}
            raise AssertionError(f"unexpected action: {action}")

        result = CommandExecution(request, lambda _: "unused").execute(
            parse_ai_commands("MOVE[abcdef, -4, 1.74, 0]"),
            running=True,
            active_game="checkers",
        )

        self.assertEqual(result["executed"][0]["status"], "executed")
        self.assertFalse(any(action == "destroy_object" for action, _ in calls))
        captured = next(item for item in objects if item["guid"] == "red123")
        self.assertGreater(captured["position"]["x"], 8.0)

    def test_checkers_capture_locks_the_jumped_piece_before_off_board_removal(self) -> None:
        source_position = {"x": 0.0, "y": 1.74, "z": 4.0}
        objects = [
            {"guid": "abcdef", "name": "Black Checker", "type": "Checker", "locked": False, "position": source_position},
            {"guid": "red123", "name": "Red Checker", "type": "Checker", "locked": False, "position": {"x": -2.0, "y": 1.74, "z": 2.0}},
        ]
        objects.extend(
            {
                "guid": f"zone-{letter}{rank}",
                "type": "LayoutZone",
                "tags": [f"{letter}{rank}"],
                "position": {"x": float((ord(letter) - ord("D")) * 2), "y": 0.0, "z": float((rank - 4) * 2)},
            }
            for letter in "ABCDEFGH"
            for rank in range(1, 9)
        )

        def request(action: str, args: dict) -> dict:
            if action == "list_objects":
                return {"objects": objects}
            if action == "get_object":
                return next(item for item in objects if item["guid"] == args["guid"])
            if action == "set_object_lock":
                next(item for item in objects if item["guid"] == args["guid"])["locked"] = args["locked"]
                return {"ok": True}
            if action == "move_object":
                piece = next(item for item in objects if item["guid"] == args["guid"])
                piece["position"].update(args["position"])
                if piece["guid"] == "red123" and not piece["locked"]:
                    piece["position"]["y"] -= 1.0
                return {"ok": True}
            raise AssertionError(f"unexpected action: {action}")

        result = CommandExecution(request, lambda _: "unused").execute(
            parse_ai_commands("MOVE[abcdef, -4, 1.74, 0]"),
            running=True,
            active_game="checkers",
        )

        self.assertEqual(result["executed"][0]["status"], "executed")
        self.assertTrue(next(item for item in objects if item["guid"] == "red123")["locked"])

    def test_checker_reaching_back_rank_is_crowned_with_a_stacked_marker(self) -> None:
        source = {
            "guid": "b1ac01",
            "name": "Black Checker",
            "type": "Checker",
            "position": {"x": 0.0, "y": 1.74, "z": -4.0},
        }
        objects = [source]
        objects.extend(
            {
                "guid": f"zone-{letter}{rank}",
                "type": "LayoutZone",
                "tags": [f"{letter}{rank}"],
                "position": {"x": float((ord(letter) - ord("D")) * 2), "y": 0.0, "z": float((rank - 4) * 2)},
            }
            for letter in "ABCDEFGH"
            for rank in range(1, 9)
        )
        calls: list[tuple[str, dict]] = []

        def request(action: str, args: dict) -> dict:
            calls.append((action, args))
            if action == "list_objects":
                return {"objects": objects}
            if action == "get_object":
                return next(item for item in objects if item["guid"] == args["guid"])
            if action == "move_object":
                if args["guid"] == "king01":
                    # Save 128 combines the base checker and cloned marker
                    # into a new stack object, invalidating both old GUIDs.
                    objects[:] = [item for item in objects if item["guid"] not in {"b1ac01", "king01"}]
                    objects.append({
                        "guid": "king-stack",
                        "name": "Black Checker",
                        "type": "Checker",
                        "quantity": 2,
                        "position": dict(args["position"]),
                    })
                else:
                    next(item for item in objects if item["guid"] == args["guid"])["position"].update(args["position"])
                return {"ok": True}
            if action == "spawn_catalog":
                marker = {
                    "guid": "king01",
                    "name": "Black Checker",
                    "type": "Checker",
                    # TTS may create a clone at its transient default
                    # location instead of the requested clone position.
                    # Crowning must therefore move and verify the marker.
                    "position": {"x": 0.0, "y": 4.78, "z": 0.0},
                }
                objects.append(marker)
                return {"action": "spawn_catalog", "object": marker}
            raise AssertionError(f"unexpected action: {action}")

        result = CommandExecution(request, lambda _: "unused").execute(
            parse_ai_commands("MOVE[b1ac01, -2, 1.74, -6]"),
            running=True,
            active_game="checkers",
        )

        entry = result["executed"][0]
        self.assertEqual(entry["status"], "executed")
        self.assertEqual(entry["crown"]["marker_guid"], "king01")
        self.assertIn(("spawn_catalog", {"guid": "b1ac01", "position": {"x": -2.0, "y": 2.24, "z": -6.0}}), calls)
        self.assertIn(("move_object", {"guid": "king01", "position": {"x": -2.0, "y": 2.24, "z": -6.0}, "smooth": False, "collide": False, "fast": False}), calls)
        self.assertTrue(any(item["guid"] == "king-stack" for item in objects))


def test_prompt_frames_ai_as_selected_game_opponent() -> None:
    with tempfile.TemporaryDirectory() as directory:
        rules_root = Path(directory) / "game_rules"
        rules_dir = rules_root / "testgame"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rules.md").write_text("The AI controls the blue side.", encoding="utf-8")

        prompt = GamePromptBuilder(rules_root).build(
            game="testgame",
            intent=Intent.ENTITY_ACTION,
            context={"text": "Blue to move."},
        )

        assert "game-playing opponent" in prompt
        assert "Never guess" in prompt
        assert "Dungeon Master" not in prompt
        assert "Selected game: testgame" in prompt
        assert "The AI controls the blue side." in prompt
        assert "Do not import rules" in prompt
        assert "Authoritative current context:" not in prompt


def test_intent_classification_prioritizes_scene_requests() -> None:
    assert classify_intent("Set up a tavern with tables") is Intent.SCENE_SETUP
    assert classify_intent("Where is the red piece?") is Intent.QUERY
    assert classify_intent("!ai status") is Intent.OOC_COMMAND


def test_vision_is_only_requested_for_an_explicit_move_while_running() -> None:
    assert should_capture_game_vision("What is on the table?", "checkers", "running") is False
    assert should_capture_game_vision("!ai status", "checkers", "running") is False
    assert should_capture_game_vision("Make your move", "checkers", "running") is True
    assert should_capture_game_vision("Move the black checker", "checkers", "running") is True
    assert should_capture_game_vision("Make your move", "checkers", "paused") is False


def test_parser_only_accepts_allowlisted_commands_and_guid_shape() -> None:
    commands = parse_ai_commands(
        "MOVE[abcdef, 1, 2, 3] DESTROY[bad-guid] "
        "DESTROY[123456] SPAWN_BUILTIN[Die_6, 0, 3, 0] os.system('oops')"
    )
    assert [(item.action, item.destructive) for item in commands] == [
        ("move_object", False),
        ("destroy_object", True),
        ("spawn_builtin", False),
    ]


def test_parser_supports_v6_catalog_spawn_and_place() -> None:
    commands = parse_ai_commands("SPAWN[abcdef, -5, 2] PLACE[123456, 4, 8]")
    assert commands[0].action == "spawn_catalog"
    assert commands[0].args == {"guid": "abcdef", "x": -5.0, "y": 2.0, "z": 2.0}
    assert commands[1].action == "place_catalog"


def test_command_execution_proposes_destroy_and_verifies_move() -> None:
    calls: list[tuple[str, dict]] = []
    proposals: list[dict] = []

    def request(action: str, args: dict) -> dict:
        calls.append((action, args))
        if action == "get_object":
            return {"guid": args["guid"], "position": {"x": 1, "y": 2, "z": 3}}
        return {"ok": True}

    executor = CommandExecution(request, proposals.append)
    result = executor.execute(parse_ai_commands("MOVE[abcdef, 1, 2, 3] DESTROY[123456]"), running=True)
    assert result["executed"][0]["status"] == "executed"
    assert result["executed"][0]["verification"]["verified"] is True
    assert len(result["approval_required"]) == 1
    assert proposals[0]["action"] == "destroy_object"
    assert any(action == "get_object" for action, _ in calls)


def test_command_execution_stops_after_first_failed_action_without_retry() -> None:
    calls: list[tuple[str, dict]] = []

    def request(action: str, args: dict) -> dict:
        calls.append((action, args))
        if action == "get_object":
            return {"guid": args["guid"], "position": {"x": 9, "y": 2, "z": 9}}
        return {"ok": True}

    executor = CommandExecution(request, lambda _: "unused")
    result = executor.execute(
        parse_ai_commands("MOVE[abcdef, 1, 2, 3] MOVE[123456, 4, 5, 6]"),
        running=True,
    )

    assert result["stopped"] is True
    assert result["executed"][0]["status"] == "unverified"
    assert result["executed"][0]["attempts"] == 1
    assert not any(args.get("guid") == "123456" for action, args in calls if action == "move_object")


def test_large_position_mismatch_requests_visual_review() -> None:
    reviews: list[dict] = []
    actual = {"x": 1.6, "y": 2.0, "z": 3.0}

    def request(action: str, args: dict) -> dict:
        if action == "get_object":
            return {"guid": args["guid"], "position": dict(actual)}
        return {"ok": True}

    executor = CommandExecution(request, lambda _: "unused", review=reviews.append)
    result = executor.execute(
        parse_ai_commands("MOVE[abcdef, 1, 2, 3]"),
        running=True,
    )

    entry = result["executed"][0]
    assert entry["status"] == "unverified"
    assert entry["verification"]["visual_review_required"] is True
    assert reviews and reviews[0]["verification"]["position_delta"]["x"] == 0.6


def test_checkers_execution_blocks_a_sideways_or_backward_move() -> None:
    calls: list[tuple[str, dict]] = []

    def request(action: str, args: dict) -> dict:
        calls.append((action, args))
        if action == "get_object":
            return {"guid": args["guid"], "type": "Checker", "position": {"x": 1, "y": 2, "z": 3}}
        return {"ok": True}

    executor = CommandExecution(request, lambda _: "unused")
    result = executor.execute(parse_ai_commands("MOVE[abcdef, -1, 2, 3]"), running=True, active_game="checkers")
    assert result["executed"][0]["status"] == "blocked"
    assert "negative world Z" in result["executed"][0]["reason"]
    assert [action for action, _ in calls] == ["list_objects", "get_object"]


def test_checkers_execution_allows_backward_move_for_double_stacked_king() -> None:
    calls: list[tuple[str, dict]] = []
    position = {"x": 1.0, "y": 2.0, "z": 3.0}

    def request(action: str, args: dict) -> dict:
        calls.append((action, args))
        if action == "get_object":
            return {"guid": args["guid"], "type": "Checker", "position": dict(position), "bounds": {"size": {"x": 1, "y": 0.25, "z": 1}}}
        if action == "list_objects":
            return {"objects": [
                {"guid": "abcdef", "type": "Checker", "position": {"x": 1.0, "y": 2.0, "z": 3.0}},
                {"guid": "123456", "type": "Checker", "position": {"x": 1.0, "y": 2.25, "z": 3.0}},
            ]}
        if action == "move_object":
            position.update(args["position"])
            return {"ok": True}
        return {"ok": True}

    executor = CommandExecution(request, lambda _: "unused")
    result = executor.execute(parse_ai_commands("MOVE[abcdef, -1, 2, 4]"), running=True, active_game="checkers")
    assert result["executed"][0]["status"] == "executed"
    assert any(action == "move_object" for action, _ in calls)


def test_checkers_execution_corrects_sqrt_two_target_to_live_square() -> None:
    position = {"x": -2.88, "y": 1.74, "z": 2.88}
    objects = [
        {"guid": "abcdef", "type": "Checker", "position": dict(position)},
        {"guid": "123456", "type": "Checker", "position": {"x": -4.80, "y": 1.74, "z": 2.88}},
        {"guid": "654321", "type": "Checker", "position": {"x": 0.96, "y": 1.74, "z": 2.88}},
        {"guid": "fedcba", "type": "Checker", "position": {"x": -4.80, "y": 1.74, "z": 0.96}},
    ]
    calls: list[tuple[str, dict]] = []

    def request(action: str, args: dict) -> dict:
        calls.append((action, args))
        if action == "get_object":
            return {"guid": "abcdef", "type": "Checker", "position": dict(position), "bounds": {"size": {"y": 0.25}}}
        if action == "list_objects":
            return {"objects": objects}
        if action == "move_object":
            position.update(args["position"])
            return {"ok": True}
        return {"ok": True}

    executor = CommandExecution(request, lambda _: "unused")
    result = executor.execute(
        parse_ai_commands("MOVE[abcdef, -1.4659, 1.74, 1.4658]"),
        running=True,
        active_game="checkers",
    )

    entry = result["executed"][0]
    assert entry["status"] == "executed"
    assert entry["position_correction"]["corrected"] == {"x": -0.96, "z": 0.96}
    move = next(args for action, args in calls if action == "move_object")
    assert move["position"] == {"x": -0.96, "y": 1.74, "z": 0.96}
    assert move["smooth"] is False


def test_checkers_execution_rejects_stale_between_square_target() -> None:
    position = {"x": -0.96, "y": 1.74, "z": 0.96}
    objects = [
        {"guid": "abcdef", "type": "Checker", "position": dict(position)},
        {"guid": "123456", "type": "Checker", "position": {"x": -2.88, "y": 1.74, "z": 0.96}},
        {"guid": "654321", "type": "Checker", "position": {"x": 0.96, "y": 1.74, "z": 0.96}},
    ]

    def request(action: str, args: dict) -> dict:
        if action == "get_object":
            return {"guid": "abcdef", "type": "Checker", "position": dict(position)}
        if action == "list_objects":
            return {"objects": objects}
        raise AssertionError(f"unexpected action: {action}")

    executor = CommandExecution(request, lambda _: "unused")
    result = executor.execute(
        parse_ai_commands("MOVE[abcdef, -0.3429, 1.74, 0.6432]"),
        running=True,
        active_game="checkers",
    )

    assert result["executed"][0]["status"] == "blocked"
    assert "target is not a one-step" in result["executed"][0]["reason"]


def test_catalog_search_uses_live_objects() -> None:
    catalog = CatalogIndex()
    found = catalog.search("red pawn", objects=[
        {"guid": "abcdef", "name": "Red Pawn", "tags": ["chess-piece"]},
        {"guid": "123456", "name": "Blue Queen", "tags": ["chess-piece"]},
    ])
    assert found[0]["guid"] == "abcdef"


def test_catalog_search_excludes_master_bags_for_scene_queries() -> None:
    catalog = CatalogIndex()
    found = catalog.search("master bag table", objects=[
        {"guid": "abcdef", "name": "Master Bag - All Table Bags", "type": "Bag"},
        {"guid": "123456", "name": "Wooden Table", "type": "Custom"},
    ])
    assert found[0]["guid"] == "abcdef"  # explicit container query remains allowed
    scene_found = catalog.search("table", objects=[
        {"guid": "abcdef", "name": "Master Bag - All Table Bags", "type": "Bag"},
        {"guid": "123456", "name": "Wooden Table", "type": "Custom"},
    ])
    assert [item["guid"] for item in scene_found] == ["123456"]


def test_location_context_returns_exact_live_position() -> None:
    intelligence = ScenePlacementIntelligence(CatalogIndex())
    context = intelligence.enrich({
        "text": "Live table location data is authoritative.",
        "objects": [{
            "guid": "abcdef",
            "name": "Red Pawn",
            "type": "Figurine",
            "tags": ["chess-piece"],
            "position": {"x": 4.0, "y": 1.2, "z": -7.0},
            "bounds": {"center": {"x": 4.0, "y": 1.2, "z": -7.0}},
        }],
    }, "Where is the red pawn?", Intent.QUERY)
    assert '"x":4.0' in context["text"]
    assert '"z":-7.0' in context["text"]
