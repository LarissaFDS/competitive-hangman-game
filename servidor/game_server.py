import socket
import threading
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import recv_msgs


HOST = "localhost"
PORT = 5000


def handle_client(client_socket, client_address):
    """Atende um cliente conectado em uma thread separada."""
    print(f"Cliente conectado: {client_address}")

    recv_buffer = [""]

    try:
        while True:
            messages = recv_msgs(client_socket, recv_buffer)
            if not messages:
                print(f"Cliente encerrou a conexao: {client_address}")
                break

            for msg in messages:
                print(f"Mensagem recebida de {client_address}: {msg}")

                response = "Mensagem recebida pelo servidor"
                client_socket.sendall(response.encode("utf-8"))
    except ConnectionResetError:
        print(f"Cliente desconectou inesperadamente: {client_address}")
    finally:
        client_socket.close()
        print(f"Conexao encerrada: {client_address}")


def start_server():
    """Inicia o servidor TCP."""
    # O socket TCP abre um ponto de comunicacao na rede.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(f"Servidor escutando em {HOST}:{PORT}")

    try:
        while True:
            client_socket, client_address = server_socket.accept()

            # Cada thread permite atender um cliente sem bloquear os demais.
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
            )
            client_thread.start()
    except KeyboardInterrupt:
        print("\nServidor encerrado manualmente.")
    finally:
        server_socket.close()


if __name__ == "__main__":
    start_server()
