import unittest

from tts_mcp.support.semantic_index import rank_scene_objects, score_object_reference


class SemanticIndexTests(unittest.TestCase):
    OBJECTS = [
        {"guid": "RED123", "name": "Red marker", "type": "BlockSquare", "tags": ["player-marker", "red"]},
        {"guid": "BLUE12", "name": "Blue marker", "type": "BlockSquare", "tags": ["player-marker", "blue"]},
    ]

    def test_scores_name_and_tag_evidence(self):
        score, evidence = score_object_reference("red marker", self.OBJECTS[0])
        self.assertGreater(score, 50)
        self.assertIn("all reference words match the name", evidence)

    def test_ranking_is_deterministic(self):
        ranked = rank_scene_objects("blue marker", self.OBJECTS)
        self.assertEqual(ranked[0]["object"]["guid"], "BLUE12")

    def test_unknown_reference_has_no_candidates(self):
        self.assertEqual(rank_scene_objects("green deck", self.OBJECTS), [])


if __name__ == "__main__":
    unittest.main()
