# Competitive Hangman Game

## 1. Visao geral

Projeto inicial de um jogo competitivo de forca para a disciplina de Redes de Computadores.

Nesta etapa, o repositorio contem apenas a estrutura base e um servidor TCP minimo em Python, usando sockets e threads. As regras completas do jogo ainda nao foram implementadas.

Docker nao sera usado neste momento porque a disciplina exige execucao simples em Python com sockets e threads.

## 2. Pre-requisitos

- Python 3 instalado.
- Terminal ou prompt de comando para executar os scripts.

Nao ha dependencias externas nesta etapa.

## 3. Como rodar o servidor

Na raiz do projeto, execute:

```bash
python servidor/game_server.py
```

O servidor TCP inicia por padrao em `localhost:5000`.

## 4. Como rodar o cliente

O cliente ainda sera implementado em outra task.

Por enquanto, para testar o servidor, pode ser usado um cliente TCP simples ou um pequeno script Python temporario.

## 5. Estrutura de pastas

```text
servidor/   Codigo relacionado ao servidor do jogo.
cliente/    Codigo relacionado ao cliente do jogo.
interface/  Arquivos futuros de interface.
assets/     Recursos estaticos futuros.
utils/      Funcoes utilitarias futuras.
docs/       Documentacao do projeto.
```

## 6. Endereco e porta padrao

- Host: `localhost`
- Porta: `5000`
