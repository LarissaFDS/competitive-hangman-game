import socket
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import recv_msgs, send_msg
from servidor.game_state import GameState
from servidor.word_manager import load_words, pick_word

HOST = "localhost"
PORT = 5000
MIN_PLAYERS = 2
MAX_CLIENTS = 3

WORDS_PATH = PROJECT_ROOT / "assets" / "palavras.txt"

#Estado global da partida — compartilhado entre todas as threads.
game_state = GameState()
next_player_id = 1
next_player_id_lock = threading.Lock()

def _broadcast_state() -> None:
    game_state.broadcast("STATE_UPDATE", game_state.get_state_payload())


def _broadcast_game_over() -> None:
    winner = game_state.determine_winner()
    payload = {
        "winner_id":   winner["id"]   if winner else None,
        "winner_name": winner["name"] if winner else None,
        "word":        "".join(game_state.revealed),
        "scores":      game_state.get_final_scores(),
    }
    game_state.broadcast("GAME_OVER", payload)

    #Reseta o estado e avisa os clientes para aguardarem nova partida.
    game_state.reset()
    game_state.broadcast("WAITING", {"connected": 0, "needed": MIN_PLAYERS})


def _handle_guess(player_id: int, letter: str) -> None:
    result = game_state.process_guess(player_id, letter)

    if not result["valid"]:
        return

    if result["correct"]:
        game_state.broadcast("CORRECT_GUESS", {
            "player_id": player_id,
            "letter":    letter.upper(),
            "positions": result["positions"],
        })
    else:
        game_state.broadcast("WRONG_GUESS", {
            "player_id": player_id,
            "guess":     letter.upper(),
        })

    #Jogador zerou tentativas → espectador.
    if result["eliminated"]:
        game_state.broadcast("PLAYER_OUT", {"player_id": player_id})

    #Alguém acertou a palavra.
    if result["won"]:
        _broadcast_game_over()
        return

    #Todos viraram espectadores (sem vencedor por acerto).
    active = [p for p in game_state.players.values() if not p.is_spectator]
    if not active:
        _broadcast_game_over()
        return

    _broadcast_state()


def _handle_word_guess(player_id: int, word: str) -> None:
    result = game_state.process_word_guess(player_id, word)

    if not result["valid"]:
        return

    if result["correct"]:
        game_state.broadcast("CORRECT_GUESS", {
            "player_id": player_id,
            "word":      word.upper(),
            "positions": result["positions"],
        })
        _broadcast_game_over()
        return

    game_state.broadcast("WRONG_GUESS", {
        "player_id": player_id,
        "guess":     word.upper(),
    })

    if result["eliminated"]:
        game_state.broadcast("PLAYER_OUT", {"player_id": player_id})

    active = [p for p in game_state.players.values() if not p.is_spectator]
    if not active:
        _broadcast_game_over()
        return

    _broadcast_state()

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
                payload  = msg.get("payload")

                if msg_type == "JOIN":
                    player_name = payload if isinstance(payload, str) else str(payload)
                    game_state.add_player(player_id, player_name, sock=conn)

                    print(f"[JOIN] Jogador {player_id} ({player_name}) entrou")

                    send_msg(conn, "GAME_START", {
                        "your_id": player_id,
                        "player_count": len(game_state.players),
                    })

                    #Mantém todos atualizados sobre quantos já estão na sala.
                    connected = len(game_state.players)
                    game_state.broadcast("WAITING", {
                        "connected": connected,
                        "needed":    MIN_PLAYERS,
                    })

                    #Segundo jogador conectado — inicia a partida.
                    if connected >= MIN_PLAYERS and game_state.phase == "WAITING":
                        words   = load_words(WORDS_PATH)
                        word, category = pick_word(words)
                        game_state.start_game(word, category)

                        game_state.broadcast("GAME_START", {
                            "category":    category,
                            "word_length": len(word),
                        })
                        _broadcast_state()
                        print(f"[GAME] Partida iniciada! Palavra: {word} ({category})")

                elif msg_type == "GUESS_LETTER" and game_state.phase == "PLAYING":
                    letter = payload if isinstance(payload, str) else ""
                    _handle_guess(player_id, letter)

                elif msg_type == "GUESS_WORD" and game_state.phase == "PLAYING":
                    word = payload if isinstance(payload, str) else ""
                    _handle_word_guess(player_id, word)

    except (ConnectionResetError, OSError):
        #Desconexão abrupta (TCP RST ou terminal fechado).
        pass

    finally:
        print(f"[-] Jogador {player_id} desconectado")

        #remove_player marca o jogador como espectador e verifica se
        #sobrou apenas 1 ativo — nesse caso retorna trigger_game_over.
        result = game_state.remove_player(player_id)
        game_state.broadcast("PLAYER_OUT", {"player_id": player_id})

        if result and result.get("trigger_game_over"):
            print(f"[GAME] Jogador {result['winner_name']} venceu por W.O.")
            _broadcast_game_over()

        try:
            conn.close()
        except OSError:
            pass

def accept_loop(server_sock: socket.socket) -> None:
    global next_player_id

    while True:
        conn, addr = server_sock.accept()

        with next_player_id_lock:
            if len(game_state.sockets) >= MAX_CLIENTS:
                send_msg(conn, "ERROR", {"message": "Servidor lotado. Limite de 3 jogadores."})
                conn.close()
                continue

            player_id       = next_player_id
            next_player_id += 1

        print(f"[+] Jogador {player_id} conectado de {addr}")
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