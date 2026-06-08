from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import recv_msgs, send_msg


def test_three_messages_in_sequence() -> None:
    sender, receiver = socket.socketpair()
    buffer = [""]

    try:
        send_msg(sender, "JOIN", {"player": "Ana"})
        send_msg(sender, "GUESS_LETTER", {"letter": "a"})
        send_msg(sender, "GUESS_WORD", {"word": "python"})

        received = []
        while len(received) < 3:
            received.extend(recv_msgs(receiver, buffer))

        assert received[0]["type"] == "JOIN"
        assert received[1]["type"] == "GUESS_LETTER"
        assert received[2]["type"] == "GUESS_WORD"

        print("Mensagens reconstruidas em sequencia:")
        for msg in received:
            print(msg)
    finally:
        sender.close()
        receiver.close()


def test_fragmentation() -> None:
    sender, receiver = socket.socketpair()
    buffer = [""]

    try:
        raw = (
            json.dumps(
                {"type": "STATE_UPDATE", "payload": {"masked": "_ _ _ _"}},
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")

        split_at = len(raw) // 2
        sender.send(raw[:split_at])
        partial = recv_msgs(receiver, buffer)
        assert partial == [], "Nao deveria montar mensagem completa no primeiro chunk"

        sender.send(raw[split_at:])
        complete = recv_msgs(receiver, buffer)

        assert len(complete) == 1
        assert complete[0]["type"] == "STATE_UPDATE"
        assert complete[0]["payload"]["masked"] == "_ _ _ _"

        print("Teste de fragmentacao passou com sucesso.")
    finally:
        sender.close()
        receiver.close()


def test_import_from_client_and_server_dirs() -> None:
    server_dir = PROJECT_ROOT / "servidor"
    client_dir = PROJECT_ROOT / "cliente"

    for base in (server_dir, client_dir):
        root_str = str(base.parent)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

        module = __import__("utils.protocol", fromlist=["send_msg"])
        assert hasattr(module, "send_msg")
        assert hasattr(module, "recv_msgs")

    print("Import do modulo utils.protocol validado para servidor/ e cliente/.")


if __name__ == "__main__":
    test_three_messages_in_sequence()
    test_fragmentation()
    test_import_from_client_and_server_dirs()
    print("Todos os testes de protocolo passaram sem erros.")
