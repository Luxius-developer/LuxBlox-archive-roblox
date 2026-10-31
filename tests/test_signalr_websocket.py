"""SignalR 1.x WebSocket transport contract checks."""
import base64
import hashlib
import unittest
from server import realtime


class SignalRWebSocketTests(unittest.TestCase):
    def test_negotiate_advertises_real_websocket_transport(self):
        response = realtime.negotiate(b"secret", 2, "1.5")
        self.assertTrue(response["TryWebSockets"])
        self.assertEqual(response["ProtocolVersion"], "1.5")
        self.assertIn("ConnectionToken", response)
        self.assertTrue(realtime.valid(b"secret", response["ConnectionToken"], 2))
        self.assertFalse(realtime.valid(b"secret", response["ConnectionToken"], 7))

    def test_signalr_endpoint_is_unchanged(self):
        self.assertEqual(realtime.PREFIX, "/realtime/notifications/signalr")


if __name__ == "__main__":
    unittest.main()
