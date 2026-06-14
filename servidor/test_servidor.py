from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from game_state import GameState, PLAYING, ENDED, WAITING, DEFAULT_ATTEMPTS
from utils.protocol import send_msg
import game_server as srv

srv.WORDS_PATH = ROOT.parent / "assets" / "palavras.txt"

def _make_game(word: str = "GATO") -> GameState:
    gs = GameState()
    gs.phase = PLAYING
    gs.word = gs._normalize_word(word)
    gs.revealed = ["_" if c.isalpha() else c for c in gs.word]
    return gs


def _read_all(sock: socket.socket) -> list[dict]:
    msgs = []
    sock.setblocking(False)
    buf = b""
    try:
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            except (BlockingIOError, OSError):
                break
    finally:
        sock.setblocking(True)

    for line in buf.decode("utf-8").split("\n"):
        line = line.strip()
        if line:
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return msgs


def _wait_for(sock: socket.socket, msg_type: str, timeout: float = 3.0) -> list[dict]:
    deadline = time.time() + timeout
    all_msgs = []
    buf = b""
    sock.settimeout(0.1)
    try:
        while time.time() < deadline:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                pass
            except OSError:
                break

            decoded = buf.decode("utf-8", errors="replace")
            lines = decoded.split("\n")
            buf = lines.pop().encode("utf-8") 
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    all_msgs.append(msg)
                    if msg.get("type") == msg_type:
                        all_msgs.extend(_read_all(sock))
                        return all_msgs
                except json.JSONDecodeError:
                    pass
    finally:
        sock.settimeout(None)
    return all_msgs


def _setup_server():
    gs = GameState()
    srv.game_state = gs

    def spawn(sock, player_id):
        t = threading.Thread(
            target=srv.handle_client,
            args=(sock, ("127.0.0.1", 0), player_id),
            daemon=True,
        )
        t.start()
        return t

    return gs, spawn


def _join_two(spawn, c1, c2) -> None:
    spawn(c1[0], 1)
    send_msg(c1[1], "JOIN", "Ana")
    time.sleep(0.15)
    spawn(c2[0], 2)
    send_msg(c2[1], "JOIN", "Bruno")

def test_gs_concorrencia_letra_repetida():
    falhas = []
    for i in range(100):
        gs = _make_game("GATO")
        gs.add_player(1, "Ana")
        gs.add_player(2, "Bruno")
        resultados = []
        lock_res = threading.Lock()

        def chutar(pid):
            r = gs.process_guess(pid, "G")
            with lock_res:
                resultados.append(r)

        t1 = threading.Thread(target=chutar, args=(1,))
        t2 = threading.Thread(target=chutar, args=(2,))
        t1.start(); t2.start()
        t1.join();  t2.join()
        validos = [r for r in resultados if r["valid"]]
        if len(validos) != 1:
            falhas.append(f"Iteração {i+1}: {len(validos)} válidos")

    assert not falhas, "\n".join(falhas)
    print("[OK] game_state — Concorrência: nunca 2 chutes válidos para a mesma letra (100x)")


def test_gs_letra_repetida_sequencial():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    assert gs.process_guess(1, "G")["valid"] is True
    assert gs.process_guess(1, "G")["valid"] is False
    print("[OK] game_state — Letra repetida retorna valid:False")


def test_gs_chute_correto():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    r = gs.process_guess(1, "G")
    assert r["valid"] and r["correct"] and gs.revealed[0] == "G"
    assert gs.players[1].score == 1
    print("[OK] game_state — Chute correto atualiza revealed e score")


def test_gs_chute_errado_decrementa():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    r = gs.process_guess(1, "Z")
    assert r["valid"] and not r["correct"]
    assert gs.players[1].attempts == DEFAULT_ATTEMPTS - 1
    print("[OK] game_state — Chute errado decrementa attempts")


def test_gs_eliminacao():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    r = None
    for letra in ["Z", "X", "W", "V", "U", "Q"]:
        r = gs.process_guess(1, letra)
    assert gs.players[1].is_spectator is True
    assert r["eliminated"] is True
    print("[OK] game_state — Jogador com 6 erros vira espectador")


def test_gs_espectador_bloqueado():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    gs.players[1].is_spectator = True
    r = gs.process_guess(1, "G")
    assert r["valid"] is False and r["eliminated"] is True
    print("[OK] game_state — Espectador não consegue chutar")


def test_gs_vitoria_letra():
    gs = _make_game("GA")
    gs.add_player(1, "Ana")
    gs.process_guess(1, "G")
    assert gs.process_guess(1, "A")["won"] is True
    print("[OK] game_state — Revelar todas as letras retorna won:True")


def test_gs_vitoria_palavra():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    r = gs.process_word_guess(1, "gato")
    assert r["valid"] and r["correct"] and r["won"]
    print("[OK] game_state — Adivinhar a palavra inteira retorna won:True")


def test_gs_palavra_errada():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    r = gs.process_word_guess(1, "LEAO")
    assert r["valid"] and not r["correct"]
    assert gs.players[1].attempts == DEFAULT_ATTEMPTS - 1
    print("[OK] game_state — Palavra errada decrementa attempts")


