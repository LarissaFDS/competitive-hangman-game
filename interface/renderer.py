from pathlib import Path


def load_gallows(path):
    """Lê o arquivo de texto contendo os estágios do jogo da forca e retorna uma lista de strings, cada uma representando um estágio."""
    content = Path(path).read_text(encoding="utf-8")
    stages = []
    current_stage = []

    for line in content.splitlines():
        if line.strip() == "---":
            stages.append("\n".join(current_stage).strip())
            current_stage = []
        else:
            current_stage.append(line)

    stages.append("\n".join(current_stage).strip())

    if len(stages) != 7:
        raise ValueError("Esperado 7 estágios.")

    return stages

# Teste de carregamento dos estágios da forca

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    gallows_path = project_root / "assets" / "forca.txt"
    gallows = load_gallows(gallows_path)

    print(f"Estágios carregados: {len(gallows)}")
    print(gallows[3])
'''
    for index, stage in enumerate(gallows):
        print(f"\n--- Estágio {index} ---")
        print(stage)
'''
