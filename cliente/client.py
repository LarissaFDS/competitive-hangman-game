import socket
import threading
import json
import sys

#Configurações camada de transporte e rede
HOST = "localhost" #Interface de loopback (127.0.0.1).
PORT = 5000        #Porta de destino na camada de transporte. 
BUFFER_SIZE = 1024 #Tamanho do buffer de recepção na camada de aplicação (em bytes).

def recv_loop(sock):
    #comportamento full-duplex da aplicação (envia e recebe simultaneamente).
    try:
        while True:
            #sock.recv() é uma chamada bloqueante (blocking I/O). 
            #A thread fica ociosa aqui até que o SO entregue dados vindos da rede.
            data = sock.recv(BUFFER_SIZE)
            
            #se recv() retornar vazio (0 bytes), significa que o servidor enviou um pacote TCP FIN (encerramento gracioso da conexão).
            if not data:
                print("\nConexão encerrada pelo servidor (TCP FIN recebido).")
                break
            
            #decodifica os bytes recebidos da rede (camada física/transporte) de volta para string (camada de aplicação) usando UTF-8.
            print(f"\n[Servidor]: {data.decode('utf-8')}")
            print("> ", end="", flush=True)
            
    except ConnectionResetError:
        #captura o recebimento de um pacote TCP RST (reset). 
        print("\nAviso: o servidor foi desconectado inesperadamente (TCP RST recebido).")
    except Exception as e:
        print(f"\nErro inesperado no cliente: {e}")
    finally:
        print("Encerrando o processo...")
        sys.exit(0)

def main():
    player_name = input("Digite seu nome de jogador: ")
    
    #criação do socket:
    #AF_INET: define a família de endereçamento como IPv4 (camada de rede).
    #SOCK_STREAM: define o uso do protocolo TCP.
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        #onicia o "3-way handshake" do TCP (SYN, SYN-ACK, ACK) com o servidor.
        client_socket.connect((HOST, PORT))
    except ConnectionRefusedError:
        #falha no handshake.
        print("Não foi possível conectar. O servidor está rodando na porta 5000?")
        return

    #construção da PDU (protocol data unit) da camada de aplicação.
    join_msg = {"type": "JOIN", "payload": player_name}
    
    client_socket.sendall(json.dumps(join_msg).encode("utf-8"))
    
    #cria uma thread separada para lidar com a recepção bloqueante do socket
    recv_thread = threading.Thread(target=recv_loop, args=(client_socket,), daemon=True)
    recv_thread.start()

    #Loop principal (thread principal) focado apenas em I/O do usuário e envio (upload)
    try:
        while True:
            user_input = input("> ").strip()
            if not user_input:
                continue
            
            #Regras do protocolo de aplicação para definir o "type" do payload
            if len(user_input) == 1:
                msg = {"type": "GUESS_LETTER", "payload": user_input}
            else:
                msg = {"type": "GUESS_WORD", "payload": user_input}
                
            #Empacota em JSON, converte para bytes e envia pelo túnel TCP estabelecido.
            client_socket.sendall(json.dumps(msg).encode("utf-8"))
            
    except KeyboardInterrupt:
        print("\nSaindo do jogo...")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()