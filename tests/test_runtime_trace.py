import threading
import unittest
from unittest.mock import patch

import runtime_trace
from runtime_trace import console_event, pretty_event, record, snapshot


class RuntimeTraceTests(unittest.TestCase):
    def test_preserves_chat_text_and_redacts_credentials(self):
        value = snapshot({
            "message": "check the board",
            "authorization": "Bearer secret",
            "token": "secret-token",
        })

        self.assertEqual(value["message"], "check the board")
        self.assertEqual(value["authorization"], "<redacted>")
        self.assertEqual(value["token"], "<redacted>")

    def test_replaces_large_or_sensitive_binary_payloads_with_metadata(self):
        value = snapshot({"image_base64": "abcd", "script": "return true"})

        self.assertEqual(value["image_base64"], {"redacted": True, "length": 4})
        self.assertEqual(value["script"], {"redacted": True, "length": 11})

    def test_pretty_event_is_a_readable_multiline_timeline_entry(self):
        rendered = pretty_event({
            "at_unix": 1700000000,
            "kind": "tts_request_complete",
            "trace_id": "abc123",
            "pid": 42,
            "thread": "worker",
            "action": "ping",
            "response": {"ok": True, "message": "ready"},
        })

        self.assertIn("tts_request_complete", rendered)
        self.assertIn("trace=abc123", rendered)
        self.assertIn("response:", rendered)
        self.assertIn('"message": "ready"', rendered)
        self.assertIn("\n", rendered)

    def test_console_event_is_compact_and_keeps_chat_visible(self):
        rendered = console_event({
            "at_unix": 1700000000,
            "kind": "ai_message_received",
            "trace_id": "abc123",
            "message": "Check the state of the board",
            "player": {"color": "White", "host": True},
            "payload": {"large": {"nested": "payload"}},
        })

        self.assertIn('RECEIVED "Check the state of the board" from White, host', rendered)
        self.assertNotIn("payload", rendered)
        self.assertNotIn("{", rendered)

    def test_console_event_shows_verbose_ai_summary_without_raw_json(self):
        rendered = console_event({
            "at_unix": 1700000000,
            "kind": "ai_backend_inbound",
            "trace_id": "abc123",
            "backend": "ollama",
            "status": 200,
            "response": {
                "model": "game-model",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "I move the red checker forward."},
                }],
            },
        })

        self.assertIn("AI backend response received", rendered)
        self.assertIn('text="I move the red checker forward."', rendered)
        self.assertIn("finish=stop", rendered)
        self.assertNotIn("choices", rendered)
        self.assertNotIn("{", rendered)

    def test_console_event_shows_structured_state_attachment(self):
        rendered = console_event({
            "at_unix": 1700000000,
            "kind": "ai_prompt_built",
            "trace_id": "abc123",
            "message_count": 3,
            "prompt_chars": 1200,
            "gameplay_prompt_chars": 800,
            "context_chars": 400,
            "object_count": 12,
            "state_in_user_turn": True,
        })

        self.assertIn("objects=12", rendered)
        self.assertIn("state_in_user=true", rendered)

    def test_console_event_summarizes_action_arguments(self):
        rendered = console_event({
            "at_unix": 1700000000,
            "kind": "tts_request_start",
            "trace_id": "abc123",
            "action": "move_object",
            "args": {"guid": "abc", "position": {"x": 1, "y": 2, "z": 3}},
        })

        self.assertIn("TTS action move_object started", rendered)
        self.assertIn("args=guid=abc", rendered)
        self.assertIn("position=(1,2,3)", rendered)
        self.assertNotIn("{'", rendered)

    def test_console_event_preserves_full_tts_print_and_lua_error_text(self):
        printed = "system text " + ("x" * 300)
        print_rendered = console_event({
            "at_unix": 1700000000,
            "kind": "tts_print",
            "trace_id": "print123",
            "message": printed,
        })
        error_rendered = console_event({
            "at_unix": 1700000000,
            "kind": "tts_lua_error",
            "trace_id": "error123",
            "error": "Global:1009: attempt to call nil value",
            "guid": "Global",
            "prefix": "Error in Script",
        })

        self.assertIn(printed, print_rendered)
        self.assertIn("Global:1009: attempt to call nil value", error_rendered)

    def test_record_never_blocks_gateway_work_when_a_trace_handler_stalls(self):
        release_logger = threading.Event()
        returned = threading.Event()

        def stalled_logger(_message: str) -> None:
            release_logger.wait(timeout=5)

        with patch.object(runtime_trace.TRACE_LOG, "info", side_effect=stalled_logger):
            worker = threading.Thread(
                target=lambda: (record("trace-stall-test"), returned.set()),
                daemon=True,
            )
            worker.start()
            try:
                self.assertTrue(
                    returned.wait(timeout=0.2),
                    "record() must enqueue tracing instead of blocking the caller",
                )
            finally:
                release_logger.set()
                worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
