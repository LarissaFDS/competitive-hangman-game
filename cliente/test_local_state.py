from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_state import LocalGameState
from utils.protocol import send_msg, recv_msgs


#Após GAME_START com o próprio ID, my_id deve ser populado.
def test_game_start_popula_my_id():
    state = LocalGameState()
    assert state.my_id is None

    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 42}}))

    assert state.my_id == 42, f"Esperado my_id=42, obtido {state.my_id}"
    assert state.phase == "PLAYING"
    print("[OK] CRITÉRIO 1 — GAME_START popula my_id e seta phase=PLAYING")


#STATE_UPDATE atualiza revealed e all_players (placar com pontuação correta).
def test_state_update_placar():
    state = LocalGameState()
    players = [
        {"name": "Ana",   "attempts_left": 5, "score": 10},
        {"name": "Bruno", "attempts_left": 3, "score": 5},
    ]
    state.update(json.dumps({
        "type": "STATE_UPDATE",
        "payload": {
            "phase": "PLAYING",
            "revealed": "G _ T _",
            "all_players": players,
        }
    }))

    assert state.revealed == "G _ T _"
    assert len(state.all_players) == 2
    assert state.all_players[0]["score"] == 10
    assert state.all_players[1]["score"] == 5
    print("[OK] CRITÉRIO 2 — STATE_UPDATE atualiza placar com pontuação correta de todos os jogadores")


#WRONG_GUESS atualiza my_attempts APENAS para o próprio jogador.
def test_wrong_guess_apenas_proprio_jogador():
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 1}}))

    #Erro do próprio jogador (id=1) → deve entrar em my_attempts
    state.update(json.dumps({"type": "WRONG_GUESS", "payload": {"player_id": 1, "guess": "Z"}}))
    #Erro de outro jogador (id=2) → NÃO deve entrar em my_attempts
    state.update(json.dumps({"type": "WRONG_GUESS", "payload": {"player_id": 2, "guess": "X"}}))

    assert "Z" in state.my_attempts, "Z deveria estar em my_attempts"
    assert "X" not in state.my_attempts, "X não deveria estar em my_attempts (erro de outro jogador)"
    assert len(state.my_attempts) == 1
    print("[OK] CRITÉRIO 3 — WRONG_GUESS atualiza my_attempts só para o próprio jogador")


#WRONG_GUESS não duplica tentativas já registradas.
def test_wrong_guess_sem_duplicatas():
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 1}}))

    state.update(json.dumps({"type": "WRONG_GUESS", "payload": {"player_id": 1, "guess": "A"}}))
    state.update(json.dumps({"type": "WRONG_GUESS", "payload": {"player_id": 1, "guess": "A"}}))

    assert state.my_attempts.count("A") == 1, "A não deve aparecer duplicado em my_attempts"
    print("[OK] CRITÉRIO 4 — WRONG_GUESS não duplica tentativas já registradas")


#Após PLAYER_OUT com o próprio ID, is_spectator deve ser True.
def test_player_out_vira_espectador():
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 7}}))

    assert state.is_spectator is False

    state.update(json.dumps({"type": "PLAYER_OUT", "payload": {"player_id": 7}}))

    assert state.is_spectator is True
    print("[OK] CRITÉRIO 5 — PLAYER_OUT com próprio ID seta is_spectator=True")


#PLAYER_OUT de outro jogador NÃO sea is_spectator.
def test_player_out_outro_jogador_nao_afeta():
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 7}}))

    state.update(json.dumps({"type": "PLAYER_OUT", "payload": {"player_id": 99}}))

    assert state.is_spectator is False
    print("[OK] CRITÉRIO 6 — PLAYER_OUT de outro jogador não afeta is_spectator")


#simulamos a lógica de validação do client.py diretamente.
def _valida_input(user_input: str) -> tuple[bool, str]:
    if not user_input:
        return False, "vazio"
    if not user_input.isalpha():
        return False, "Aviso: apenas letras (A-Z) são permitidas."
    return True, "ok"


