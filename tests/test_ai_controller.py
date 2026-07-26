import tempfile
import unittest
from pathlib import Path

from ai_controller import AIController
from session_store import SessionStore


class AIControllerTests(unittest.TestCase):
    def test_explicit_ai_question_is_forwarded_to_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = AIController(
                Path(directory) / "rules",
                SessionStore(Path(directory) / "state.sqlite3"),
            )

            self.assertIsNone(
                controller.handle(
                    "!ai check the state of the board",
                    is_host=False,
                )
            )

    def test_unknown_lifecycle_command_is_not_reported_as_controller_error(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = AIController(
                Path(directory) / "rules",
                SessionStore(Path(directory) / "state.sqlite3"),
            )

            self.assertIsNone(controller.handle("!ai look", is_host=False))

    def test_known_control_still_requires_host(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = AIController(
                Path(directory) / "rules",
                SessionStore(Path(directory) / "state.sqlite3"),
            )

            response = controller.handle("!ai status", is_host=False)

            self.assertIsNotNone(response)
            self.assertIn("only the TTS host", response["text"])

    def test_fresh_start_word_order_is_accepted_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = AIController(
                Path(directory) / "rules",
                SessionStore(Path(directory) / "state.sqlite3"),
            )
            controller.state.active_game = "checkers"
            controller.state.game_position = {"turn": "black", "ply": 0, "pieces": []}

            response = controller.handle("!ai fresh start", is_host=True)

            self.assertIsNotNone(response)
            self.assertIn("started fresh", response["text"])
            self.assertEqual(controller.state.state, "running")
            self.assertIsNone(controller.state.game_position)


class DrawAgreementTests(unittest.TestCase):
    def controller(self) -> AIController:
        temp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        temp.close()
        controller = AIController(Path("game_rules"), SessionStore(temp.name))
        controller.state.active_game = "checkers"
        controller.state.state = "running"
        return controller

    def test_draw_requires_a_clear_offer_and_acceptance_by_the_other_player(self) -> None:
        controller = self.controller()

        offered = controller.handle_draw_message("!ai offer draw", player_identity="Red")
        self.assertIn("offered", offered["text"])
        self.assertEqual(controller.state.state, "running")

        agreed = controller.handle_draw_message("!ai accept draw", player_identity="Blue")
        self.assertIn("Draw agreed", agreed["text"])
        self.assertEqual(controller.state.state, "stopped")
        self.assertTrue(controller.state.draw_agreed)

    def test_a_player_cannot_accept_their_own_offer(self) -> None:
        controller = self.controller()
        controller.handle_draw_message("!ai offer draw", player_identity="Red")

        response = controller.handle_draw_message("!ai accept draw", player_identity="Red")

        self.assertIn("cannot accept", response["text"])
        self.assertEqual(controller.state.state, "running")

    def test_ordinary_chat_does_not_end_the_game(self) -> None:
        controller = self.controller()

        self.assertIsNone(controller.handle_draw_message("We should probably draw", player_identity="Red"))
        self.assertEqual(controller.state.state, "running")


if __name__ == "__main__":
    unittest.main()
