import json

class LocalGameState:
    def __init__(self):
        self.my_id = None #Necessário para comparar quem errou ou quem foi eliminado
        self.phase = "WAITING"
        self.revealed = ""
        self.category = ""
        self.my_attempts = []
        self.all_players = [] #Lista de dicionários com nome, tentativas restantes e pontuação
        self.is_spectator = False

    def update(self, msg):
        #Atualiza o estado local do jogo com base na mensagem recebida.
        try:
            #Garante que a mensagem seja um dicionário
            if isinstance(msg, str):
                data = json.loads(msg)
            else:
                data = msg
            
            msg_type = data.get("type")
            payload = data.get("payload", {})

            #Dispatcher: mapeia o tipo de mensagem para o método privado correspondente
            dispatch_map = {
                "GAME_START": self._on_game_start,
                "STATE_UPDATE": self._on_state_update,
                "WRONG_GUESS": self._on_wrong_guess,
                "PLAYER_OUT": self._on_player_out,
            }

            if msg_type in dispatch_map:
                dispatch_map[msg_type](payload)
            else:
                #Ignora silenciosamente ou loga tipos de mensagens não mapeados
                pass
                
        except json.JSONDecodeError:
            print("\nErro ao decodificar a mensagem JSON do servidor.")
        except Exception as e:
            print(f"\nErro ao processar o estado local: {e}")

    #--- Metodos de tratamento de estado ---
    def _on_game_start(self, payload):
        self.my_id = payload.get("your_id", self.my_id)
        self.phase = "PLAYING"
        self.my_attempts = []    
        self.is_spectator = False
        self.category = payload.get("category", self.category)

    def _on_state_update(self, payload):
        self.phase = payload.get("phase", self.phase)
        self.revealed = payload.get("revealed", self.revealed)
        self.all_players = payload.get("all_players", self.all_players)

    def _on_wrong_guess(self, payload):
        #Atualiza my_attempts apenas se o erro foi do próprio jogador
        if payload.get("player_id") == self.my_id:
            guess = payload.get("guess")
            if guess and guess not in self.my_attempts:
                self.my_attempts.append(guess)

    def _on_player_out(self, payload):

        eliminated_id = payload.get("player_id")
        #Define como espectador se o eliminado for o próprio jogador
        if  eliminated_id== self.my_id:
            self.is_spectator = True

        #Permite que o renderer exiba o estado atualizado sem esperar pelo próximo STATE_UPDATE.
        for player in self.all_players:
            if player.get("id") == eliminated_id:
                player["active"] = False
                break