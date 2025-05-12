from prompt_toolkit import PromptSession, application
from prompt_toolkit.patch_stdout import patch_stdout
import threading
import socket
import time


PORT = 60000
BUFFER_SIZE = 4096
PROMPT = "> "


class App:
    _app_state = None
    _client_socket = None
    _host = None
    _stop_app = None
    _stop_connection = None
    _session = None
    _read_messages_thread = None
    _prompt = {"prompt": ""}


    def __init__(self):
        self._app_state = "DISCONNECTED"
        self._stop_connection = threading.Event()
        self._stop_app = threading.Event()
        self._session = PromptSession()
    

    def start(self):
        try:
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
        

    def _shutdown_app(self):
        self._stop_connection.set()
        self._stop_app.set()
        
        try:
            self._client_socket.shutdown(socket.SHUT_WR)
            self._client_socket.close()
        except Exception:
            pass

        self._client_socket = None
    
    
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
                
                if self._connect_to_host(user_input):
                    self._set_state("CONNECTED")
                                        
            case "CONNECTED":
                if (user_input.lower() == 'exit'):
                    self._set_state("DISCONNECTED")
                    return

                with patch_stdout():
                    print("Utilice 'exit' para desconectarse del servidor")
                

    def _set_state(self, new_state):
        self._app_state = new_state
        
        match new_state:
            case "DISCONNECTED":
                self._stop_connection.set()
                self._host = None
                try:
                    self._client_socket.shutdown(socket.SHUT_WR)
                    self._client_socket.close()
                    self._client_socket = None
                except Exception:
                    pass

            case "CONNECTED":
                self._stop_connection.clear()
                self._read_messages_thread = threading.Thread(target=self._receive_data, daemon=True)
                self._read_messages_thread.start()
        
        app = application.current.get_app()
        app.invalidate() # forzar la actualización del prompt

    
    def _connect_to_host(self, host):
        try:
            if self._client_socket:
                self._client_socket.shutdown(socket.SHUT_WR)
                self._client_socket.close()
                self._client_socket = None
        except Exception:
            pass
        
        try:
            self._client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._client_socket.connect((host, PORT))
        
        except Exception as e:
            print(f"No se pudo conectar al host {host}:{PORT}. Error: ", e)
            return False
        
        self._host = host
        print(f"Conectado al host {host}:{PORT}")

        return True


    def _get_prompt(self):
        match self._app_state:
            case "DISCONNECTED":
                self._prompt["prompt"] = "Ingrese un host al cual conectarse (o exit para salir): "
            case "CONNECTED":
                self._prompt["prompt"] = PROMPT
        
        return self._prompt["prompt"]
    
    
    def _receive_data(self):
        while not self._stop_connection.is_set():
            try:
                FILE_NAME_MAX_LENGTH = 255
                
                data = self._client_socket.recv(FILE_NAME_MAX_LENGTH)
                file_name = data.decode().split(':')[0]

                if data == b'':
                    self._handle_disconnect()

                data = self._client_socket.recv(4)
                size_in_bytes = int.from_bytes(data, byteorder="little")

                if data == b'':
                    self._handle_disconnect()

                self._receive_file(file_name, size_in_bytes)

            except Exception as e:
                self._handle_disconnect()
                return


    def _receive_file(self, file_name, file_size):
        try:
            with open(file_name, 'wb') as f:
                remaining = file_size
                progress = 0
                while remaining > 0:
                    chunk = self._client_socket.recv(BUFFER_SIZE)
                    remaining -= len(chunk)
                    progress = 1 - remaining / file_size
                    if chunk:
                        f.write(chunk)
                    print(f"\rRecibiendo archivo '{file_name}' ({file_size} bytes) de '{self._host}': {int(progress * 100)}%", end='')
            
                with patch_stdout():
                    print("\nTransferencia completada")
        
        except KeyboardInterrupt:
            print("\nTransferencia cancelada")
        except Exception as e:
            print("\nOcurrió un error:", e)

    
    def _handle_disconnect(self):
        if not self._stop_connection.is_set():
            with patch_stdout():
                print(f"SE PERDIÓ LA CONEXIÓN A '{self._host.upper()}'")
            self._set_state("DISCONNECTED")
            return


if __name__ == "__main__":
    app = App()
    app.start()
