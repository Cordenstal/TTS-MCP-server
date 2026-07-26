from pathlib import Path
import unittest


class LuaBridgeSourceTests(unittest.TestCase):
    def test_external_message_decodes_before_unwrapping_envelope(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        decode_index = source.index("local function mcp_decode_message")
        unwrap_index = source.index("local function mcp_unwrap_external_message")
        handler_index = source.index("function mcp_handleExternalMessage")

        self.assertLess(decode_index, unwrap_index)
        self.assertLess(unwrap_index, handler_index)
        self.assertIn('tostring(data.messageID or "") == "2"', source)
        self.assertIn("data = mcp_unwrap_external_message(data)", source)

    def test_on_chat_does_not_consume_player_chat(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        chat_handler = source[source.index("function onChat(message, sender)"):]

        self.assertNotIn("return true", chat_handler)

    def test_ai_chat_uses_an_explicit_opaque_color(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn("printToAll(text, {r = 1, g = 1, b = 1, a = 1})", source)
        self.assertNotIn("printToAll(text)", source)

    def test_on_chat_posts_nonempty_messages_and_reports_delivery(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        chat_handler = source[source.index("function onChat(message, sender)"):]

        self.assertIn("mcp_forward_chat(message, sender)", chat_handler)
        self.assertIn("WebRequest.custom(", chat_handler)
        self.assertIn('MCP_HTTP_CHAT_URL', chat_handler)
        self.assertIn("chat received; sending to http://127.0.0.1:8765/chat", chat_handler)
        self.assertIn('HTTP status: " .. tostring(request.response_code) .. " body: " .. body', chat_handler)

    def test_large_chat_response_uses_non_pattern_trim(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")
        sanitizer = source[
            source.index("local function mcp_public_chat_text(value)"):
            source.index("local function mcp_decode_message(data)")
        ]
        self.assertIn("local function mcp_trim(value)", source)
        self.assertNotIn('string.match(text, "^%s*(.-)%s*$")', source)
        self.assertNotIn("string.gmatch(", sanitizer)
        self.assertNotIn("string.gsub(", sanitizer)

    def test_mcp_responses_use_hidden_http_transport_not_player_chat(self) -> None:
        source = Path("tts_mcp_global.lua").read_text(encoding="utf-8")

        self.assertIn('local MCP_HTTP_BRIDGE_RESPONSE_URL = "http://127.0.0.1:8765/bridge/response"', source)
        self.assertIn("local function mcp_post_bridge_response(response)", source)
        for function_name in ("mcp_send_ok", "mcp_send_error"):
            start = source.index(f"local function {function_name}")
            end = source.find("\nend", start)
            function_source = source[start:end]
            self.assertIn("mcp_post_bridge_response(response)", function_source)
            self.assertIn("sendExternalMessage(response)", function_source)
            self.assertNotIn("[tts-mcp-response]", function_source)
