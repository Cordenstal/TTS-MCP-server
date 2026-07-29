import tempfile
import unittest
from pathlib import Path

from tts_mcp.support.session_store import SessionStore


class SemanticAliasStoreTests(unittest.TestCase):
    def test_aliases_round_trip_with_game_scope_and_role(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "state.sqlite3")
            saved = store.save_semantic_alias(
                "supply deck",
                "ABC123",
                game_name="chess",
                role="supply-deck",
            )
            self.assertEqual(saved["guid"], "ABC123")
            aliases = store.list_semantic_aliases(game_name="chess")
            self.assertEqual(aliases[0]["alias"], "supply deck")
            self.assertEqual(aliases[0]["role"], "supply-deck")
            self.assertTrue(store.delete_semantic_alias("supply deck", game_name="chess"))
            self.assertEqual(store.list_semantic_aliases(game_name="chess"), [])


if __name__ == "__main__":
    unittest.main()
