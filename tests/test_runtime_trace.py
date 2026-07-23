import unittest

from runtime_trace import pretty_event, snapshot


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


if __name__ == "__main__":
    unittest.main()
