from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from pathlib import Path
import threading
import socket
import struct
import time
import os


PORT = 60000
BUFFER_SIZE = 4096
PROMPT = "> "


class App:
    _username = None
    _app_state = None
    _server_socket = None
    _client_socket = None
    _client_ip = None
    _stop_app = None
    _stop_connection = None
    _session = None
    _read_messages_thread = None
    _server_thread = None


    def __init__(self):
        self._stop_connection = threading.Event()
        self._stop_app = threading.Event()
        self._session = PromptSession()
    

    def start(self):
        try:
            self._set_state("DISCONNECTED")
            
            while not self._stop_app.is_set():
                self._handle_user_input()

        except KeyboardInterrupt:
            self.stop()
        finally:
            self._stop_connection.set()
            self._stop_app.set()
            if self._client_socket:
                self._client_socket.shutdown(socket.SHUT_WR)
                self._client_socket.close()
                self._client_socket = None
        

    def stop(self):
        self._stop_connection.set()
        self._stop_app.set()
        if self._client_socket:
            self._client_socket.shutdown(socket.SHUT_WR)
            self._client_socket.close()
            self._client_socket = None
        if self._server_socket:
            self._server_socket.shutdown(socket.SHUT_WR)
            self._server_socket.close()
            self._server_socket = None
        print("Saliendo...")
        time.sleep(0.2)


    def _handle_user_input(self):
        user_input = self._session.prompt(PROMPT)

        match self._app_state:
            case "DISCONNECTED":
                if (user_input.lower() == 'exit'):
                    self.stop()
                    return
                
                with patch_stdout():
                    print("No está conectado un cliente, espere o utilice 'exit' para salir")
                                        
            case "CONNECTED":
                if (user_input.lower() == 'exit'):
                    with patch_stdout():
                        print("No se puede salir mientras esté conectado un cliente")
                    return

                self._process_path(user_input)


    def _set_state(self, new_state):
        self._app_state = new_state
        
        match new_state:
            case "DISCONNECTED":
                self._stop_connection.set()
                self._client_ip = None
                if self._client_socket:
                    self._client_socket.shutdown(socket.SHUT_WR)
                    self._client_socket.close()
                    self._client_socket = None
                
                self._server_thread = threading.Thread(target=self._wait_for_connections, daemon=True)
                self._server_thread.start()

            case "CONNECTED":
                self._stop_connection.clear()

    
    def _wait_for_connections(self):
        with patch_stdout():
            print("Esperando conexión del cliente...")

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(('0.0.0.0', PORT))
            self._server_socket.listen(1)

            self._client_socket, (self._client_ip, _) = self._server_socket.accept()
            self._client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if self._server_socket:
                self._server_socket.shutdown(socket.SHUT_WR)
                self._server_socket.close()
                self._server_socket = None
        except Exception as e:
            print(e)
        
        with patch_stdout():
            print(f"{self._client_ip} se conectó al servidor")
        
        self._set_state("CONNECTED")
    
    
    def _read_messages(self):
        while not self._stop_connection.is_set():
            try:
                data = self._client_socket.recv(BUFFER_SIZE)
            except Exception as e:
                self._handle_disconnect()
                return

            if data == b'':
                self._handle_disconnect()
                return

            parsedData = data.decode().split(":")
            user = parsedData[0]
            msg = ":".join(parsedData[1:])
            
            if data == '' or user == '' or msg == '':
                continue

            with patch_stdout():
                print(f"{user} ({self._client_ip}) dice: {msg}")
    

    def _handle_disconnect(self):
        if not self._stop_connection.is_set():
            with patch_stdout():
                print(f"SE PERDIÓ LA CONEXIÓN A '{self._client_ip.upper()}'")
            self._set_state("DISCONNECTED")
            return


    def _get_username(self):
        username = None
        while True:
            username = self._session.prompt("Ingrese su nombre de usuario: ")
            if not username:
                print("El nombre de usuario no puede estar vacío")
            elif ":" in username:
                print("El nombre de usuario no puede contener dos puntos ':'")
            else:
                break
        return username


    def _process_path(self, path):
        file_path = Path(path).expanduser().resolve(strict=False)

        with patch_stdout():
            if file_path.is_file():
                self._send_file(file_path)
            else:
                print(f"Error: No se encontró un archivo en '{file_path}'")
    

    def _send_file(self, file_path):
        try:
            file_name = file_path.name

            if len(file_name) < 256:
                file_name += ':'
                file_name += ' ' * (256 - len(file_name))

            self._client_socket.sendall(file_name.encode())

            size_in_bytes = os.path.getsize(file_path)
            self._client_socket.sendall(struct.pack('<I', size_in_bytes))

            bytes_sent = 0
            print(f"Enviando archivo {file_name} ({size_in_bytes} bytes) a {self._client_ip}: {int(bytes_sent / size_in_bytes * 100)}%", end='')
            with open(file_path, 'rb') as f:
                while chunk := f.read(BUFFER_SIZE):
                    self._client_socket.sendall(chunk)
                    print(f"\rEnviando archivo {file_name} ({size_in_bytes} bytes) a {self._client_ip}: {int(bytes_sent / size_in_bytes * 100)}%", end='')
            
            print("\nTransferencia completada")

        except KeyboardInterrupt:
            print("Transferencia cancelada")
        except Exception as e:
            print("Ocurrió un error: ", e)


if __name__ == "__main__":
    app = App()
    app.start()
