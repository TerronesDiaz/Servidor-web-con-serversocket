#!/usr/bin/env python3
"""
Servidor de Benchmark - Ejecuta pruebas de rendimiento desde el backend
y expone los resultados via API para el frontend.
"""

import socketserver
import threading
import subprocess
import socket
import time
import json
import os
import sys
import platform
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HOST = "0.0.0.0"
BENCHMARK_PORT = 8082
THREADING_PORT = 8080
FORKING_PORT = 8081
PUBLIC_DIR = "public"

IS_UNIX_LIKE = platform.system() in ['Linux', 'Darwin', 'FreeBSD', 'OpenBSD']

# Resultados del último benchmark
last_benchmark_results = {
    "status": "idle",
    "threading": None,
    "forking": None,
    "comparison": None
}
results_lock = threading.Lock()


def make_http_request(host, port, path):
    """
    Hace una petición HTTP raw usando sockets.
    Retorna el tiempo en segundos.
    """
    start_time = time.perf_counter()
    sock = None
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(60)
        sock.connect((host, port))
        
        request = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
        sock.sendall(request.encode())
        
        # Recibir solo el header para verificar éxito (más rápido)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        
        # Consumir el resto del body
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
        except:
            pass
        
        elapsed = time.perf_counter() - start_time
        
        # Verificar que fue exitosa (200 OK)
        if b"200 OK" in response[:100]:
            return {"success": True, "time": elapsed}
        else:
            return {"success": False, "time": elapsed, "error": f"Non-200: {response[:50]}"}
            
    except socket.timeout:
        elapsed = time.perf_counter() - start_time
        return {"success": False, "time": elapsed, "error": "Timeout"}
    except ConnectionRefusedError:
        elapsed = time.perf_counter() - start_time
        return {"success": False, "time": elapsed, "error": "Connection refused"}
    except OSError as e:
        elapsed = time.perf_counter() - start_time
        return {"success": False, "time": elapsed, "error": f"OS Error: {e.errno}"}
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return {"success": False, "time": elapsed, "error": str(e)}
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass


def run_benchmark_test(port, file_path, num_requests, parallel=True):
    """
    Ejecuta un benchmark contra un servidor.
    
    Args:
        port: Puerto del servidor
        file_path: Ruta del archivo a solicitar
        num_requests: Número de peticiones
        parallel: Si True, ejecuta en paralelo; si False, secuencial
    
    Returns:
        dict con resultados del benchmark
    """
    results = []
    errors = {}
    start_total = time.perf_counter()
    
    # Limitar workers para no saturar el sistema
    max_workers = min(num_requests, 100)  # Máximo 100 conexiones simultáneas
    
    if parallel:
        # Ejecutar peticiones en paralelo usando ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(make_http_request, "127.0.0.1", port, file_path)
                for _ in range(num_requests)
            ]
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                # Contar errores
                if not result["success"]:
                    err = result.get("error", "Unknown")
                    errors[err] = errors.get(err, 0) + 1
    else:
        # Ejecutar peticiones secuencialmente
        for i in range(num_requests):
            result = make_http_request("127.0.0.1", port, file_path)
            results.append(result)
            
            if not result["success"]:
                err = result.get("error", "Unknown")
                errors[err] = errors.get(err, 0) + 1
    
    total_time = time.perf_counter() - start_total
    
    # Calcular estadísticas
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    if successful:
        times = [r["time"] for r in successful]
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
    else:
        avg_time = min_time = max_time = 0
    
    # Log de errores si hay
    if errors:
        print(f"  Errores encontrados: {errors}")
    
    return {
        "total_requests": num_requests,
        "successful": len(successful),
        "failed": len(failed),
        "total_time": round(total_time, 4),
        "avg_time": round(avg_time, 4),
        "min_time": round(min_time, 4),
        "max_time": round(max_time, 4),
        "requests_per_second": round(len(successful) / total_time, 2) if total_time > 0 and len(successful) > 0 else 0,
        "errors": errors if errors else None
    }