def test_gs_remove_player_trigger_game_over():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    gs.add_player(2, "Bruno")
    result = gs.remove_player(2)
    assert result is not None and result["trigger_game_over"] is True
    assert result["winner_name"] == "Ana" and gs.phase == ENDED
    print("[OK] game_state — remove_player retorna trigger_game_over quando sobra 1 ativo")


def test_gs_remove_player_sem_trigger():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    gs.add_player(2, "Bruno")
    gs.add_player(3, "Carla")
    assert gs.remove_player(3) is None
    assert gs.phase == PLAYING
    print("[OK] game_state — remove_player retorna None quando há 2+ ativos")


def test_gs_broadcast_sem_runtime_error():
    gs = _make_game("GATO")
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()
    gs.add_player(1, "Ana",   sock=s1)
    gs.add_player(2, "Bruno", sock=s2)
    s2.close(); c2.close()
    try:
        gs.broadcast("STATE_UPDATE", {"phase": "PLAYING"})
    except RuntimeError as e:
        assert False, f"broadcast lançou RuntimeError: {e}"
    finally:
        s1.close(); c1.close()
    print("[OK] game_state — broadcast não lança RuntimeError com socket morto")


def test_gs_desempate_letras_unicas():
    gs = _make_game("GATO")
    gs.add_player(1, "Ana")
    gs.add_player(2, "Bruno")
    gs.players[1].score = 5
    gs.players[1].correct_unique_letters = {"G", "A"}
    gs.players[2].score = 5
    gs.players[2].correct_unique_letters = {"G"}
    assert gs.get_final_scores()[0]["name"] == "Ana"
    print("[OK] game_state — Desempate por letras únicas funciona")


def test_gs_start_e_reset():
    gs = GameState()
    gs.add_player(1, "Ana")
    s1, c1 = socket.socketpair()
    gs.sockets[1] = s1
    gs.start_game("GATO", "Animais")
    assert gs.phase == PLAYING and gs.word == "GATO"
    gs.reset()
    assert gs.phase == WAITING and gs.players == {}
    assert gs.sockets[1] is s1
    s1.close(); c1.close()
    print("[OK] game_state — start_game e reset funcionam corretamente")


def test_gs_normalizacao_acento():
    gs = GameState()
    gs.phase = PLAYING
    gs.word = gs._normalize_word("LEÃO")
    gs.revealed = ["_"] * len(gs.word)
    gs.add_player(1, "Ana")
    assert gs.word == "LEAO"
    r = gs.process_guess(1, "ã")
    assert r["valid"] and r["correct"]
    print("[OK] game_state — Acentos normalizados em palavra e chute")


# ===========================================================================
# BLOCO 2 — game_server.py
# ===========================================================================

def test_srv_join_responde_game_start():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    spawn(s1, 1)

    send_msg(c1, "JOIN", "Ana")
    msgs = _wait_for(c1, "GAME_START", timeout=2.0)
    tipos = [m["type"] for m in msgs]

    assert "GAME_START" in tipos, f"Esperado GAME_START, recebido: {tipos}"
    game_start = next(m for m in msgs if m["type"] == "GAME_START")
    assert game_start["payload"]["your_id"] == 1

    c1.close()
    print("[OK] game_server — JOIN responde com GAME_START contendo your_id")


def test_srv_dois_jogadores_iniciam_partida():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()

    spawn(s1, 1)
    send_msg(c1, "JOIN", "Ana")
    _wait_for(c1, "GAME_START", timeout=2.0)

    spawn(s2, 2)
    send_msg(c2, "JOIN", "Bruno")

    msgs1 = _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    msgs2 = _wait_for(c2, "STATE_UPDATE", timeout=3.0)
    tipos1 = [m["type"] for m in msgs1]
    tipos2 = [m["type"] for m in msgs2]

    assert "STATE_UPDATE" in tipos1, f"c1 não recebeu STATE_UPDATE: {tipos1}"
    assert "STATE_UPDATE" in tipos2, f"c2 não recebeu STATE_UPDATE: {tipos2}"
    assert gs.phase == PLAYING

    c1.close(); c2.close()
    print("[OK] game_server — 2 jogadores conectados iniciam partida e recebem STATE_UPDATE")


def test_srv_guess_letter_broadcast():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()

    spawn(s1, 1)
    send_msg(c1, "JOIN", "Ana")
    _wait_for(c1, "GAME_START", timeout=2.0)

    spawn(s2, 2)
    send_msg(c2, "JOIN", "Bruno")

    _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    _wait_for(c2, "STATE_UPDATE", timeout=3.0)

    primeira_letra = gs.word[0]
    send_msg(c1, "GUESS_LETTER", primeira_letra)

    msgs1 = _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    msgs2 = _wait_for(c2, "STATE_UPDATE", timeout=3.0)
    tipos1 = [m["type"] for m in msgs1]
    tipos2 = [m["type"] for m in msgs2]

    assert "CORRECT_GUESS" in tipos1 or "WRONG_GUESS" in tipos1, f"c1: {tipos1}"
    assert "CORRECT_GUESS" in tipos2 or "WRONG_GUESS" in tipos2, f"c2: {tipos2}"

    c1.close(); c2.close()
    print("[OK] game_server — Chute de letra faz broadcast do resultado para todos")


