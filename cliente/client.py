import json
import socket
import threading
import sys
import argparse 
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import send_msg, recv_msgs
from local_state import LocalGameState
from interface.renderer import render_state, render_waiting, render_game_over


def parse_args():
    parser = argparse.ArgumentParser(description="Cliente do jogo da forca competitivo.")
    parser.add_argument(
        "host",
        nargs="?",
        default="localhost",
        help="IP ou hostname do servidor. Ex: 192.168.1.10",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Porta TCP do servidor.",
    )
    return parser.parse_args()

def recv_loop(sock, state):
    #comportamento full-duplex da aplicação (envia e recebe simultaneamente).
    #Buffer acumulador de fragmentos TCP — mesma abordagem usada no servidor.
    #recv_msgs() acumula chunks parciais e só retorna mensagens quando o delimitador '\n' é encontrado,
    #evitando que JSONs fragmentados sejam entregues incompletos ao LocalGameState.
    recv_buffer = [""]

    try:
        while True:
            #recv_msgs() é bloqueante: a thread fica ociosa até o SO entregar dados.
            #Retorna lista vazia quando o servidor envia TCP FIN (conexão encerrada).
            messages = recv_msgs(sock, recv_buffer)

            if not messages:
                print("\nConexão encerrada pelo servidor.")
                break

            for msg in messages:
                msg_type = msg.get("type")

                #Atualiza a fonte de verdade com a mensagem já montada e validada.
                state.update(json.dumps(msg))

                #Renderiza a tela sempre que o estado mudar — exceto mensagens de
                #controle que não alteram a tela principal (ex: WELCOME, ERROR).
                if msg_type in ("GAME_START", "STATE_UPDATE", "WRONG_GUESS",
                                "CORRECT_GUESS", "PLAYER_OUT"):
                    render_state(state)

                elif msg_type == "WAITING":
                    payload = msg.get("payload", {})
                    render_waiting(
                        payload.get("connected", 0),
                        payload.get("needed", 2),
                    )

                elif msg_type == "GAME_OVER":
                    payload = msg.get("payload", {})
                    render_game_over(
                        winner_name=payload.get("winner_name"),
                        word=payload.get("word", "?"),
                        scores=payload.get("scores", []),
                    )

                print("> ", end="", flush=True)

    except (ConnectionResetError, OSError):
        #captura o recebimento de um pacote TCP RST (reset).
        print("\nAviso: o servidor foi desconectado inesperadamente.")
    except Exception as e:
        print(f"\nErro inesperado no cliente: {e}")
    finally:
        state.connection_closed = True
        print("Encerrando conexão...")
        sys.exit(0)

def main():
    args = parse_args()
    player_name = input("Digite seu nome de jogador: ")
    state = LocalGameState()
    #criação do socket:
    #AF_INET: define a família de endereçamento como IPv4 (camada de rede).
    #SOCK_STREAM: define o uso do protocolo TCP.
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        #onicia o "3-way handshake" do TCP (SYN, SYN-ACK, ACK) com o servidor.
        client_socket.connect((args.host, args.port))
    except ConnectionRefusedError:
        print(f"Não foi possível conectar. O servidor está rodando em {args.host}:{args.port}?")
        return

    #construção da PDU (protocol data unit) da camada de aplicação.
    try:
        send_msg(client_socket, "JOIN", player_name)
    except OSError:
        print("Não foi possível enviar JOIN. A conexão foi encerrada.")
        client_socket.close()
        return
    #cria uma thread separada para lidar com a recepção bloqueante do socket
    recv_thread = threading.Thread(target=recv_loop, args=(client_socket, state), daemon=True)
    recv_thread.start()

    #Loop principal (thread principal) focado apenas em I/O do usuário e envio (upload)
    try:
        while True:
            if state.connection_closed:
                break

            user_input = input("> ").strip()

            if state.phase == "ENDED":
                if not user_input:
                    send_msg(client_socket, "READY", {"player_id": state.my_id})
                    print("Confirmação enviada. Aguardando outro jogador...")
                else:
                    print("Pressione ENTER para jogar novamente.")
                continue

            if state.is_spectator:
                print("[Você é espectador]")
                continue

            if not user_input:
                continue
            if not user_input.isalpha():
                print("Aviso: apenas letras (A-Z) são permitidas.")
                continue

            #Regras do protocolo de aplicação para definir o "type" do payload
            if len(user_input) == 1:
                msg_type = "GUESS_LETTER"
            else:
                msg_type = "GUESS_WORD"
            #envia para o servidor.
            send_msg(client_socket, msg_type, user_input.upper())
    except KeyboardInterrupt:
        print("\nSaindo do jogo...")
    except (ConnectionResetError, BrokenPipeError, OSError):
        print("\nConexão com o servidor encerrada.")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()
