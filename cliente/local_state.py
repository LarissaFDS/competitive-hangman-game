import json

class LocalGameState:
    def __init__(self):
        self.phase = "WAITING"
        self.revealed = ""
        self.my_attempts = []
        self.scores = {}

    def update(self, msg):
        #atualiza o estado local do jogo com base no dicionário ou JSON recebido.
        try:
            #grante que a mensagem seja um dicionário, fazendo o parse caso chegue como string
            if isinstance(msg, str):
                data = json.loads(msg)
            else:
                data = msg
            
            msg_type = data.get("type")
            payload = data.get("payload", {})

            #atualiza os dados apenas se a mensagem for um update de estado
            if msg_type == "STATE_UPDATE":
                self.phase = payload.get("phase", self.phase)
                self.revealed = payload.get("revealed", self.revealed)
                self.my_attempts = payload.get("my_attempts", self.my_attempts)
                self.scores = payload.get("scores", self.scores)
                
        except json.JSONDecodeError:
            print("Erro ao decodificar a mensagem de atualização de estado.")
        except Exception as e:
            print(f"Erro ao processar o estado local: {e}")