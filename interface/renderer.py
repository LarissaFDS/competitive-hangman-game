"""Carregamento da ASCII Art da forca por estagio."""

from __future__ import annotations

from pathlib import Path


def load_gallows(path: str | Path) -> list[str]:
    """Le forca.txt e retorna os 7 estagios separados por '---'."""
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    stages = [stage.strip() for stage in content.split("\n---\n")]
    return [stage for stage in stages if stage]
