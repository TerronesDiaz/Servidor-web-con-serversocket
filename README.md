# HTTP Server - Benchmark Comparativo

Servidor HTTP con `socketserver` que permite comparar el rendimiento entre **ThreadingMixIn** y **ForkingMixIn** con mediciones precisas desde el backend.

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
│   │   ├── file_example_MP4_1920_18MG.mp4  (18 MB)
│   │   └── sample-30s.mp4                   (5 MB)
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

## Archivos de Prueba

| Archivo | Tamaño | Uso |
|---------|--------|-----|
| PDF | 1 MB | Pruebas rápidas |
| PNG | 3 MB | Pruebas medianas |
| Video corto | 5 MB | Pruebas de carga |
| Video HD | 18 MB | Pruebas de rendimiento intensivo |

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
- No requiere dependencias externas
