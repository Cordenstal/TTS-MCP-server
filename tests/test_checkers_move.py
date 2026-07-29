from __future__ import annotations

import unittest

try:
    from tts_mcp.app import server
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-gated test import
    server = None
    _SERVER_IMPORT_ERROR = exc
else:
    _SERVER_IMPORT_ERROR = None


def piece(guid: str, name: str, x: float, z: float) -> dict:
    return {
        "guid": guid,
        "name": name,
        "position": {"x": x, "y": 1.7406, "z": z},
        "locked": False,
        "tags": [],
        "bounds": {"size": {"y": 0.25}},
    }


def board_pieces() -> list[dict]:
    return [
        piece("black1", "Checker_black", 0, 6),
        piece("black2", "Checker_black", -4, 6),
        piece("black3", "Checker_black", 4, 6),
        piece("black4", "Checker_black", -2, 8),
        piece("red1", "Checker_red", 2, 4),
        piece("red2", "Checker_red", 4, 2),
    ]


class CheckersMoveValidationTests(unittest.TestCase):
    def test_accepts_black_forward_diagonal(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        pieces = board_pieces()
        result = server._validate_checkers_target(pieces[0], pieces, -2, 4)

        self.assertEqual(result["target"], {"x": -2.0, "y": 1.7406, "z": 4.0})
        self.assertEqual(result["steps"], {"x": -1, "z": -1})

    def test_rejects_lateral_or_backward_black_man(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        pieces = board_pieces()

        for target in ((2, 6), (2, 8)):
            with self.subTest(target=target), self.assertRaises(ValueError):
                server._validate_checkers_target(pieces[0], pieces, *target)

    def test_rejects_occupied_destination(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        pieces = board_pieces()

        with self.assertRaisesRegex(ValueError, "occupied"):
            server._validate_checkers_target(pieces[0], pieces, 2, 4)

    def test_capture_identifies_the_exact_jumped_red_checker(self) -> None:
        if _SERVER_IMPORT_ERROR is not None:
            self.skipTest(f"server dependencies missing: {_SERVER_IMPORT_ERROR}")
        pieces = [
            piece("black1", "Checker_black", 0, 6),
            piece("red1", "Checker_red", -2, 4),
            piece("other", "Checker_black", 4, 6),
        ]

        result = server._validate_checkers_target(pieces[0], pieces, -4, 2)

        self.assertEqual(result["steps"], {"x": -2, "z": -2})
        self.assertEqual(result["captured_guid"], "red1")
