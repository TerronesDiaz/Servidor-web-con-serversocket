/**
 * Benchmark Comparativo - ThreadingMixIn vs ForkingMixIn
 * Ejecuta pruebas desde el BACKEND para mediciones precisas
 */

const BENCHMARK_PORT = 8082;
const THREADING_PORT = 8080;
const FORKING_PORT = 8081;

let pollingInterval = null;

/**
 * Verifica el estado de los servidores
 */
async function checkServerStatus() {
    try {
        const response = await fetch(`http://localhost:${BENCHMARK_PORT}/api/benchmark/status`, {
            mode: 'cors',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            const status = await response.json();
            
            // Actualizar indicadores
            document.getElementById('threadingStatus').className = 
                status.threading_server ? 'status-dot online' : 'status-dot offline';
            document.getElementById('forkingStatus').className = 
                status.forking_server ? 'status-dot online' : 'status-dot offline';
            
            // Actualizar botón
            const btn = document.getElementById('runBenchmark');
            if (!status.threading_server && !status.forking_server) {
                btn.disabled = true;
                btn.textContent = 'Servidores no disponibles';
            } else {
                btn.disabled = false;
                btn.textContent = 'Ejecutar Benchmark';
            }
            
            return status;
        }
    } catch (e) {
        document.getElementById('threadingStatus').className = 'status-dot offline';
        document.getElementById('forkingStatus').className = 'status-dot offline';
        
        const btn = document.getElementById('runBenchmark');
        btn.disabled = true;
        btn.textContent = 'Servidor de benchmark no disponible';
    }
    
    return null;
}

/**
 * Agrega una entrada al log
 */
function addLog(message, type = '') {
    const container = document.getElementById('logContainer');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

/**
 * Actualiza la barra de progreso
 */
function updateProgress(percent, message) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    progressFill.style.width = `${percent}%`;
    progressText.textContent = message;
}

/**
 * Muestra los resultados en la tabla
 */
function displayResults(results) {
    if (!results || results.status === 'idle') {
        return;
    }
    
    // Threading
    if (results.threading && !results.threading.error) {
        const t = results.threading;
        document.getElementById('resultThreadingReqs').textContent = `${t.successful}/${t.total_requests}`;
        document.getElementById('resultThreadingAvg').textContent = `${(t.avg_time * 1000).toFixed(2)} ms`;
        document.getElementById('resultThreadingTotal').textContent = `${t.total_time.toFixed(3)} s`;
        document.getElementById('threadingRequests').textContent = t.successful;
        document.getElementById('threadingAvg').textContent = t.avg_time.toFixed(4);
    } else {
        document.getElementById('resultThreadingReqs').textContent = '-';
        document.getElementById('resultThreadingAvg').textContent = '-';
        document.getElementById('resultThreadingTotal').textContent = '-';
    }
    
    // Forking
    if (results.forking && !results.forking.error) {
        const f = results.forking;
        document.getElementById('resultForkingReqs').textContent = `${f.successful}/${f.total_requests}`;
        document.getElementById('resultForkingAvg').textContent = `${(f.avg_time * 1000).toFixed(2)} ms`;
        document.getElementById('resultForkingTotal').textContent = `${f.total_time.toFixed(3)} s`;
        document.getElementById('forkingRequests').textContent = f.successful;
        document.getElementById('forkingAvg').textContent = f.avg_time.toFixed(4);
    } else {
        document.getElementById('resultForkingReqs').textContent = '-';
        document.getElementById('resultForkingAvg').textContent = '-';
        document.getElementById('resultForkingTotal').textContent = '-';
    }
    
    // Comparación
    if (results.comparison) {
        const c = results.comparison;
        const winner = c.winner === 'threading' ? 'Threading' : 'Forking';
        document.getElementById('diffAvg').textContent = `${winner} ${c.difference_percent}% más rápido`;
        document.getElementById('diffTotal').textContent = 
            `Threading: ${c.threading_rps} req/s | Forking: ${c.forking_rps} req/s`;
        document.getElementById('diffReqs').textContent = 'Completado';
    } else {
        document.getElementById('diffAvg').textContent = '-';
        document.getElementById('diffTotal').textContent = '-';
        document.getElementById('diffReqs').textContent = '-';
    }
}

/**
 * Consulta el estado del benchmark
 */
async function pollBenchmarkResults() {
    try {
        const response = await fetch(`http://localhost:${BENCHMARK_PORT}/api/benchmark/results`, {
            mode: 'cors',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            const results = await response.json();
            
            if (results.status === 'running') {
                updateProgress(50, 'Ejecutando benchmark en el servidor...');
            } else if (results.status === 'completed') {
                // Detener polling
                if (pollingInterval) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                }
                
                updateProgress(100, 'Benchmark completado');
                displayResults(results);
                
                // Restaurar botón
                const btn = document.getElementById('runBenchmark');
                btn.disabled = false;
                btn.textContent = 'Ejecutar Benchmark';
                
                // Log
                if (results.comparison) {
                    const winner = results.comparison.winner === 'threading' ? 'Threading' : 'Forking';
                    addLog(`Benchmark completado: ${winner} es ${results.comparison.difference_percent}% más rápido`, 'success');
                } else {
                    addLog('Benchmark completado', 'success');
                }
            }
            
            return results;
        }
    } catch (e) {
        console.error('Error polling results:', e);
    }
    
    return null;
}

/**
 * Ejecuta el benchmark desde el backend
 */
async function runBenchmark() {
    const file = document.getElementById('benchmarkFile').value;
    const count = parseInt(document.getElementById('benchmarkCount').value);
    const parallel = document.getElementById('benchmarkParallel')?.checked !== false;
    const processImage = document.getElementById('benchmarkProcess')?.checked === true;

    // Verificar que se seleccionó una imagen o video si se quiere procesar
    if (processImage && !file.match(/\.(png|jpg|jpeg|gif|mp4|avi|mov|mkv)$/i)) {
        addLog('Error: "Procesar" solo funciona con imágenes (PNG, JPG, GIF) o videos (MP4)', 'error');
        return;
    }

    // Mostrar progreso
    const progressContainer = document.getElementById('progressContainer');
    progressContainer.style.display = 'block';
    updateProgress(10, 'Iniciando benchmark en el servidor...');

    // Deshabilitar botón
    const btn = document.getElementById('runBenchmark');
    btn.disabled = true;
    btn.textContent = 'Ejecutando...';

    const modeDesc = processImage ? 'con procesamiento CPU' : 'I/O estándar';
    addLog(`Iniciando benchmark: ${count} peticiones ${parallel ? 'paralelas' : 'secuenciales'} (${modeDesc})`, 'info');
    
    if (processImage) {
        if (file.match(/\.(mp4|avi|mov|mkv)$/i)) {
            addLog('Modo CPU intensivo: Se calcularán hashes SHA256/MD5 del video completo', 'info');
        } else {
            addLog('Modo CPU intensivo: Las imágenes serán redimensionadas al 50%', 'info');
        }
        addLog('En este modo, Forking debería superar a Threading', 'info');
    } else {
        addLog('Modo I/O: Threading debería ser más rápido', 'info');
    }

    try {
        // Llamar al endpoint de benchmark
        const url = `http://localhost:${BENCHMARK_PORT}/api/benchmark/run?file=${encodeURIComponent(file)}&requests=${count}&parallel=${parallel}&process=${processImage}`;
        
        const response = await fetch(url, {
            mode: 'cors',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            addLog('Benchmark iniciado en el servidor, esperando resultados...', 'info');
            
            // Iniciar polling para obtener resultados
            pollingInterval = setInterval(pollBenchmarkResults, 500);
        } else {
            throw new Error('Error al iniciar benchmark');
        }
    } catch (e) {
        addLog(`Error: ${e.message}`, 'error');
        btn.disabled = false;
        btn.textContent = 'Ejecutar Benchmark';
        updateProgress(0, 'Error');
    }
}

/**
 * Reinicia todas las métricas y resultados
 */
async function resetAll() {
    // Limpiar tabla
    const fields = [
        'resultThreadingReqs', 'resultForkingReqs',
        'resultThreadingAvg', 'resultForkingAvg',
        'resultThreadingTotal', 'resultForkingTotal',
        'diffReqs', 'diffAvg', 'diffTotal'
    ];
    fields.forEach(id => {
        document.getElementById(id).textContent = '-';
    });

    // Resetear métricas mostradas
    document.getElementById('threadingRequests').textContent = '0';
    document.getElementById('threadingAvg').textContent = '0.0000';
    document.getElementById('forkingRequests').textContent = '0';
    document.getElementById('forkingAvg').textContent = '0.0000';

    // Ocultar progreso
    document.getElementById('progressContainer').style.display = 'none';
    document.getElementById('progressFill').style.width = '0%';

    addLog('Resultados reiniciados', 'info');
}

/**
 * Copia texto al portapapeles
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        addLog(`Ruta copiada: ${text}`, 'success');
    }).catch(err => {
        // Fallback para navegadores antiguos
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        addLog(`Ruta copiada: ${text}`, 'success');
    });
}

/**
 * Inicialización cuando el DOM está listo
 */
document.addEventListener('DOMContentLoaded', function() {
    addLog('Conectando con servidor de benchmark...', 'info');
    
    checkServerStatus().then(status => {
        if (status) {
            addLog('Servidor de benchmark conectado', 'success');
            if (status.threading_server) addLog('Servidor Threading disponible', 'success');
            if (status.forking_server) addLog('Servidor Forking disponible', 'success');
            if (!status.forking_supported) {
                addLog('Nota: ForkingMixIn no disponible en este sistema', 'info');
            }
        } else {
            addLog('No se pudo conectar con el servidor de benchmark', 'error');
            addLog('Ejecuta: python benchmark_server.py', 'info');
        }
    });
    
    // Verificar estado cada 5 segundos
    setInterval(checkServerStatus, 5000);
});
