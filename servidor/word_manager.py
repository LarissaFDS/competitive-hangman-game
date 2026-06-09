"""Carregamento e sorteio de palavras do banco estatico do jogo."""

from __future__ import annotations

import random
from pathlib import Path


def load_words(path: str | Path) -> list[tuple[str, str]]:
    """Le palavras.txt e retorna lista de tuplas (palavra, categoria)."""
    words: list[tuple[str, str]] = []
    file_path = Path(path)

    with file_path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            word, category = line.split(",", maxsplit=1)
            words.append((word.strip(), category.strip()))

    return words


def pick_word(words: list[tuple[str, str]]) -> tuple[str, str]:
    """Sorteia uma palavra aleatoriamente do banco."""
    return random.choice(words)
