"""Protocol framing helpers for newline-delimited JSON messages.

Message types catalog:
JOIN, GUESS_LETTER, GUESS_WORD, WELCOME, WAITING, GAME_START,
STATE_UPDATE, WRONG_GUESS, CORRECT_GUESS, PLAYER_OUT, GAME_OVER, ERROR.
"""

from __future__ import annotations

import json
import socket
from typing import Any


def send_msg(sock: socket.socket, msg_type: str, data: Any) -> None:
    """Serialize and send one protocol message."""
    payload = {"type": msg_type, "payload": data}
    encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(encoded)


def recv_msgs(sock: socket.socket, buffer: list[str]) -> list[dict[str, Any]]:
    """Read from socket, accumulate fragments, and return complete messages."""
    if not buffer:
        buffer.append("")

    chunk = sock.recv(4096)
    if not chunk:
        return []

    buffer[0] += chunk.decode("utf-8")
    parts = buffer[0].split("\n")
    buffer[0] = parts.pop()

    messages: list[dict[str, Any]] = []
    for raw in parts:
        line = raw.strip()
        if not line:
            continue
        messages.append(json.loads(line))

    return messages