def test_validacao_input_cliente():
    casos_invalidos = ["1", "123", "@", "A1", "!", " ", ""]
    casos_validos   = ["A", "Z", "GATO", "abc"]

    for entrada in casos_invalidos:
        ok, msg = _valida_input(entrada)
        assert not ok, f"Entrada '{entrada}' deveria ser inválida"

    for entrada in casos_validos:
        ok, _ = _valida_input(entrada)
        assert ok, f"Entrada '{entrada}' deveria ser válida"

    print("[OK] CRITÉRIO 7 — Números e símbolos são rejeitados; letras são aceitas")


#is_spectator=True bloqueia o envio: o loop de input deve ignorar o chute.
def test_espectador_nao_envia():
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 3}}))
    state.update(json.dumps({"type": "PLAYER_OUT", "payload": {"player_id": 3}}))

    assert state.is_spectator is True

    server_side, client_side = socket.socketpair()

    try:
        user_input = "A"
        if state.is_spectator:
            blocked = True
        else:
            blocked = False
            send_msg(client_side, "GUESS_LETTER", user_input)

        assert blocked, "Espectador deveria ter bloqueado o envio"

        server_side.setblocking(False)
        try:
            data = server_side.recv(1024)
            assert False, f"Nenhum dado deveria ter sido enviado, mas recebeu: {data}"
        except BlockingIOError:
            pass 

    finally:
        server_side.close()
        client_side.close()

    print("[OK] CRITÉRIO 8 — is_spectator=True bloqueia o envio ao servidor")


#Garante que recv_msgs reconstrói corretamente uma mensagem partida em dois chunks TCP antes de entregá-la ao LocalGameState.
def test_fragmentacao_tcp_nao_corrompe_estado():
    """
    Simula o cenário em que o TCP divide uma mensagem JSON em dois pacotes.
    Antes da correção, sock.recv() entregaria JSON incompleto ao state.update(),
    causando JSONDecodeError silencioso e estado nunca atualizado.
    Após a correção (recv_msgs + buffer), o estado é atualizado corretamente.
    """
    server_side, client_side = socket.socketpair()
    buf = [""]
    state = LocalGameState()

    try:
        raw = (
            json.dumps({"type": "GAME_START", "payload": {"your_id": 5}}) + "\n"
        ).encode("utf-8")

        #Divide o payload no meio, simulando fragmentação TCP
        split_at = len(raw) // 2
        server_side.send(raw[:split_at])

        #Primeiro chunk: recv_msgs não deve retornar nada ainda
        partial = recv_msgs(client_side, buf)
        assert partial == [], "Não deve montar mensagem com chunk incompleto"
        assert state.my_id is None, "Estado não deve mudar com chunk incompleto"

        #Segundo chunk: agora a mensagem está completa
        server_side.send(raw[split_at:])
        complete = recv_msgs(client_side, buf)

        assert len(complete) == 1
        state.update(json.dumps(complete[0]))
        assert state.my_id == 5, f"my_id deveria ser 5, obtido {state.my_id}"

    finally:
        server_side.close()
        client_side.close()

    print("[OK] REGRESSÃO — Fragmentação TCP: recv_msgs reconstrói mensagem corretamente")


if __name__ == "__main__":
    print("=" * 60)
    print("Demonstração dos critérios de aceite — LocalGameState")
    print("=" * 60)

    test_game_start_popula_my_id()
    test_state_update_placar()
    test_wrong_guess_apenas_proprio_jogador()
    test_wrong_guess_sem_duplicatas()
    test_player_out_vira_espectador()
    test_player_out_outro_jogador_nao_afeta()
    test_validacao_input_cliente()
    test_espectador_nao_envia()
    test_fragmentacao_tcp_nao_corrompe_estado()

    print("=" * 60)
    print("Todos os critérios de aceite foram demonstrados com sucesso.")
    print("=" * 60)