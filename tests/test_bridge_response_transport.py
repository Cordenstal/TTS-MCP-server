from __future__ import annotations

import json
import queue
import unittest
from urllib.request import Request, urlopen

from http_gateway import HttpGateway
from server import TTSBridge


class BridgeResponseTransportTests(unittest.TestCase):
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

