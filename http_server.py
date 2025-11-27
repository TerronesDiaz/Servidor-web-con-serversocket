import socketserver
import threading
import os
import time
import sys
import json
import platform
from pathlib import Path
from multiprocessing import Value, Lock

HOST = "0.0.0.0"
PORT = 8080
BUFFER_SIZE = 4096
PUBLIC_DIR = "public"

# Detectar sistema operativo
IS_UNIX_LIKE = platform.system() in ['Linux', 'Darwin', 'FreeBSD', 'OpenBSD']

# Métricas compartidas entre procesos
request_count = Value('i', 0)
total_response_time = Value('d', 0.0)
lock = Lock()

# Modo del servidor (se configura via argumentos)
SERVER_MODE = "threading"  # threading o forking


class HTTPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        start_time = time.time()

        try:
            data_bytes = self.request.recv(BUFFER_SIZE)
            if not data_bytes:
                return

            request = data_bytes.decode("utf-8")
            lines = request.split("\r\n")
            request_line = lines[0].split()

            if len(request_line) < 3:
                self.send_response(400, "Bad Request")
                return

            method, path, _ = request_line

            if method != "GET":
                self.send_response(405, "Method Not Allowed")
                return

            self.handle_get(path)

        except Exception as e:
            print(f"[Error] {e}")
            self.send_response(500, "Internal Server Error")

        finally:
            elapsed = time.time() - start_time
            self.update_metrics(elapsed)

    def handle_get(self, path):
        # Endpoint especial para métricas (API)
        if path == "/api/metrics":
            self.send_metrics_json()
            return

        # Endpoint para resetear métricas
        if path == "/api/reset":
            self.reset_metrics()
            return

        # Endpoint para info del servidor
        if path == "/api/info":
            self.send_server_info()
            return

        if path == "/":
            path = "/index.html"

        file_path = Path(PUBLIC_DIR + path)

        if not file_path.exists() or not file_path.is_file():
            self.send_response(404, "Not Found")
            return

        try:
            content_type = self.get_content_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()

            response = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(content)}\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            self.request.sendall(response.encode("utf-8") + content)

        except Exception as e:
            print(f"Error reading file: {e}")
            self.send_response(500, "Internal Server Error")

    def send_metrics_json(self):
        """Envía métricas como JSON"""
        with lock:
            avg_time = total_response_time.value / request_count.value if request_count.value > 0 else 0
            metrics = {
                "mode": SERVER_MODE,
                "port": PORT,
                "requests": request_count.value,
                "avg_time": round(avg_time, 4),
                "total_time": round(total_response_time.value, 4)
            }

        content = json.dumps(metrics)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(content)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{content}"
        )
        self.request.sendall(response.encode("utf-8"))

    def reset_metrics(self):
        """Resetea las métricas"""
        with lock:
            request_count.value = 0
            total_response_time.value = 0.0

        content = json.dumps({"status": "ok", "message": "Metrics reset"})
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(content)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{content}"
        )
        self.request.sendall(response.encode("utf-8"))

    def send_server_info(self):
        """Envía información del servidor"""
        info = {
            "mode": SERVER_MODE,
            "port": PORT,
            "host": HOST,
            "platform": platform.system(),
            "forking_available": IS_UNIX_LIKE
        }
        content = json.dumps(info)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(content)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{content}"
        )
        self.request.sendall(response.encode("utf-8"))

    def send_response(self, code, message):
        response = (
            f"HTTP/1.1 {code} {message}\r\n"
            "Content-Type: text/html\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"<html><body><h1>{code} {message}</h1></body></html>"
        )
        self.request.sendall(response.encode("utf-8"))

    def get_content_type(self, file_path):
        ext = file_path.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".txt": "text/plain; charset=utf-8",
            ".mp4": "video/mp4",
            ".pdf": "application/pdf",
        }
        return types.get(ext, "application/octet-stream")

    def update_metrics(self, elapsed):
        with lock:
            request_count.value += 1
            total_response_time.value += elapsed


def print_metrics():
    """Imprime métricas de rendimiento"""
    with lock:
        if request_count.value > 0:
            avg_time = total_response_time.value / request_count.value
            print(f"\n{'='*40}")
            print(f"MÉTRICAS DE RENDIMIENTO - {SERVER_MODE.upper()}")
            print(f"{'='*40}")
            print(f"Total de requests: {request_count.value}")
            print(f"Tiempo promedio: {avg_time:.4f}s")
            print(f"Tiempo total: {total_response_time.value:.4f}s")
            print(f"{'='*40}\n")


