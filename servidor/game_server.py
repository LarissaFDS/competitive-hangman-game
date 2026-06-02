import socket
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import recv_msgs, send_msg

HOST = "localhost"
PORT = 5000
MAX_CLIENTS = 3

clients: dict[int, socket.socket] = {}
clients_lock = threading.Lock()
next_player_id = 1


def handle_client(conn: socket.socket, addr, player_id: int) -> None:
    """Atende um cliente em thread dedicada."""
    recv_buffer = [""]

    try:
        while True:
            messages = recv_msgs(conn, recv_buffer)
            if not messages:
                break

            for msg in messages:
                msg_type = msg.get("type")
                payload = msg.get("payload")

                if msg_type == "JOIN":
                    player_name = payload if isinstance(payload, str) else str(payload)
                    with clients_lock:
                        player_count = len(clients)

                    print(f"[JOIN] Jogador {player_id} ({player_name}) entrou")
                    send_msg(
                        conn,
                        "WELCOME",
                        {"player_id": player_id, "player_count": player_count},
                    )
    except (ConnectionResetError, OSError):
        pass
    finally:
        with clients_lock:
            clients.pop(player_id, None)

        try:
            conn.close()
        except OSError:
            pass
        print(f"[-] Jogador {player_id} desconectado")


def accept_loop(server_sock: socket.socket) -> None:
    """Loop principal de aceitação de conexões."""
    global next_player_id

    while True:
        conn, addr = server_sock.accept()

        with clients_lock:
            if len(clients) >= MAX_CLIENTS:
                send_msg(
                    conn,
                    "ERROR",
                    {"message": "Servidor lotado. Limite de 3 jogadores."},
                )
                conn.close()
                continue

            player_id = next_player_id
            next_player_id += 1
            clients[player_id] = conn

        print(f"[+] Jogador {player_id} conectado")
        client_thread = threading.Thread(
            target=handle_client,
            args=(conn, addr, player_id),
            daemon=True,
        )
        client_thread.start()


def main() -> None:
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen()
    print(f"Servidor escutando em {HOST}:{PORT}")

    try:
        accept_loop(server_sock)
    except KeyboardInterrupt:
        print("\nServidor encerrado manualmente.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
