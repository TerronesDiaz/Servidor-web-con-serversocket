import socketserver
import threading
import os
import time
import sys
import json
import platform
import io
from pathlib import Path
from multiprocessing import Value, Lock
from datetime import datetime, timezone
from email.utils import formatdate
from urllib.parse import urlparse, parse_qs

# Intentar importar Pillow para procesamiento de imágenes
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Nota: Pillow no instalado. Procesamiento de imágenes deshabilitado.")
    print("Instala con: pip install Pillow")

# Verificar si FFmpeg está disponible para procesamiento de video
import shutil
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
if not FFMPEG_AVAILABLE:
    print("Nota: FFmpeg no encontrado. Procesamiento de video deshabilitado.")
    print("Instala FFmpeg para habilitar extracción de thumbnails de video.")

HOST = "0.0.0.0"
PORT = 8080
BUFFER_SIZE = 4096
PUBLIC_DIR = "public"
SERVER_NAME = "PythonHTTPServer/1.0"

# Detectar sistema operativo
IS_UNIX_LIKE = platform.system() in ['Linux', 'Darwin', 'FreeBSD', 'OpenBSD']

# Métricas compartidas entre procesos
request_count = Value('i', 0)
total_response_time = Value('d', 0.0)
lock = Lock()

# Modo del servidor (se configura via argumentos)
SERVER_MODE = "threading"  # threading o forking


