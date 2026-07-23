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


if __name__ == "__main__":
    unittest.main()
