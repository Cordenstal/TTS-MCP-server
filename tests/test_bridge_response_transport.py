from __future__ import annotations

import json
import os
import queue
import socket
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from http_gateway import HttpGateway
from server import TTSBridge, _ai_observation_bridge_timeout


class BridgeResponseTransportTests(unittest.TestCase):
    def test_windows_listener_claims_exclusive_callback_port(self) -> None:
        bridge = TTSBridge()
        listener = Mock()
        bridge._listener_stop.set()

        with patch("server.os.name", "nt"), patch(
            "server.socket.socket", return_value=listener
        ):
            bridge._listen_loop()

        listener.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
        )
        listener.bind.assert_called_once_with((bridge.host, bridge.receive_port))

    def test_ai_facing_bridge_deadlines_default_to_300_seconds(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(TTSBridge().timeout, 300.0)
            self.assertEqual(_ai_observation_bridge_timeout(), 300.0)

    def test_request_keeps_external_editor_custom_message_object_form(self) -> None:
        bridge = TTSBridge()
        sent: dict[str, object] = {}
        bridge.ensure_listener = lambda: None  # type: ignore[method-assign]

        def fake_send(message: dict[str, object]) -> None:
            sent.update(message)
            raw = message["customMessage"]
            envelope = json.loads(raw) if isinstance(raw, str) else raw
            assert isinstance(envelope, dict)
            bridge.deliver_response({
                "channel": "tts-mcp",
                "event": "mcp_response",
                "requestId": envelope["requestId"],
                "ok": True,
                "result": {"decoded": True},
            }, transport="test")

        bridge._send = fake_send  # type: ignore[method-assign]

        result = bridge.request(
            "killteam_list_objects",
            {
                "query_tags_json": "[\"Operative\"]",
                "required_guids_json": "[]",
                "snap_point_tags_json": "[]",
            },
        )

        self.assertEqual(result, {"decoded": True})
        self.assertIsInstance(sent["customMessage"], dict)
        self.assertEqual(
            sent["customMessage"]["query_tags_json"],  # type: ignore[index]
            "[\"Operative\"]",
        )
        self.assertEqual(
            sent["customMessage"]["query_tag_count"],  # type: ignore[index]
            1,
        )
        self.assertEqual(
            sent["customMessage"]["query_tag_1"],  # type: ignore[index]
            "Operative",
        )
        self.assertEqual(
            sent["customMessage"]["required_guid_count"],  # type: ignore[index]
            0,
        )
        self.assertEqual(
            sent["customMessage"]["snap_point_tag_count"],  # type: ignore[index]
            0,
        )
        self.assertNotIn("args", sent["customMessage"])  # type: ignore[arg-type]

    def test_loopback_bridge_response_releases_the_matching_waiter(self) -> None:
        bridge = TTSBridge()
        request_id = "response-transport-test"
        waiter: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        with bridge._pending_guard:
            bridge._pending[request_id] = waiter

        gateway = HttpGateway(host="127.0.0.1", port=0)
        gateway.configure_bridge_response(
            lambda response: bridge.deliver_response(response, transport="http")
        )
        gateway.start()
        try:
            payload = {
                "channel": "tts-mcp",
                "event": "mcp_response",
                "requestId": request_id,
                "ok": True,
                "result": {"objects": [{"guid": "abcdef"}]},
            }
            request = Request(
                f"http://127.0.0.1:{gateway.server.server_port}/bridge/response",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read().decode("utf-8")), {"ok": True})
            self.assertEqual(waiter.get(timeout=1), payload)
        finally:
            gateway.close()
            with bridge._pending_guard:
                bridge._pending.pop(request_id, None)
