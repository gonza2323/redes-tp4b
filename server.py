from prompt_toolkit import PromptSession, application
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
    _app_state = None
    _server_socket = None
    _client_socket = None
    _client_ip = None
    _stop_app = None
    _stop_connection = None
    _session = None
    _server_thread = None
    _prompt = {"prompt": ""}


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
        except Exception as e:
            print("Ocurrió un error:", e)
            self._shutdown_app()
        

    def _shutdown_app(self):
        self._stop_connection.set()
        self._stop_app.set()

        try:
            self._client_socket.shutdown(socket.SHUT_WR)
            self._client_socket.close()
        except Exception:
            pass
        
        try:
            self._server_socket.shutdown(socket.SHUT_WR)
            self._server_socket.close()
        except Exception:
            pass

        self._client_socket = None
        self._server_socket = None
    
    
    def stop(self):
        self._shutdown_app()
        print("Saliendo...")
        time.sleep(0.2)


    def _handle_user_input(self):
        user_input = self._session.prompt(self._get_prompt)

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
                try:
                    self._client_socket.shutdown(socket.SHUT_WR)
                    self._client_socket.close()
                except Exception:
                    pass
                self._client_socket = None
                
                self._server_thread = threading.Thread(target=self._wait_for_connections, daemon=True)
                self._server_thread.start()

            case "CONNECTED":
                self._stop_connection.clear()
                self._read_messages_thread = threading.Thread(target=self._receive_data, daemon=True)
                self._read_messages_thread.start()
        
        app = application.current.get_app()
        app.invalidate() # forzar la actualización del prompt

    
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
    

    def _get_prompt(self):
        match self._app_state:
            case "DISCONNECTED":
                self._prompt["prompt"] = PROMPT
            case "CONNECTED":
                self._prompt["prompt"] = "Qué archivo desea enviar al cliente?: "
        
        return self._prompt["prompt"]
    
    
    def _receive_data(self):
        while not self._stop_connection.is_set():
            try:
                data = self._client_socket.recv(BUFFER_SIZE)
            except Exception as e:
                self._handle_disconnect()
                return

            if data == b'':
                self._handle_disconnect()
                return
    
    
    def _handle_disconnect(self):
        if not self._stop_connection.is_set():
            with patch_stdout():
                print(f"SE PERDIÓ LA CONEXIÓN A '{self._client_ip.upper()}'")
            self._set_state("DISCONNECTED")
            return


    def _process_path(self, path):
        file_path = Path(path).expanduser().resolve(strict=False)

        if file_path.is_file():
            self._send_file(file_path)
        else:
            with patch_stdout():
                print(f"Error: No se encontró un archivo en '{file_path}'")
    

    def _send_file(self, file_path):
        try:
            FILE_NAME_MAX_LENGTH = 255
            file_name = file_path.name
            file_name_to_send = file_name

            if len(file_name) > FILE_NAME_MAX_LENGTH:
                raise Exception("El nombre del archivo es muy largo")

            if len(file_name) < FILE_NAME_MAX_LENGTH:
                file_name_to_send += ':'
                file_name_to_send += ' ' * (FILE_NAME_MAX_LENGTH - len(file_name_to_send))

            self._client_socket.sendall(file_name_to_send.encode())

            size_in_bytes = os.path.getsize(file_path)
            self._client_socket.sendall(struct.pack('<I', size_in_bytes))

            bytes_sent = 0
            progress = 0
            with open(file_path, 'rb') as f:
                while chunk := f.read(BUFFER_SIZE):
                    self._client_socket.sendall(chunk)
                    bytes_sent += len(chunk)
                    progress = bytes_sent / size_in_bytes
                    print(f"\rEnviando archivo {file_name} ({size_in_bytes} bytes) a '{self._client_ip}': {int(progress * 100)}%", end='')
            
            with patch_stdout():
                print("\nTransferencia completada")

        except KeyboardInterrupt:
            print("\nTransferencia cancelada")
        except Exception as e:
            print("\nOcurrió un error:", e)


if __name__ == "__main__":
    app = App()
    app.start()
