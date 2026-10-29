"""Minimal legacy SignalR long-poll handshake; no notification delivery yet."""
import hashlib
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
            "ConnectionTimeout": 110.0, "TryWebSockets": False,
            "ProtocolVersion": protocol, "TransportConnectTimeout": 5.0,
            "LongPollDelay": 1.0}