class HTTPRequestHandler(socketserver.BaseRequestHandler):
    """
    Handler HTTP/1.1 que implementa GET y HEAD según RFC 9110
    https://www.rfc-editor.org/rfc/rfc9110.html
    """
    
    def handle(self):
        start_time = time.time()

        try:
            data_bytes = self.request.recv(BUFFER_SIZE)
            if not data_bytes:
                return

            request = data_bytes.decode("utf-8")
            lines = request.split("\r\n")
            
            # Parsear línea de petición (RFC 9110 Section 3.1)
            request_line = lines[0].split()

            if len(request_line) < 3:
                self.send_error_response(400, "Bad Request")
                return

            method, path, http_version = request_line
            
            # Parsear headers de la petición
            headers = self.parse_headers(lines[1:])
            
            # Log de la petición
            client_ip = self.client_address[0]
            print(f"[{SERVER_MODE}] {client_ip} - {method} {path} {http_version}")

            # Métodos soportados: GET y HEAD (RFC 9110 Section 9.3)
            if method == "GET":
                self.handle_get(path, include_body=True)
            elif method == "HEAD":
                # HEAD es igual a GET pero sin body (RFC 9110 Section 9.3.2)
                self.handle_get(path, include_body=False)
            else:
                self.send_error_response(405, "Method Not Allowed")
                return

        except Exception as e:
            print(f"[Error] {e}")
            self.send_error_response(500, "Internal Server Error")

        finally:
            elapsed = time.time() - start_time
            self.update_metrics(elapsed)
    
    def parse_headers(self, header_lines):
        """Parsea los headers HTTP de la petición"""
        headers = {}
        for line in header_lines:
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        return headers
    
    def get_http_date(self):
        """Retorna la fecha actual en formato HTTP (RFC 9110 Section 5.6.7)"""
        return formatdate(timeval=None, localtime=False, usegmt=True)
    
    def get_file_modified_date(self, file_path):
        """Retorna la fecha de modificación del archivo en formato HTTP"""
        mtime = os.path.getmtime(file_path)
        return formatdate(timeval=mtime, localtime=False, usegmt=True)

    def parse_path_and_query(self, full_path):
        """Parsea la ruta y los query parameters"""
        parsed = urlparse(full_path)
        path = parsed.path
        query_params = parse_qs(parsed.query)
        # Convertir listas a valores simples
        params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        return path, params

    def handle_get(self, full_path, include_body=True):
        """
        Maneja peticiones GET y HEAD (RFC 9110 Section 9.3)
        
        Args:
            full_path: Ruta completa del recurso (puede incluir query string)
            include_body: True para GET, False para HEAD
        """
        # Parsear path y query parameters
        path, params = self.parse_path_and_query(full_path)
        
        # Endpoint especial para métricas (API)
        if path == "/api/metrics":
            self.send_metrics_json(include_body)
            return

        # Endpoint para resetear métricas
        if path == "/api/reset":
            self.reset_metrics(include_body)
            return

        # Endpoint para info del servidor
        if path == "/api/info":
            self.send_server_info(include_body)
            return

        # Documento por defecto (RFC 9110 Section 7.1)
        if path == "/":
            path = "/index.html"

        file_path = Path(PUBLIC_DIR + path)

        # Verificar que el archivo existe y es un archivo regular
        if not file_path.exists() or not file_path.is_file():
            self.send_error_response(404, "Not Found")
            return
        
        # Verificar que no se intenta acceder fuera de PUBLIC_DIR (seguridad)
        try:
            file_path.resolve().relative_to(Path(PUBLIC_DIR).resolve())
        except ValueError:
            self.send_error_response(403, "Forbidden")
            return

        # Verificar si se solicita procesamiento
        process_media = params.get("process") == "true" or params.get("resize")
        resize_percent = int(params.get("resize", 50)) if params.get("resize") else 50
        
        # Si es una imagen y se solicita procesamiento
        if process_media and PILLOW_AVAILABLE and file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
            self.handle_image_processing(file_path, resize_percent, include_body)
            return
        
        # Si es un video y se solicita procesamiento (extraer thumbnail)
        if process_media and FFMPEG_AVAILABLE and file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
            self.handle_video_thumbnail(file_path, include_body)
            return

        try:
            content_type = self.get_content_type(file_path)
            file_size = file_path.stat().st_size
            last_modified = self.get_file_modified_date(file_path)
            
            # Construir headers de respuesta según RFC 9110
            headers = [
                "HTTP/1.1 200 OK",
                f"Date: {self.get_http_date()}",
                f"Server: {SERVER_NAME}",
                f"Content-Type: {content_type}",
                f"Content-Length: {file_size}",
                f"Last-Modified: {last_modified}",
                "Accept-Ranges: bytes",
                "Access-Control-Allow-Origin: *",
                "Connection: close",
            ]
            
            response_headers = "\r\n".join(headers) + "\r\n\r\n"
            self.request.sendall(response_headers.encode("utf-8"))
            
            # Enviar body solo si es GET (no HEAD)
            if include_body:
                with open(file_path, "rb") as f:
                    # Enviar en chunks para archivos grandes
                    while True:
                        chunk = f.read(65536)  # 64KB chunks
                        if not chunk:
                            break
                        self.request.sendall(chunk)

        except Exception as e:
            print(f"Error reading file: {e}")
            self.send_error_response(500, "Internal Server Error")
    
    def handle_image_processing(self, file_path, resize_percent, include_body=True):
        """
        Procesa una imagen: redimensiona y comprime (CPU INTENSIVO)
        Este es el caso donde ForkingMixIn debería superar a ThreadingMixIn
        
        Args:
            file_path: Ruta del archivo de imagen
            resize_percent: Porcentaje de redimensión (1-100)
            include_body: True para GET, False para HEAD
        """
        try:
            print(f"[{SERVER_MODE}] Procesando imagen: {file_path.name} al {resize_percent}%")
            
            # Abrir imagen con Pillow (CPU intensivo: decodificación)
            with Image.open(file_path) as img:
                original_size = img.size
                
                # Calcular nuevo tamaño
                new_width = int(img.width * resize_percent / 100)
                new_height = int(img.height * resize_percent / 100)
                
                # Redimensionar (CPU intensivo: interpolación de píxeles)
                # Usar LANCZOS para mejor calidad (más CPU)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Determinar formato de salida
                if file_path.suffix.lower() == '.png':
                    output_format = 'PNG'
                    content_type = 'image/png'
                else:
                    output_format = 'JPEG'
                    content_type = 'image/jpeg'
                
                # Guardar en memoria (CPU intensivo: codificación)
                output_buffer = io.BytesIO()
                if output_format == 'JPEG':
                    resized_img.save(output_buffer, format=output_format, quality=85, optimize=True)
                else:
                    resized_img.save(output_buffer, format=output_format, optimize=True)
                
                content = output_buffer.getvalue()
                
                print(f"[{SERVER_MODE}] Imagen procesada: {original_size} -> ({new_width}, {new_height}), {len(content)} bytes")
            
            # Construir headers de respuesta
            headers = [
                "HTTP/1.1 200 OK",
                f"Date: {self.get_http_date()}",
                f"Server: {SERVER_NAME}",
                f"Content-Type: {content_type}",
                f"Content-Length: {len(content)}",
                "X-Image-Processed: true",
                f"X-Original-Size: {original_size[0]}x{original_size[1]}",
                f"X-New-Size: {new_width}x{new_height}",
                "Access-Control-Allow-Origin: *",
                "Connection: close",
            ]
            
            response_headers = "\r\n".join(headers) + "\r\n\r\n"
            self.request.sendall(response_headers.encode("utf-8"))
            
            if include_body:
                self.request.sendall(content)
                
        except Exception as e:
            print(f"Error procesando imagen: {e}")
            self.send_error_response(500, f"Error processing image: {str(e)}")
    
    def handle_video_thumbnail(self, file_path, include_body=True):
        """
        Extrae un thumbnail de un video usando FFmpeg (CPU INTENSIVO)
        
        Args:
            file_path: Ruta del archivo de video
            include_body: True para GET, False para HEAD
        """
        import subprocess
        import tempfile
        
        try:
            print(f"[{SERVER_MODE}] Extrayendo thumbnail de video: {file_path.name}")
            
            # Crear archivo temporal para el thumbnail
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            # Extraer frame del segundo 1 del video usando FFmpeg
            # -ss 1: Ir al segundo 1
            # -vframes 1: Extraer solo 1 frame
            # -q:v 2: Calidad alta (1-31, menor es mejor)
            cmd = [
                'ffmpeg',
                '-ss', '1',
                '-i', str(file_path),
                '-vframes', '1',
                '-q:v', '2',
                '-y',  # Sobrescribir si existe
                tmp_path
            ]
            
            # Ejecutar FFmpeg (CPU intensivo)
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr.decode()[:200]}")
            
            # Leer el thumbnail generado
            with open(tmp_path, 'rb') as f:
                content = f.read()
            
            # Eliminar archivo temporal
            os.unlink(tmp_path)
            
            print(f"[{SERVER_MODE}] Thumbnail extraído: {len(content)} bytes")
            
            # Construir headers de respuesta
            headers = [
                "HTTP/1.1 200 OK",
                f"Date: {self.get_http_date()}",
                f"Server: {SERVER_NAME}",
                "Content-Type: image/jpeg",
                f"Content-Length: {len(content)}",
                "X-Video-Thumbnail: true",
                f"X-Source-Video: {file_path.name}",
                "Access-Control-Allow-Origin: *",
                "Connection: close",
            ]
            
            response_headers = "\r\n".join(headers) + "\r\n\r\n"
            self.request.sendall(response_headers.encode("utf-8"))
            
            if include_body:
                self.request.sendall(content)
                
        except subprocess.TimeoutExpired:
            print(f"Error: FFmpeg timeout")
            self.send_error_response(500, "Video processing timeout")
        except Exception as e:
            print(f"Error procesando video: {e}")
            self.send_error_response(500, f"Error processing video: {str(e)}")

    def send_json_response(self, data, include_body=True):
        """Envía una respuesta JSON con headers HTTP/1.1 correctos"""
        content = json.dumps(data, indent=2)
        content_bytes = content.encode("utf-8")
        
        headers = [
            "HTTP/1.1 200 OK",
            f"Date: {self.get_http_date()}",
            f"Server: {SERVER_NAME}",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(content_bytes)}",
            "Access-Control-Allow-Origin: *",
            "Connection: close",
        ]
        
        response = "\r\n".join(headers) + "\r\n\r\n"
        self.request.sendall(response.encode("utf-8"))
        
        if include_body:
            self.request.sendall(content_bytes)

    def send_metrics_json(self, include_body=True):
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
        self.send_json_response(metrics, include_body)

    def reset_metrics(self, include_body=True):
        """Resetea las métricas"""
        with lock:
            request_count.value = 0
            total_response_time.value = 0.0
        self.send_json_response({"status": "ok", "message": "Metrics reset"}, include_body)

    def send_server_info(self, include_body=True):
        """Envía información del servidor"""
        info = {
            "mode": SERVER_MODE,
            "port": PORT,
            "host": HOST,
            "server": SERVER_NAME,
            "platform": platform.system(),
            "forking_available": IS_UNIX_LIKE,
            "pillow_available": PILLOW_AVAILABLE,
            "ffmpeg_available": FFMPEG_AVAILABLE,
            "image_processing": PILLOW_AVAILABLE,
            "video_processing": FFMPEG_AVAILABLE,
            "http_version": "HTTP/1.1",
            "supported_methods": ["GET", "HEAD"]
        }
        self.send_json_response(info, include_body)

    def send_error_response(self, code, message):
        """
        Envía una respuesta de error HTTP con headers correctos (RFC 9110 Section 15)
        """
        body = f"""<!DOCTYPE html>
<html>
<head><title>{code} {message}</title></head>
<body>
<h1>{code} {message}</h1>
<hr>
<p>{SERVER_NAME}</p>
</body>
</html>"""
        body_bytes = body.encode("utf-8")
        
        headers = [
            f"HTTP/1.1 {code} {message}",
            f"Date: {self.get_http_date()}",
            f"Server: {SERVER_NAME}",
            "Content-Type: text/html; charset=utf-8",
            f"Content-Length: {len(body_bytes)}",
            "Access-Control-Allow-Origin: *",
            "Connection: close",
        ]
        
        response = "\r\n".join(headers) + "\r\n\r\n"
        self.request.sendall(response.encode("utf-8") + body_bytes)

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