def check_server_available(port):
    """Verifica si un servidor está disponible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except:
        return False


def run_full_benchmark(file_path, num_requests, parallel=True):
    """
    Ejecuta benchmark completo en ambos servidores.
    """
    global last_benchmark_results
    
    with results_lock:
        last_benchmark_results["status"] = "running"
        last_benchmark_results["threading"] = None
        last_benchmark_results["forking"] = None
        last_benchmark_results["comparison"] = None
    
    results = {
        "file": file_path,
        "requests": num_requests,
        "parallel": parallel,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Verificar disponibilidad de servidores
    threading_available = check_server_available(THREADING_PORT)
    forking_available = check_server_available(FORKING_PORT)
    
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {num_requests} peticiones {'paralelas' if parallel else 'secuenciales'}")
    print(f"Archivo: {file_path}")
    print(f"{'='*60}")
    
    # Benchmark Threading
    if threading_available:
        print(f"\n[Threading] Ejecutando {num_requests} peticiones...")
        threading_results = run_benchmark_test(THREADING_PORT, file_path, num_requests, parallel)
        results["threading"] = threading_results
        print(f"[Threading] Completado: {threading_results['avg_time']:.4f}s promedio, {threading_results['requests_per_second']} req/s")
    else:
        print("[Threading] Servidor no disponible")
        results["threading"] = {"error": "Server not available"}
    
    # Benchmark Forking
    if forking_available:
        print(f"\n[Forking] Ejecutando {num_requests} peticiones...")
        forking_results = run_benchmark_test(FORKING_PORT, file_path, num_requests, parallel)
        results["forking"] = forking_results
        print(f"[Forking] Completado: {forking_results['avg_time']:.4f}s promedio, {forking_results['requests_per_second']} req/s")
    else:
        print("[Forking] Servidor no disponible")
        results["forking"] = {"error": "Server not available"}
    
    # Comparación
    if threading_available and forking_available:
        t_avg = results["threading"]["avg_time"]
        f_avg = results["forking"]["avg_time"]
        
        if t_avg > 0 and f_avg > 0:
            if t_avg < f_avg:
                winner = "threading"
                diff_percent = ((f_avg - t_avg) / f_avg) * 100
            else:
                winner = "forking"
                diff_percent = ((t_avg - f_avg) / t_avg) * 100
            
            results["comparison"] = {
                "winner": winner,
                "difference_percent": round(diff_percent, 2),
                "threading_rps": results["threading"]["requests_per_second"],
                "forking_rps": results["forking"]["requests_per_second"]
            }
            
            print(f"\n{'='*60}")
            print(f"RESULTADO: {winner.upper()} es {diff_percent:.1f}% más rápido")
            print(f"{'='*60}\n")
    
    with results_lock:
        last_benchmark_results = {
            "status": "completed",
            **results
        }
    
    return results


class BenchmarkRequestHandler(socketserver.BaseRequestHandler):
    """Handler para el servidor de benchmark"""
    
    def handle(self):
        try:
            data = self.request.recv(4096).decode("utf-8")
            if not data:
                return
            
            lines = data.split("\r\n")
            request_line = lines[0].split()
            
            if len(request_line) < 2:
                self.send_response(400, "Bad Request")
                return
            
            method, path = request_line[0], request_line[1]
            
            # Parsear query string
            query_params = {}
            if "?" in path:
                path, query_string = path.split("?", 1)
                for param in query_string.split("&"):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        query_params[key] = value
            
            if method == "GET":
                self.handle_get(path, query_params)
            else:
                self.send_response(405, "Method Not Allowed")
                
        except Exception as e:
            print(f"[Benchmark Error] {e}")
            self.send_response(500, str(e))
    
    def handle_get(self, path, params):
        if path == "/api/benchmark/run":
            self.run_benchmark_endpoint(params)
        elif path == "/api/benchmark/results":
            self.get_results_endpoint()
        elif path == "/api/benchmark/status":
            self.get_status_endpoint()
        elif path == "/" or path == "/index.html":
            self.serve_file("/index.html")
        elif path.startswith("/css/") or path.startswith("/js/"):
            self.serve_file(path)
        else:
            self.send_response(404, "Not Found")
    
    def run_benchmark_endpoint(self, params):
        """Endpoint para ejecutar benchmark"""
        from urllib.parse import unquote
        
        file_path = params.get("file", "/pdf/file-example_PDF_1MB.pdf")
        # Decodificar URL encoding (%2F -> /)
        file_path = unquote(file_path)
        
        num_requests = int(params.get("requests", "10"))
        parallel = params.get("parallel", "true").lower() == "true"
        
        # Ejecutar benchmark en un thread separado para no bloquear
        def run_async():
            run_full_benchmark(file_path, num_requests, parallel)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        
        response_data = {
            "status": "started",
            "file": file_path,
            "requests": num_requests,
            "parallel": parallel
        }
        self.send_json(response_data)
    
    def get_results_endpoint(self):
        """Endpoint para obtener resultados"""
        with results_lock:
            self.send_json(last_benchmark_results)
    
    def get_status_endpoint(self):
        """Endpoint para verificar estado de servidores"""
        status = {
            "benchmark_server": True,
            "threading_server": check_server_available(THREADING_PORT),
            "forking_server": check_server_available(FORKING_PORT),
            "platform": platform.system(),
            "forking_supported": IS_UNIX_LIKE
        }
        self.send_json(status)
    
    def serve_file(self, path):
        """Sirve archivos estáticos"""
        file_path = Path(PUBLIC_DIR + path)
        
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404, "Not Found")
            return
        
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }
        
        content_type = content_types.get(file_path.suffix, "application/octet-stream")
        
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
    
    def send_json(self, data):
        """Envía respuesta JSON"""
        content = json.dumps(data, indent=2)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(content)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{content}"
        )
        self.request.sendall(response.encode("utf-8"))
    
    def send_response(self, code, message):
        """Envía respuesta de error"""
        content = json.dumps({"error": message})
        response = (
            f"HTTP/1.1 {code} {message}\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{content}"
        )
        self.request.sendall(response.encode("utf-8"))


class ThreadedBenchmarkServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def start_all_servers():
    """Inicia todos los servidores necesarios"""
    processes = []
    
    print("\n" + "="*60)
    print("  BENCHMARK SERVER - Pruebas de Rendimiento desde Backend")
    print("="*60)
    
    # Iniciar servidor Threading
    print(f"\nIniciando servidor Threading en puerto {THREADING_PORT}...")
    threading_proc = subprocess.Popen(
        [sys.executable, "http_server.py", str(THREADING_PORT), "threading"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.getcwd()
    )
    processes.append(("Threading", threading_proc))
    time.sleep(0.5)
    
    # Iniciar servidor Forking (solo Unix)
    if IS_UNIX_LIKE:
        print(f"Iniciando servidor Forking en puerto {FORKING_PORT}...")
        forking_proc = subprocess.Popen(
            [sys.executable, "http_server.py", str(FORKING_PORT), "forking"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd()
        )
        processes.append(("Forking", forking_proc))
        time.sleep(0.5)
    else:
        print("Forking no disponible en este sistema (Windows)")
    
    # Iniciar servidor de Benchmark
    print(f"Iniciando servidor de Benchmark en puerto {BENCHMARK_PORT}...")
    benchmark_server = ThreadedBenchmarkServer((HOST, BENCHMARK_PORT), BenchmarkRequestHandler)
    
    print("\n" + "-"*60)
    print("SERVIDORES ACTIVOS:")
    print(f"  - Threading:  http://localhost:{THREADING_PORT}")
    if IS_UNIX_LIKE:
        print(f"  - Forking:    http://localhost:{FORKING_PORT}")
    print(f"  - Benchmark:  http://localhost:{BENCHMARK_PORT}")
    print("-"*60)
    print(f"\nAbre http://localhost:{BENCHMARK_PORT} en tu navegador")
    print("Presiona Ctrl+C para detener todos los servidores")
    print("="*60 + "\n")
    
    try:
        benchmark_server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nDeteniendo servidores...")
        for name, proc in processes:
            proc.terminate()
            proc.wait()
            print(f"  {name} detenido")
        benchmark_server.shutdown()
        print("Todos los servidores detenidos.")


if __name__ == "__main__":
    start_all_servers()

