from __future__ import annotations

from gameplay_runtime import (
    CatalogIndex,
    CommandExecution,
    Intent,
    classify_intent,
    parse_ai_commands,
    ScenePlacementIntelligence,
)


def test_intent_classification_prioritizes_scene_requests() -> None:
    assert classify_intent("Set up a tavern with tables") is Intent.SCENE_SETUP
    assert classify_intent("Where is the red piece?") is Intent.QUERY
    assert classify_intent("!ai status") is Intent.OOC_COMMAND


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
    assert [action for action, _ in calls] == ["get_object", "list_objects"]


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