def test_srv_guess_word_correto_dispara_game_over():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()

    spawn(s1, 1)
    send_msg(c1, "JOIN", "Ana")
    _wait_for(c1, "GAME_START", timeout=2.0)

    spawn(s2, 2)
    send_msg(c2, "JOIN", "Bruno")

    _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    _wait_for(c2, "STATE_UPDATE", timeout=3.0)

    send_msg(c1, "GUESS_WORD", gs.word)

    msgs1 = _wait_for(c1, "GAME_OVER", timeout=3.0)
    msgs2 = _wait_for(c2, "GAME_OVER", timeout=3.0)
    tipos1 = [m["type"] for m in msgs1]
    tipos2 = [m["type"] for m in msgs2]

    assert "GAME_OVER" in tipos1, f"c1 não recebeu GAME_OVER: {tipos1}"
    assert "GAME_OVER" in tipos2, f"c2 não recebeu GAME_OVER: {tipos2}"
    game_over = next(m for m in msgs1 if m["type"] == "GAME_OVER")
    assert game_over["payload"]["winner_name"] == "Ana"

    c1.close(); c2.close()
    print("[OK] game_server — Adivinhar a palavra dispara GAME_OVER com vencedor correto")


def test_srv_desconexao_abrupta_nao_trava():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()

    spawn(s1, 1)
    send_msg(c1, "JOIN", "Ana")
    _wait_for(c1, "GAME_START", timeout=2.0)

    spawn(s2, 2)
    send_msg(c2, "JOIN", "Bruno")

    _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    _wait_for(c2, "STATE_UPDATE", timeout=3.0)
    gs.players[2].score = 99

    c2.close(); s2.close()

    msgs1 = _wait_for(c1, "GAME_OVER", timeout=3.0)
    tipos1 = [m["type"] for m in msgs1]

    assert "PLAYER_OUT" in tipos1 or "GAME_OVER" in tipos1, \
        f"c1 deveria ter recebido PLAYER_OUT ou GAME_OVER: {tipos1}"
    game_over = next((m for m in msgs1 if m["type"] == "GAME_OVER"), None)
    assert game_over is not None, f"c1 deveria ter recebido GAME_OVER: {tipos1}"
    assert game_over["payload"]["winner_name"] == "Ana", \
        f"Vencedor por sobrevivência deveria ser Ana: {game_over}"

    c1.close()
    print("[OK] game_server — Desconexão abrupta não trava; demais recebem PLAYER_OUT/GAME_OVER")


def test_srv_game_over_reseta_para_nova_partida():
    gs, spawn = _setup_server()
    s1, c1 = socket.socketpair()
    s2, c2 = socket.socketpair()

    spawn(s1, 1)
    send_msg(c1, "JOIN", "Ana")
    _wait_for(c1, "GAME_START", timeout=2.0)

    spawn(s2, 2)
    send_msg(c2, "JOIN", "Bruno")

    _wait_for(c1, "STATE_UPDATE", timeout=3.0)
    _wait_for(c2, "STATE_UPDATE", timeout=3.0)

    send_msg(c1, "GUESS_WORD", gs.word)

    msgs1 = _wait_for(c1, "WAITING", timeout=3.0)
    tipos1 = [m["type"] for m in msgs1]

    assert "WAITING" in tipos1, f"Após GAME_OVER deveria receber WAITING: {tipos1}"
    assert gs.phase == WAITING

    c1.close(); c2.close()
    print("[OK] game_server — Após GAME_OVER, estado reseta e envia WAITING para nova partida")

if __name__ == "__main__":
    print("=" * 60)
    print("Testes — game_state.py + game_server.py")
    print("=" * 60)

    print("\n--- game_state.py ---")
    test_gs_concorrencia_letra_repetida()
    test_gs_letra_repetida_sequencial()
    test_gs_chute_correto()
    test_gs_chute_errado_decrementa()
    test_gs_eliminacao()
    test_gs_espectador_bloqueado()
    test_gs_vitoria_letra()
    test_gs_vitoria_palavra()
    test_gs_palavra_errada()
    test_gs_remove_player_trigger_game_over()
    test_gs_remove_player_sem_trigger()
    test_gs_broadcast_sem_runtime_error()
    test_gs_desempate_letras_unicas()
    test_gs_start_e_reset()
    test_gs_normalizacao_acento()

    print("\n--- game_server.py ---")
    test_srv_join_responde_game_start()
    test_srv_dois_jogadores_iniciam_partida()
    test_srv_guess_letter_broadcast()
    test_srv_guess_word_correto_dispara_game_over()
    test_srv_desconexao_abrupta_nao_trava()
    test_srv_game_over_reseta_para_nova_partida()

    print("\n" + "=" * 60)
    print("Todos os testes passaram.")
    print("=" * 60)
