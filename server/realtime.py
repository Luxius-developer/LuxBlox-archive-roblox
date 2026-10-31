"""Minimal legacy SignalR long-poll handshake; no notification delivery yet."""
import base64
import hashlib
import json
import socket
import struct
import hmac
import secrets
import time

PREFIX = "/realtime/notifications/signalr"


def issue(secret, user_id):
    connection_id = secrets.token_hex(16)
    data = f"{user_id}.{int(time.time()) + 3600}.{connection_id}"
    signature = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    return connection_id, data + "." + signature


def valid(secret, token, user_id):
    if len(token) > 256:
        return False
    try:
        owner, expiry, connection_id, signature = token.split(".")
        data = f"{owner}.{expiry}.{connection_id}"
        expected = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        return (owner == str(user_id) and int(expiry) > time.time()
                and hmac.compare_digest(signature, expected))
    except (ValueError, TypeError):
        return False


def negotiate(secret, user_id, protocol):
    connection_id, token = issue(secret, user_id)
    return {"Url": PREFIX, "ConnectionToken": token, "ConnectionId": connection_id,
            "KeepAliveTimeout": 20.0, "DisconnectTimeout": 30.0,
            "ConnectionTimeout": 110.0, "TryWebSockets": True,
            "ProtocolVersion": protocol, "TransportConnectTimeout": 5.0,
            "LongPollDelay": 1.0}


# Minimal RFC 6455 WebSocket transport for legacy SignalR 1.x.
# Frames are deliberately bounded; no message push is advertised yet.
def websocket(handler, action):
    if handler.headers.get("Upgrade", "").lower() != "websocket" or \
            "upgrade" not in handler.headers.get("Connection", "").lower():
        handler.send_error(400, "WebSocket upgrade required")
        return
    key = handler.headers.get("Sec-WebSocket-Key", "")
    try:
        raw_key = base64.b64decode(key, validate=True)
    except (ValueError, Exception):
        handler.send_error(400, "Invalid WebSocket key")
        return
    if len(raw_key) != 16 or handler.headers.get("Sec-WebSocket-Version") != "13":
        handler.send_error(400, "Unsupported WebSocket handshake")
        return
    accept = base64.b64encode(hashlib.sha1((key +
        "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()
    handler.wfile.flush()
    handler.connection.settimeout(10)

    def frame(opcode, payload=b""):
        if len(payload) > 65535:
            return
        header = bytes([0x80 | opcode, len(payload)]) if len(payload) < 126 else \
            bytes([0x80 | opcode, 126]) + struct.pack("!H", len(payload))
        handler.wfile.write(header + payload)
        handler.wfile.flush()

    def read_exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = handler.rfile.read(size - len(data))
            if not chunk:
                raise EOFError()
            data.extend(chunk)
        return bytes(data)

    frame(1, json.dumps({"C": "0", "M": [], "S": 1}).encode("utf-8"))
    deadline = time.monotonic() + 65
    try:
        while time.monotonic() < deadline:
            try:
                head = read_exact(2)
            except socket.timeout:
                frame(9, b"keepalive")
                continue
            opcode = head[0] & 15
            masked = bool(head[1] & 128)
            size = head[1] & 127
            if size == 126:
                size = struct.unpack("!H", read_exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", read_exact(8))[0]
            if not masked or size > 65536:
                frame(8, b"")
                break
            mask = read_exact(4)
            payload = read_exact(size)
            payload = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
            if opcode == 8:
                frame(8, payload[:125])
                break
            if opcode == 9:
                frame(10, payload[:125])
    except (EOFError, OSError, ValueError):
        pass
