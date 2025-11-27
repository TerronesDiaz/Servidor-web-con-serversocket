#!/usr/bin/env python3
"""
Benchmark Comparativo - ThreadingMixIn vs ForkingMixIn

Inicia ambos servidores automáticamente y sirve una página
de benchmark que permite comparar el rendimiento en tiempo real.
"""

import subprocess
import sys
import os
import time
import signal
import platform

# Configuración
THREADING_PORT = 8080
FORKING_PORT = 8081
HOST = "localhost"

# Detectar sistema operativo
IS_UNIX_LIKE = platform.system() in ['Linux', 'Darwin', 'FreeBSD', 'OpenBSD']


def print_header():
    print("\n" + "="*60)
    print("  BENCHMARK COMPARATIVO - HTTP SERVER")
    print("  ThreadingMixIn vs ForkingMixIn")
    print("="*60)


def start_servers():
    """Inicia ambos servidores en background"""
    processes = []

    # Servidor Threading
    print(f"\nIniciando servidor Threading en puerto {THREADING_PORT}...")
    threading_proc = subprocess.Popen(
        [sys.executable, "http_server.py", str(THREADING_PORT), "threading"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.getcwd()
    )
    processes.append(("Threading", threading_proc, THREADING_PORT))
    time.sleep(0.5)

    # Servidor Forking (solo en Unix)
    if IS_UNIX_LIKE:
        print(f"Iniciando servidor Forking en puerto {FORKING_PORT}...")
        forking_proc = subprocess.Popen(
            [sys.executable, "http_server.py", str(FORKING_PORT), "forking"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        processes.append(("Forking", forking_proc, FORKING_PORT))
        time.sleep(0.5)
    else:
        print("\nADVERTENCIA: ForkingMixIn no disponible en este sistema.")
        print("Solo se ejecutará el servidor Threading.")
        print("Para comparar ambos modos, ejecuta en Linux/macOS o WSL.")

    return processes


def print_status(processes):
    print("\n" + "-"*60)
    print("SERVIDORES ACTIVOS:")
    print("-"*60)

    for name, proc, port in processes:
        status = "Ejecutando" if proc.poll() is None else "Detenido"
        print(f"  {name:12} | Puerto: {port} | Estado: {status}")

    print("-"*60)
    print(f"\nAbre tu navegador en: http://{HOST}:{THREADING_PORT}")
    print("\nLa página incluye:")
    print("  - Archivos de prueba para descargar")
    print("  - Benchmark comparativo automático")
    print("  - Tabla de resultados en tiempo real")
    print("\nPresiona Ctrl+C para detener todos los servidores")
    print("="*60 + "\n")


def stop_servers(processes):
    print("\n\nDeteniendo servidores...")

    for name, proc, port in processes:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
                print(f"  {name} detenido correctamente")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  {name} forzado a detener")

    print("\nTodos los servidores han sido detenidos.")


def main():
    print_header()

    # Verificar que existe http_server.py
    if not os.path.exists("http_server.py"):
        print("ERROR: No se encontró http_server.py")
        print("Asegúrate de ejecutar este script desde el directorio del proyecto.")
        sys.exit(1)

    # Iniciar servidores
    processes = start_servers()

    if not processes:
        print("ERROR: No se pudieron iniciar los servidores")
        sys.exit(1)

    # Mostrar estado
    print_status(processes)

    # Mantener vivo hasta Ctrl+C
    try:
        while True:
            # Verificar que los procesos siguen vivos
            for name, proc, port in processes:
                if proc.poll() is not None:
                    print(f"\nADVERTENCIA: Servidor {name} se detuvo inesperadamente")

            time.sleep(2)

    except KeyboardInterrupt:
        stop_servers(processes)


if __name__ == "__main__":
    main()

