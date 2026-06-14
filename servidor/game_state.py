from __future__ import annotations

import socket
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from utils.protocol import send_msg


WAITING = "WAITING"
PLAYING = "PLAYING"
ENDED = "ENDED"
DEFAULT_ATTEMPTS = 6


@dataclass
class PlayerData:
    player_id: int
    name: str
    attempts: int = DEFAULT_ATTEMPTS
    score: int = 0
    is_spectator: bool = False
    correct_unique_letters: set[str] = field(default_factory=set)


class GameState:
    def __init__(self, word: str = "", category: str = "") -> None:
        self.phase = WAITING
        self.word = self._normalize_word(word)
        self.category = category
        self.revealed = ["_" if char.isalpha() else char for char in self.word]
        self.guessed_letters: set[str] = set()
        self.players: dict[int, PlayerData] = {}
        self.sockets: dict[int, socket.socket] = {}
        self.lock = threading.Lock()

    def add_player(
        self,
        player_id: int,
        name: str,
        sock: socket.socket | None = None,
    ) -> PlayerData:
        with self.lock:
            player = self.players.get(player_id)
            if player is None:
                player = PlayerData(player_id=player_id, name=name)
                self.players[player_id] = player

            if sock is not None:
                self.sockets[player_id] = sock

            return player

    def remove_player(self, player_id: int) -> dict[str, Any] | None:
        with self.lock:
            self.sockets.pop(player_id, None)
            player = self.players.get(player_id)
            if player is not None:
                player.is_spectator = True

            if self.phase != PLAYING:
                return None

            active = [p for p in self.players.values() if not p.is_spectator]
            if len(active) == 1:
                winner = active[0]
                self.phase = ENDED
                return {
                    "trigger_game_over": True,
                    "winner_id": winner.player_id,
                    "winner_name": winner.name,
                }

            return None

    def start_game(self, word: str, category: str) -> None:
        with self.lock:
            self.phase = PLAYING
            self.word = self._normalize_word(word)
            self.category = category
            self.revealed = ["_" if char.isalpha() else char for char in self.word]
            self.guessed_letters = set()
            for player in self.players.values():
                player.attempts = DEFAULT_ATTEMPTS
                player.score = 0
                player.is_spectator = False
                player.correct_unique_letters = set()

    def reset(self) -> None:
        with self.lock:
            self.phase = WAITING
            self.word = ""
            self.category = ""
            self.revealed = []
            self.guessed_letters = set()
            self.players = {}

    def process_guess(self, player_id: int, letter: str) -> dict[str, Any]:
        with self.lock:
            player = self.players.get(player_id)
            if player is None:
                return self._result(valid=False)
            if player.is_spectator:
                return self._result(valid=False, eliminated=True)

            normalized_letter = self._normalize_letter(letter)
            if normalized_letter is None:
                return self._result(valid=False)

            if normalized_letter in self.guessed_letters:
                return self._result(valid=False)

            self.guessed_letters.add(normalized_letter)
            positions = [
                index
                for index, char in enumerate(self.word)
                if char == normalized_letter
            ]
            correct = bool(positions)

            if correct:
                for index in positions:
                    self.revealed[index] = normalized_letter
                player.score += len(positions)
                player.correct_unique_letters.add(normalized_letter)
            else:
                self._decrement_attempt(player)

            return self._result(
                valid=True,
                correct=correct,
                won=self._is_won(),
                eliminated=player.is_spectator,
                positions=positions,
            )

    def process_word_guess(self, player_id: int, word: str) -> dict[str, Any]:
        with self.lock:
            player = self.players.get(player_id)
            if player is None:
                return self._result(valid=False)
            if player.is_spectator:
                return self._result(valid=False, eliminated=True)

            normalized_word = self._normalize_word_guess(word)
            if normalized_word is None:
                return self._result(valid=False)

            correct = normalized_word == self.word
            positions: list[int] = []
            if correct:
                self.revealed = list(self.word)
                player.score += len({char for char in self.word if char.isalpha()})
                player.correct_unique_letters.update(
                    char for char in self.word if char.isalpha()
                )
                positions = [
                    index
                    for index, char in enumerate(self.word)
                    if char.isalpha()
                ]
            else:
                self._decrement_attempt(player)

            return self._result(
                valid=True,
                correct=correct,
                won=self._is_won(),
                eliminated=player.is_spectator,
                positions=positions,
            )

    def broadcast(self, msg_type: str, data: Any) -> None:
        with self.lock:
            sockets_snapshot = list(self.sockets.items())
            snapshot_by_player = dict(sockets_snapshot)

        failed_player_ids: list[int] = []
        for player_id, sock in sockets_snapshot:
            try:
                send_msg(sock, msg_type, data)
            except OSError:
                failed_player_ids.append(player_id)

        if failed_player_ids:
            with self.lock:
                for player_id in failed_player_ids:
                    if self.sockets.get(player_id) is snapshot_by_player.get(player_id):
                        self.sockets.pop(player_id, None)

    def get_state_payload(self) -> dict[str, Any]:
        with self.lock:
            return {
                "phase": self.phase,
                "revealed": " ".join(self.revealed),
                "all_players": [
                    {
                        "id": p.player_id,
                        "name": p.name,
                        "attempts_left": p.attempts,
                        "score": p.score,
                        "active": not p.is_spectator,
                    }
                    for p in self.players.values()
                ],
            }

    def get_final_scores(self) -> list[dict[str, Any]]:
        with self.lock:
            return sorted(
                [
                    {
                        "id": p.player_id,
                        "name": p.name,
                        "score": p.score,
                        "unique_letters": len(p.correct_unique_letters),
                    }
                    for p in self.players.values()
                ],
                key=lambda x: (x["score"], x["unique_letters"]),
                reverse=True,
            )

    def determine_winner(self) -> dict[str, Any] | None:
        scores = self.get_final_scores()
        if not scores:
            return None
        return scores[0]

    def _decrement_attempt(self, player: PlayerData) -> None:
        player.attempts = max(0, player.attempts - 1)
        if player.attempts == 0:
            player.is_spectator = True

    def _is_won(self) -> bool:
        return bool(self.word) and "".join(self.revealed) == self.word

    def _result(
        self,
        *,
        valid: bool,
        correct: bool = False,
        won: bool = False,
        eliminated: bool = False,
        positions: list[int] | None = None,
    ) -> dict[str, Any]:
        return {
            "valid": valid,
            "correct": correct,
            "won": won,
            "eliminated": eliminated,
            "positions": positions or [],
        }

    def _normalize_letter(self, letter: str) -> str | None:
        if not isinstance(letter, str):
            return None
        normalized = self._remove_accents(letter.strip()).upper()
        if len(normalized) != 1 or not normalized.isalpha():
            return None
        return normalized

    def _normalize_word_guess(self, word: str) -> str | None:
        if not isinstance(word, str):
            return None
        normalized = self._normalize_word(word.strip())
        if not normalized or not normalized.replace(" ", "").isalpha():
            return None
        return normalized

    def _normalize_word(self, word: str) -> str:
        return self._remove_accents(word).upper()

    def _remove_accents(self, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value)
        return "".join(char for char in normalized if unicodedata.category(char) != "Mn")