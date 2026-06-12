import os
from pathlib import Path
import json
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cliente.local_state import LocalGameState

#Carregamento dos estágios da forca
def _load_gallows(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    stages, current = [], []
    for line in content.splitlines():
        if line.strip() == "---":
            stages.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    stages.append("\n".join(current).strip())
    if len(stages) != 7:
        raise ValueError(f"Esperado 7 estágios na forca, encontrado {len(stages)}.")
    return stages

_GALLOWS_PATH = next(
    p for p in [
        Path(__file__).resolve().parent / "forca.txt",
        Path(__file__).resolve().parent.parent / "assets" / "forca.txt",
    ]
    if p.exists()
)
_GALLOWS: list[str] = _load_gallows(_GALLOWS_PATH)

#Utilitários
def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _gallows_stage(wrong_count: int) -> str:
    index = max(0, min(wrong_count, 6))
    return _GALLOWS[index]


def _format_revealed(revealed: str) -> str:
    if " " in revealed:
        return revealed
    return " ".join(revealed)

#Formata o placar lateral com nome, pontuação, tentativas e status
def _render_scoreboard(players: list[dict], my_id) -> str:
    if not players:
        return "  (sem jogadores)"

    lines = []
    for p in players:
        active = p.get("active", True)
        is_me  = p.get("id") == my_id

        status = ""
        if not active:
            status = " [ESPECTADOR]"
        elif is_me:
            status = " ◄ você"

        name     = p.get("name", "?")
        score    = p.get("score", 0)
        attempts = p.get("attempts_left", "?")

        lines.append(f"  {name}{status}")
        lines.append(f"    Pontos: {score}  |  Tentativas: {attempts}")

    return "\n".join(lines)

#Funções públicas de renderização
def render_state(state) -> None:
    clear_screen()

    wrong_count  = len(state.my_attempts)
    gallows_text = _gallows_stage(wrong_count)
    scoreboard   = _render_scoreboard(state.all_players, state.my_id)

    gallows_lines = gallows_text.splitlines()
    board_lines   = ["── PLACAR ──", scoreboard]

    print(gallows_text)
    print()

    print("── PLACAR ──────────────────────────")
    print(scoreboard)
    print("────────────────────────────────────")
    print()

    revealed = _format_revealed(state.revealed) if state.revealed else "?"
    print(f"  Palavra: {revealed}")
    print()

    if state.my_attempts:
        tentativas = "  ".join(state.my_attempts)
        print(f"  Letras erradas: {tentativas}")
    else:
        print("  Letras erradas: (nenhuma ainda)")
    print()

    if state.is_spectator:
        print("  Você é espectador. Acompanhe a partida.")
    else:
        print("  Sua vez — digite uma letra ou a palavra completa:")


def render_waiting(connected: int, needed: int) -> None:
    clear_screen()
    print("╔══════════════════════════════════════╗")
    print("║        JOGO DA FORCA  — Aguarde      ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  Jogadores conectados: {connected}/{needed}            ║")
    print("║  Aguardando os demais jogadores...   ║")
    print("╚══════════════════════════════════════╝")


def render_game_over(winner_name: str, word: str, scores: list[dict]) -> None:
    clear_screen()
    print("╔══════════════════════════════════════╗")
    print("║            FIM DE JOGO               ║")
    print("╠══════════════════════════════════════╣")

    if winner_name:
        print(f"║  Vencedor: {winner_name:<24}║")
    else:
        print("║  Nenhum vencedor desta vez.          ║")

    print(f"║  Palavra: {word:<29}║")
    print("╠══════════════════════════════════════╣")
    print("║  PLACAR FINAL                        ║")

    for p in sorted(scores, key=lambda x: x.get("score", 0), reverse=True):
        name  = p.get("name", "?")[:18]
        score = p.get("score", 0)
        print(f"║    {name:<18} — {score:>4} pts      ║")

    print("╚══════════════════════════════════════╝")


if __name__ == "__main__":

    sys.path.insert(0, str(Path(__file__).resolve().parent))
 
    def pausa(msg=""):
        input(f"\n  [{msg}] — pressione Enter para continuar...")
 
    render_waiting(connected=1, needed=3)
    pausa("sala de espera com 1/3 jogadores")
 
    render_waiting(connected=2, needed=3)
    pausa("sala de espera com 2/3 jogadores")
 
    state = LocalGameState()
    state.update(json.dumps({"type": "GAME_START", "payload": {"your_id": 1}}))
    state.update(json.dumps({
        "type": "STATE_UPDATE",
        "payload": {
            "phase": "PLAYING",
            "revealed": "_ _ _ _ _ _ _ _",
            "all_players": [
                {"id": 1, "name": "Você",  "attempts_left": 6, "score": 0,  "active": True},
                {"id": 2, "name": "Bruno", "attempts_left": 6, "score": 0,  "active": True},
                {"id": 3, "name": "Carla", "attempts_left": 6, "score": 0,  "active": True},
            ]
        }
    }))
    render_state(state)
    pausa("início — nenhum erro ainda (estágio 0)")
 
    for letra in ["Z", "X"]:
        state.update(json.dumps({"type": "WRONG_GUESS", "payload": {"player_id": 1, "guess": letra}}))
    render_state(state)
    pausa("2 erros (estágio 2)")
 
    state.update(json.dumps({
        "type": "STATE_UPDATE",
        "payload": {
            "phase": "PLAYING",
            "revealed": "C A _ _ O R R _",
            "all_players": [
                {"id": 1, "name": "Você",  "attempts_left": 4, "score": 10, "active": True},
                {"id": 2, "name": "Bruno", "attempts_left": 6, "score": 0,  "active": True},
                {"id": 3, "name": "Carla", "attempts_left": 6, "score": 0,  "active": True},
            ]
        }
    }))
    render_state(state)
    pausa("acertou algumas letras — pontuação atualizada")
 
    state.update(json.dumps({"type": "PLAYER_OUT", "payload": {"player_id": 3}}))
    render_state(state)
    pausa("Carla desconectou — aparece como [ESPECTADOR] no placar")
 
    state.update(json.dumps({"type": "PLAYER_OUT", "payload": {"player_id": 1}}))
    render_state(state)
    pausa("você foi eliminado — tela mostra modo espectador")
 
    render_game_over(
        winner_name="Bruno",
        word="CACHORRO",
        scores=[
            {"name": "Bruno", "score": 40},
            {"name": "Você",  "score": 10},
            {"name": "Carla", "score": 0},
        ]
    )
    print("\n  Fim da demonstração.")