# Threading version
class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


# Forking version (Unix only)
FORKING_AVAILABLE = False
ForkingHTTPServer = None

if IS_UNIX_LIKE:
    try:
        class ForkingHTTPServer(socketserver.ForkingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
        FORKING_AVAILABLE = True
    except AttributeError:
        FORKING_AVAILABLE = False
        ForkingHTTPServer = None


def run_server(port, mode):
    """Ejecuta el servidor en el puerto y modo especificado"""
    global PORT, SERVER_MODE

    PORT = port
    SERVER_MODE = mode

    # Resetear métricas
    with lock:
        request_count.value = 0
        total_response_time.value = 0.0

    if mode == "threading":
        server = ThreadedHTTPServer((HOST, port), HTTPRequestHandler)
    elif mode == "forking" and FORKING_AVAILABLE:
        server = ForkingHTTPServer((HOST, port), HTTPRequestHandler)
    else:
        print(f"Modo {mode} no disponible, usando threading")
        server = ThreadedHTTPServer((HOST, port), HTTPRequestHandler)
        SERVER_MODE = "threading"

    print(f"Servidor {SERVER_MODE} iniciado en puerto {port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nDeteniendo servidor {SERVER_MODE}...")
        print_metrics()
    finally:
        server.shutdown()
        server.server_close()


def show_menu():
    """Muestra el menú interactivo"""
    print("\n" + "="*50)
    print("  SERVIDOR HTTP CON SOCKETSERVER")
    print("="*50)
    print("\nSeleccione una opción:")
    print("  [1] Threading (Multihilo) - Puerto 8080")
    if IS_UNIX_LIKE:
        print("  [2] Forking (Multiproceso) - Puerto 8080")
    else:
        print("  [2] Forking (No disponible en Windows)")
    print("  [3] Benchmark (Ambos servidores)")
    print("  [4] Salir")
    print("="*50)


def get_menu_choice():
    """Obtiene la elección del usuario"""
    while True:
        choice = input("\nIngrese su opción (1-4): ").strip()
        if choice in ["1", "2", "3", "4"]:
            return choice
        print("Opción inválida. Intente de nuevo.")


def start_benchmark_mode():
    """Inicia el modo benchmark con ambos servidores"""
    import subprocess

    print("\nIniciando modo benchmark...")
    print("Threading: http://localhost:8080")
    if IS_UNIX_LIKE:
        print("Forking:   http://localhost:8081")
    print("\nPresiona Ctrl+C para detener")

    processes = []

    # Servidor Threading
    threading_proc = subprocess.Popen(
        [sys.executable, __file__, "8080", "threading"],
        cwd=os.getcwd()
    )
    processes.append(threading_proc)

    # Servidor Forking (solo Unix)
    if IS_UNIX_LIKE:
        time.sleep(0.5)
        forking_proc = subprocess.Popen(
            [sys.executable, __file__, "8081", "forking"],
            cwd=os.getcwd()
        )
        processes.append(forking_proc)

    print("\nServidores iniciados. Abre http://localhost:8080 en tu navegador.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nDeteniendo servidores...")
        for proc in processes:
            proc.terminate()
            proc.wait()
        print("Servidores detenidos.")


if __name__ == "__main__":
    # Modo automático: python http_server.py <puerto> <modo>
    if len(sys.argv) >= 3:
        port = int(sys.argv[1])
        mode = sys.argv[2].lower()
        run_server(port, mode)
    elif len(sys.argv) == 2:
        port = int(sys.argv[1])
        run_server(port, "threading")
    else:
        # Modo interactivo con menú
        if not IS_UNIX_LIKE:
            print("\nNota: ForkingMixIn no está disponible en Windows.")

        while True:
            show_menu()
            choice = get_menu_choice()

            if choice == "1":
                run_server(8080, "threading")
            elif choice == "2":
                if IS_UNIX_LIKE:
                    run_server(8080, "forking")
                else:
                    print("\nForkingMixIn no está disponible en Windows.")
                    print("Usa WSL o un sistema Unix-like para esta opción.")
            elif choice == "3":
                start_benchmark_mode()
            elif choice == "4":
                print("\nSaliendo...")
                break
