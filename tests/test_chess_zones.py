from __future__ import annotations

import unittest

from server import _find_unique_tagged_zone, _validate_chess_objects


def zone(guid: str, tag: str) -> dict:
    return {
        "guid": guid,
        "name": "LayoutZone",
        "type": "LayoutZone",
        "tags": [tag],
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
    }


class ChessZoneTests(unittest.TestCase):
    def test_chess_mapping_accepts_plain_layout_zone_square_tags(self) -> None:
        objects = [
            zone(f"z{index:04d}", f"{letter}{rank}")
            for index, (letter, rank) in enumerate(
                ((letter, rank) for letter in "ABCDEFGH" for rank in range(1, 9)),
                start=1,
            )
        ]

        self.assertEqual(_validate_chess_objects(objects), [])

    def test_tagged_zone_resolution_is_case_insensitive(self) -> None:
        found = _find_unique_tagged_zone([zone("abc123", "E4")], "e4")

        self.assertEqual(found["guid"], "abc123")

    def test_tagged_zone_resolution_rejects_duplicate_destinations(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            _find_unique_tagged_zone([zone("abc123", "E4"), zone("def456", "e4")], "E4")
