from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import save_file


class SaveFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.path = self.root / "TS_Save_128.json"
        self.path.write_text(
            json.dumps({
                "SaveName": "test",
                "ObjectStates": [
                    {"GUID": "abcdef", "Nickname": "old", "Locked": False}
                ],
            }),
            encoding="utf-8",
        )
        self.default_patch = patch.object(save_file, "DEFAULT_SAVE_PATH", self.path)
        self.default_patch.start()

    def tearDown(self) -> None:
        self.default_patch.stop()
        self.temp_dir.cleanup()

    def test_inspect_returns_hash_and_object_count(self) -> None:
        result = save_file.inspect_save()

        self.assertEqual(result["file_name"], "TS_Save_128.json")
        self.assertEqual(result["object_count"], 1)
        self.assertEqual(len(result["sha256"]), 64)

    def test_dry_run_does_not_write(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        result = save_file.apply_operations(
            "",
            [{"op": "replace", "path": "/ObjectStates/0/Nickname", "value": "new"}],
            dry_run=True,
        )

        self.assertTrue(result["would_write"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_write_creates_backup_and_applies_pointer_edits(self) -> None:
        result = save_file.apply_operations(
            "",
            [
                {"op": "replace", "path": "/ObjectStates/0/Nickname", "value": "new"},
                {"op": "add", "path": "/ObjectStates/0/Tags", "value": ["piece"]},
            ],
            allow_irreversible=True,
        )

        self.assertTrue(result["written"])
        backup = Path(result["backup_path"])
        self.assertTrue(backup.is_file())
        updated = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(updated["ObjectStates"][0]["Nickname"], "new")
        self.assertEqual(updated["ObjectStates"][0]["Tags"], ["piece"])
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["ObjectStates"][0]["Nickname"], "old")

    def test_rejects_non_numbered_or_outside_paths(self) -> None:
        with self.assertRaises(ValueError):
            save_file.resolve_save_path(str(self.root / "other.json"))
        with self.assertRaises(ValueError):
            save_file.resolve_save_path(str(self.root.parent / "TS_Save_128.json"))


if __name__ == "__main__":
    unittest.main()

