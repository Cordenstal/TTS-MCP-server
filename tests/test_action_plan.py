import unittest

from tts_mcp.support.action_plan import expectation_failures, validate_action_plan


class ActionPlanValidationTests(unittest.TestCase):
    def test_accepts_supported_actions(self):
        plan = validate_action_plan([
            {"action": "move_object", "args": {"guid": "abc123"}},
            {"action": "set_object_lock", "args": {"guid": "abc123", "locked": True}},
        ])
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["action"], "move_object")

    def test_rejects_arbitrary_lua_or_unknown_actions(self):
        with self.assertRaises(ValueError):
            validate_action_plan([{"action": "execute_lua", "args": {}}])

    def test_requires_explicit_irreversible_opt_in(self):
        with self.assertRaises(ValueError):
            validate_action_plan([
                {"action": "destroy_object", "args": {"guid": "abc123"}},
            ])

        plan = validate_action_plan(
            [{"action": "destroy_object", "args": {"guid": "abc123"}}],
            allow_irreversible=True,
        )
        self.assertEqual(plan[0]["action"], "destroy_object")

    def test_bounds_plan_size(self):
        with self.assertRaises(ValueError):
            validate_action_plan([
                {"action": "broadcast", "args": {"message": "x"}}
                for _ in range(51)
            ])

    def test_expectation_checks_identity_tags_and_position(self):
        actual = {
            "guid": "abc123",
            "name": "Red die",
            "tags": ["Die", "red"],
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        }
        self.assertEqual(
            expectation_failures(actual, {
                "guid": "abc123",
                "tags_contains": ["red"],
                "position": {"x": 1, "y": 2, "z": 3},
            }),
            [],
        )
        self.assertTrue(expectation_failures(actual, {"name": "Blue die"}))


if __name__ == "__main__":
    unittest.main()
