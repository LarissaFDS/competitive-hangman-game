import socket
import threading


HOST = "localhost"
PORT = 5000
BUFFER_SIZE = 1024


def handle_client(client_socket, client_address):
    """Atende um cliente conectado em uma thread separada."""
    print(f"Cliente conectado: {client_address}")

    try:
        while True:
            message = client_socket.recv(BUFFER_SIZE)

            if not message:
                print(f"Cliente encerrou a conexao: {client_address}")
                break

            decoded_message = message.decode("utf-8")
            print(f"Mensagem recebida de {client_address}: {decoded_message}")

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
