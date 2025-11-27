# HTTP Server - Benchmark Comparativo

Servidor HTTP/1.1 implementado con `socketserver` siguiendo el [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html). Permite comparar el rendimiento entre **ThreadingMixIn** y **ForkingMixIn** con mediciones precisas desde el backend.

## Características HTTP/1.1 Implementadas

Según el [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html):

| Característica | Sección RFC | Estado |
|----------------|-------------|--------|
| Método GET | 9.3.1 | ✅ |
| Método HEAD | 9.3.2 | ✅ |
| Header `Date` | 6.6.1 | ✅ |
| Header `Server` | 10.2.4 | ✅ |
| Header `Content-Type` | 8.3 | ✅ |
| Header `Content-Length` | 8.6 | ✅ |
| Header `Last-Modified` | 8.8.2 | ✅ |
| Códigos de estado | 15 | ✅ (200, 400, 403, 404, 405, 500) |

## Inicio Rápido

### Modo Benchmark (Recomendado)

Ejecuta todos los servidores automáticamente:

```bash
python benchmark_server.py
```

Esto inicia:
- **Threading** en `http://localhost:8080`
- **Forking** en `http://localhost:8081`
- **Benchmark Server** en `http://localhost:8082`

Luego abre `http://localhost:8082` en tu navegador para ver la página de benchmark.

### ¿Por qué desde el backend?

Las mediciones se hacen con **sockets raw desde Python**, no desde el navegador. Esto elimina:
- Límite de conexiones del navegador (6 por dominio)
- Overhead de JavaScript
- Latencia del DOM

El resultado son **tiempos reales y precisos**.

### Modo Individual

Ejecutar un servidor específico:

```bash
# Threading (puerto 8080)
python http_server.py 8080 threading

# Forking (puerto 8081) - Solo Unix/Linux/macOS
python http_server.py 8081 forking
```

## Uso del Benchmark

1. Ejecuta `python benchmark.py`
2. Abre `http://localhost:8080` en el navegador
3. Selecciona el archivo y número de peticiones
4. Haz clic en **Ejecutar Benchmark**
5. Observa la tabla comparativa con los resultados

La página muestra:
- Estado de ambos servidores (online/offline)
- Métricas en tiempo real
- Tabla comparativa con diferencias porcentuales
- Log de actividad

## Estructura del Proyecto

```
.
├── http_server.py      # Servidor HTTP principal
├── benchmark.py        # Script para iniciar ambos servidores
├── public/
│   ├── index.html      # Página de benchmark
│   ├── css/
│   │   └── styles.css  # Estilos CSS
│   ├── js/
│   │   └── benchmark.js # Lógica JavaScript
│   ├── mp4/
│   │   ├── 5898193_Person_Human_3840x2160.mp4  (Video 4K)
│   │   └── sample-30s.mp4                       (5 MB)
│   ├── pdf/
│   │   └── file-example_PDF_1MB.pdf         (1 MB)
│   └── png/
│       └── file_example_PNG_3MB.png         (3 MB)
└── README.md
```

## API Endpoints

El servidor expone endpoints para métricas:

| Endpoint | Descripción |
|----------|-------------|
| `/api/metrics` | Devuelve métricas actuales (JSON) |
| `/api/reset` | Reinicia las métricas |
| `/api/info` | Información del servidor |

Ejemplo de respuesta `/api/metrics`:
```json
{
  "mode": "threading",
  "port": 8080,
  "requests": 25,
  "avg_time": 0.0234,
  "total_time": 0.585
}
```

## Compatibilidad

| Sistema | ThreadingMixIn | ForkingMixIn |
|---------|---------------|--------------|
| Windows | ✅ | ❌ |
| Linux | ✅ | ✅ |
| macOS | ✅ | ✅ |
| WSL | ✅ | ✅ |

**Nota**: En Windows, solo ThreadingMixIn está disponible. Para comparar ambos modos, usa WSL o un sistema Unix-like.

## Prueba de Headers HTTP

Puedes verificar los headers HTTP/1.1 con curl:

```bash
# Ver headers de respuesta
curl -I http://localhost:8080/

# Petición HEAD (sin body)
curl --head http://localhost:8080/png/file_example_PNG_3MB.png

# Ver respuesta completa con headers
curl -v http://localhost:8080/api/info
```

Ejemplo de respuesta:
```
HTTP/1.1 200 OK
Date: Thu, 27 Nov 2025 06:30:00 GMT
Server: PythonHTTPServer/1.0
Content-Type: text/html; charset=utf-8
Content-Length: 1234
Last-Modified: Wed, 26 Nov 2025 10:00:00 GMT
Accept-Ranges: bytes
Connection: close
```

## Archivos de Prueba

| Archivo | Tamaño | Uso |
|---------|--------|-----|
| PDF | 1 MB | Pruebas rápidas |
| PNG | 3 MB | Pruebas medianas |
| Video corto | 5 MB | Pruebas de carga |
| Video 4K | 97.4 MB | Pruebas de rendimiento intensivo |

## Diferencias entre Modos

### ThreadingMixIn
- Usa hilos (threads) para manejar conexiones
- Comparte memoria entre hilos
- Menor overhead de creación
- Afectado por el GIL de Python

### ForkingMixIn
- Usa procesos separados (fork)
- Memoria aislada por proceso
- Mayor overhead de creación
- No afectado por el GIL
- Solo disponible en sistemas Unix-like

## Requisitos

- Python 3.7+
- Pillow (para procesamiento de imágenes)

### Instalación de dependencias

```bash
pip install -r requirements.txt
```

## Procesamiento de Media (CPU Intensivo)

El servidor incluye la capacidad de **procesar imágenes y videos on-the-fly**, lo cual es CPU intensivo y demuestra cuándo **ForkingMixIn supera a ThreadingMixIn**.

### Uso

Agrega `?process=true` a cualquier imagen o video:
```bash
# Imagen: redimensiona al 50%
http://localhost:8080/png/file_example_PNG_3MB.png?process=true

# Video: extrae thumbnail (frame del segundo 1)
http://localhost:8080/mp4/sample-30s.mp4?process=true
```

O usa el checkbox "Procesar (CPU)" en el benchmark.

### Requisitos

| Tipo | Dependencia | Instalación |
|------|-------------|-------------|
| Imágenes | Pillow | `pip install Pillow` |
| Videos | FFmpeg | Instalar desde [ffmpeg.org](https://ffmpeg.org/download.html) |

### ¿Por qué Forking gana con CPU intensivo?

| Escenario | Ganador | Razón |
|-----------|---------|-------|
| I/O (archivos) | Threading | Menor overhead, GIL se libera durante I/O |
| CPU (procesamiento) | Forking | Sin GIL, paralelismo real en múltiples cores |

**Procesamiento de imágenes** (Pillow):
- Decodificación de la imagen
- Redimensionado con interpolación LANCZOS
- Recodificación y compresión

**Procesamiento de videos** (FFmpeg):
- Decodificación del video
- Extracción de frame específico
- Codificación a JPEG

Estas operaciones son **CPU-bound** y el GIL de Python impide que Threading las ejecute en paralelo real.
