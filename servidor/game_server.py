import socket
import sys
import threading
import argparse # <--- ADICIONE ESTE IMPORT
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.protocol import recv_msgs, send_msg
from servidor.game_state import GameState
from servidor.word_manager import load_words, pick_word


parser = argparse.ArgumentParser(description="Inicia o servidor do jogo da forca.")
parser.add_argument("--host", type=str, default="0.0.0.0", help="IP para escutar (0.0.0.0 para LAN)")
parser.add_argument("--port", type=int, default=5000, help="Porta do servidor")
args = parser.parse_args()

HOST = args.host
PORT = args.port


MIN_PLAYERS = 2
MAX_CLIENTS = 3
WORD_SOLVED_DELAY_SECONDS = 2

WORDS_PATH = PROJECT_ROOT / "assets" / "palavras.txt"
available_words = []

#Estado global da partida — compartilhado entre todas as threads.
game_state = GameState()
next_player_id = 1
next_player_id_lock = threading.Lock()
ready_player_ids: set[int] = set()
ready_lock = threading.Lock()
last_game_over_payload = None

def _broadcast_state(status_message: str | None = None) -> None:
    game_state.broadcast("STATE_UPDATE", game_state.get_state_payload(status_message))


def _pop_next_word() -> tuple[str, str] | None:
    if not available_words:
        return None

    word_tuple = pick_word(available_words)
    available_words.remove(word_tuple)
    return word_tuple


def _start_next_round(
    reset_scores: bool,
    active_player_ids: set[int] | None = None,
) -> bool:
    word_tuple = _pop_next_word()
    if word_tuple is None:
        return False

    word, category = word_tuple
    if reset_scores and active_player_ids is None:
        active_player_ids = game_state.connected_player_ids()

    game_state.start_game(
        word,
        category,
        reset_scores=reset_scores,
        active_player_ids=active_player_ids,
    )
    game_state.broadcast("GAME_START", {
        "category":    category,
        "word_length": len(word),
        "active_player_ids": list(game_state.active_player_ids()),
    })
    _broadcast_state()
    print(f"[GAME] Round iniciado! Palavra: {word} ({category})")
    return True


def _broadcast_game_over(winner_override: dict | None = None) -> None:
    global last_game_over_payload

    game_state.mark_ended()
    winner = winner_override or game_state.determine_winner()
    payload = {
        "winner_id":   winner["id"]   if winner else None,
        "winner_name": winner["name"] if winner else None,
        "word":        game_state.current_word(),
        "scores":      game_state.get_final_scores(),
    }
    last_game_over_payload = payload
    with ready_lock:
        ready_player_ids.clear()
    game_state.broadcast("GAME_OVER", payload)


def _handle_word_solved() -> None:
    _broadcast_state("Palavra descoberta! Trocando palavra...")
    time.sleep(WORD_SOLVED_DELAY_SECONDS)

    if game_state.current_phase() != PLAYING:
        return

    if _start_next_round(reset_scores=False):
        return

    print("[GAME] Banco de palavras esgotado.")
    _broadcast_game_over()


def _handle_ready(player_id: int) -> None:
    global available_words

    if game_state.current_phase() != ENDED:
        return

    connected_ids = game_state.connected_player_ids()
    if player_id not in connected_ids:
        return

    with ready_lock:
        ready_player_ids.add(player_id)
        ready_connected_ids = ready_player_ids & connected_ids
        if len(ready_connected_ids) < MIN_PLAYERS:
            return
        starting_player_ids = set(ready_connected_ids)
        ready_player_ids.clear()

    available_words = load_words(WORDS_PATH)
    if not _start_next_round(
        reset_scores=True,
        active_player_ids=starting_player_ids,
    ):
        game_state.broadcast("ERROR", {"message": "Banco de palavras vazio."})

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
        _handle_word_solved()
        return

    #Todos viraram espectadores (sem vencedor por acerto).
    if not game_state.active_player_ids():
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
        _handle_word_solved()
        return

    game_state.broadcast("WRONG_GUESS", {
        "player_id": player_id,
        "guess":     word.upper(),
    })

    if result["eliminated"]:
        game_state.broadcast("PLAYER_OUT", {"player_id": player_id})

    if not game_state.active_player_ids():
        _broadcast_game_over()
        return

    _broadcast_state()

def handle_client(conn: socket.socket, addr, player_id: int) -> None:
    """Atende um cliente em thread dedicada."""
    global available_words

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

                    connected = game_state.connected_count()
                    send_msg(conn, "GAME_START", {
                        "your_id":      player_id,
                        "player_count": connected,
                        "category":     game_state.category,
                        "word_length":  len(game_state.word),
                        "active_player_ids": list(game_state.active_player_ids()),
                    })

                    if game_state.current_phase() == PLAYING:
                        _broadcast_state()
                        continue

                    if game_state.current_phase() == ENDED:
                        if last_game_over_payload is not None:
                            send_msg(conn, "GAME_OVER", last_game_over_payload)
                        continue

                    #Mantém a sala em espera somente antes de a partida começar.
                    if connected < MIN_PLAYERS:
                        game_state.broadcast("WAITING", {
                            "connected": connected,
                            "needed":    MIN_PLAYERS,
                        })
                        continue

                    #Segundo jogador conectado — inicia a partida.
                    available_words = load_words(WORDS_PATH)
                    if not _start_next_round(reset_scores=True):
                        send_msg(conn, "ERROR", {"message": "Banco de palavras vazio."})

                elif msg_type == "GUESS_LETTER" and game_state.current_phase() == PLAYING:
                    letter = payload if isinstance(payload, str) else ""
                    _handle_guess(player_id, letter)

                elif msg_type == "GUESS_WORD" and game_state.current_phase() == PLAYING:
                    word = payload if isinstance(payload, str) else ""
                    _handle_word_guess(player_id, word)

                elif msg_type == "READY":
                    _handle_ready(player_id)

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
            _broadcast_game_over({
                "id": result["winner_id"],
                "name": result["winner_name"],
            })
        elif game_state.current_phase() == PLAYING:
            _broadcast_state()

        try:
            conn.close()
        except OSError:
            pass

def accept_loop(server_sock: socket.socket) -> None:
    global next_player_id

    while True:
        conn, addr = server_sock.accept()

        with next_player_id_lock:
            if game_state.connected_count() >= MAX_CLIENTS:
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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor do jogo da forca competitivo.")
    parser.add_argument(
        "--host",
        default=HOST,
        help="Interface para escutar conexões. Use 0.0.0.0 para LAN.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help="Porta TCP do servidor.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((args.host, args.port))
    server_sock.listen()
    print(f"Servidor escutando em {args.host}:{args.port}")

    try:
        accept_loop(server_sock)
    except KeyboardInterrupt:
        print("\nServidor encerrado manualmente.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
