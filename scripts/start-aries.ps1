<#
.SYNOPSIS
    Supervisor único de Aries OS: arranca y vigila WSL2 (holder de Redis),
    la API y VoicePipeline, y los relanza si se caen.

.DESCRIPTION
    Fase 1 del plan de arranque automático (ver diagnóstico de sesión,
    2026-09-15) — reemplaza abrir 4-5 terminales a mano por una sola
    ejecución de este script. NO es todavía la solución "arranca solo al
    prender Windows" (eso es Fase 2, vía Task Scheduler invocando este
    mismo script) — acá el objetivo es un supervisor real, no un lanzador
    que arranca todo una vez y se olvida:

    - Un único loop de supervisión vigila LOS CUATRO elementos (holder de
      WSL, Redis vía PING, API, Voice) — no solo API/Voice. Si el proceso
      que mantiene viva la VM de WSL2 muere (reinicio de WSL, un
      `wsl --shutdown`, una actualización), Redis desaparece ~8s después
      SIN que la API ni Voice se enteren — el wake word sigue funcionando,
      las rutinas simplemente dejan de sonar, en silencio. Es exactamente
      la falla que todo el diseño de Streams (MessageBus.spec.md) existe
      para evitar, así que el holder y el PING viven en el MISMO loop que
      vigila los otros dos, no solo en el arranque inicial.
    - Guardia de instancia única vía un Mutex nombrado de Windows — si ya
      hay un supervisor corriendo (por Task Scheduler o por vos a mano
      debuggeando) y corrés este script de nuevo, sale enseguida sin tocar
      nada. Sin esto: dos APIs peleando por el puerto 8000, dos Voice
      peleando por el micrófono, y dos consumidores con el MISMO nombre
      estable ("voice-pipeline"/"main") compartiendo PEL en el mismo
      consumer group de Redis — comportamiento no determinístico y habla
      duplicada, difícil de diagnosticar (ver MessageBus.spec.md sección
      6.4: el nombre de consumidor fijo asume un solo proceso a la vez).
    - Apagado ordenado vía un archivo de señal (`.aries/stop.flag`), no
      matando PIDs a ciegas — `stop-aries.ps1` es el único camino soportado
      para parar esto; ver ese script para el porqué (si algo mata los
      hijos sin avisarle primero al supervisor, este simplemente los
      relanza, que es el comportamiento correcto en cualquier OTRO
      escenario de caída).
    - Logs por lanzamiento con timestamp (nunca se pisan entre reinicios)
      + rotación por tamaño (un reinicio controlado del hijo correspondiente
      cuando su log supera `-MaxLogSizeMB`) + limpieza de logs viejos por
      antigüedad. `LOG_LEVEL` por defecto en INFO (no el DEBUG de
      `Settings`) para no llenar el disco con logging por frame de Voice
      durante las 2 semanas de validación de Fase 1 — parametrizable si en
      algún momento hace falta debuggear en DEBUG.

    Deliberadamente NO implementado acá (ver docs, no es parte de esta
    tarea): apagado *gracioso* de los procesos Python (Kernel.shutdown(),
    descarga de plugins en orden inverso, KernelShutdownEvent) — este
    script usa `Stop-Process -Force` (terminación dura) tanto en el
    apagado ordenado como al relanzar un hijo caído. Es seguro (SQLite se
    commitea por operación, no hay estado en memoria pendiente de flush
    final) pero se salta esa limpieza "prolija". Aceptable para Fase 1 de
    desarrollo; si hace falta un apagado real vía CTRL_BREAK_EVENT más
    adelante, es una mejora aislada a `Stop-ChildProcess` más abajo.
    Tampoco valida honestamente la salud de Redis/Voice en `GET /health`
    (sigue devolviendo `{"status": "ok"}` fijo) — señalado como pendiente
    antes de Fase 2, no bloqueante acá.

.PARAMETER SupervisionIntervalSeconds
    Cada cuánto el loop revisa los 4 elementos vigilados.

.PARAMETER MaxLogSizeMB
    Tamaño máximo (por archivo out/err) antes de rotar un hijo con un
    reinicio controlado.

.PARAMETER LogRetentionDays
    Los archivos de log más viejos que esto se borran en cada vuelta del
    loop.

.PARAMETER LogLevel
    Nivel de log exportado a la API/Voice vía la variable de entorno
    LOG_LEVEL (sobreescribe lo que diga .env — ver Settings, pydantic-settings
    prioriza variables de entorno del proceso sobre el archivo .env).

.EXAMPLE
    .\scripts\start-aries.ps1
    .\scripts\start-aries.ps1 -LogLevel DEBUG -SupervisionIntervalSeconds 10
#>

[CmdletBinding()]
param(
    [int]$SupervisionIntervalSeconds = 15,
    [int]$RedisReadyTimeoutSeconds = 60,
    [int]$ApiReadyTimeoutSeconds = 60,
    [int]$MaxLogSizeMB = 20,
    [int]$LogRetentionDays = 14,
    [string]$WslDistro = "Ubuntu",
    [string]$ApiHealthUrl = "http://127.0.0.1:8000/health",
    [string]$LogLevel = "INFO",
    [int]$BaseBackoffSeconds = 10,
    [int]$MaxBackoffSeconds = 300,
    [int]$StableAfterSeconds = 300
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------
# 0. Rutas y estado
# ---------------------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".aries"
$LogDir = Join-Path $RepoRoot "logs"
$PythonExe = Join-Path $RepoRoot ".venv-313\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $PythonExe)) {
    Write-Error "No se encontró el intérprete del venv en '$PythonExe'. ¿Corriste esto desde el repo correcto, con .venv-313 ya creado?"
    exit 1
}

$MutexName = "Global\AriesSupervisor"
$StopFlagPath = Join-Path $StateDir "stop.flag"
$SupervisorPidPath = Join-Path $StateDir "supervisor.pid"
$SupervisorLogPath = Join-Path $LogDir "supervisor.log"

# ---------------------------------------------------------------------
# 1. Guardia de instancia única (punto 3 del diagnóstico)
# ---------------------------------------------------------------------
$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$acquired = $mutex.WaitOne(0)
if (-not $acquired) {
    Write-Host "Ya hay un supervisor de Aries corriendo (mutex '$MutexName' tomado por otro proceso)."
    Write-Host "Si creés que es un error (ej. quedó huérfano), corré stop-aries.ps1 primero."
    exit 1
}

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    # -Encoding UTF8 explícito: sin esto, Add-Content usa el codepage del
    # sistema y cualquier acento/raya queda ilegible al leer el log desde
    # otra herramienta (confirmado en la prueba real de este script).
    Add-Content -Path $SupervisorLogPath -Value $line -Encoding UTF8
}

# Limpiar señales/estado de una corrida anterior que no cerró prolijo.
Remove-Item -Path $StopFlagPath -ErrorAction SilentlyContinue
$PID | Out-File -FilePath $SupervisorPidPath -Encoding ascii -Force

Write-Log "=== Supervisor de Aries arrancando (PID $PID) ==="

# ---------------------------------------------------------------------
# 2. Estado de cada hijo vigilado
# ---------------------------------------------------------------------
function New-ChildState {
    [PSCustomObject]@{
        Process        = $null
        Failures       = 0
        LastStartedAt  = $null
        OutLogPath     = $null
        ErrLogPath     = $null
    }
}

$Children = @{
    WslHolder = New-ChildState
    Api       = New-ChildState
    Voice     = New-ChildState
}

function New-TimestampedLogPaths {
    param([string]$Prefix)
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    [PSCustomObject]@{
        Out = Join-Path $LogDir ("{0}_{1}.out.log" -f $Prefix, $stamp)
        Err = Join-Path $LogDir ("{0}_{1}.err.log" -f $Prefix, $stamp)
    }
}

function Test-ProcessAlive {
    param($Process)
    if ($null -eq $Process) { return $false }
    try {
        return -not $Process.HasExited
    } catch {
        return $false
    }
}

function Stop-ChildProcess {
    param($Process, [string]$Name)
    if (Test-ProcessAlive $Process) {
        Write-Log "Deteniendo $Name (PID $($Process.Id))..."
        try { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}

# ---------------------------------------------------------------------
# 3. Cómo se arranca cada hijo
# ---------------------------------------------------------------------
function Start-WslHolderProcess {
    $paths = New-TimestampedLogPaths -Prefix "wsl-holder"
    # `sleep infinity` corriendo DENTRO de la distro mantiene la VM de
    # WSL2 adjunta — sin esto, Windows la apaga ~8s después de que se
    # desconecta el último proceso adjunto, y Redis se va con ella aunque
    # redis-server.service esté `enabled` en systemd (ya lo está, ver
    # diagnóstico — no hace falta arrancar Redis a mano, solo mantener la
    # VM viva).
    $proc = Start-Process -FilePath "wsl.exe" `
        -ArgumentList @("-d", $WslDistro, "--", "sleep", "infinity") `
        -RedirectStandardOutput $paths.Out -RedirectStandardError $paths.Err `
        -NoNewWindow -PassThru
    $Children.WslHolder.Process = $proc
    $Children.WslHolder.LastStartedAt = Get-Date
    $Children.WslHolder.OutLogPath = $paths.Out
    $Children.WslHolder.ErrLogPath = $paths.Err
    Write-Log "Holder de WSL ('$WslDistro') arrancado (PID $($proc.Id))."
}

function Start-ApiProcess {
    $paths = New-TimestampedLogPaths -Prefix "api"
    $env:LOG_LEVEL = $LogLevel
    $proc = Start-Process -FilePath $PythonExe -ArgumentList @("-m", "aries") `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $paths.Out -RedirectStandardError $paths.Err `
        -NoNewWindow -PassThru
    $Children.Api.Process = $proc
    $Children.Api.LastStartedAt = Get-Date
    $Children.Api.OutLogPath = $paths.Out
    $Children.Api.ErrLogPath = $paths.Err
    Write-Log "API arrancada (PID $($proc.Id)) — log: $($paths.Out)"
}

function Start-VoiceProcess {
    $paths = New-TimestampedLogPaths -Prefix "voice"
    $env:LOG_LEVEL = $LogLevel
    $proc = Start-Process -FilePath $PythonExe -ArgumentList @("-m", "aries.voice") `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $paths.Out -RedirectStandardError $paths.Err `
        -NoNewWindow -PassThru
    $Children.Voice.Process = $proc
    $Children.Voice.LastStartedAt = Get-Date
    $Children.Voice.OutLogPath = $paths.Out
    $Children.Voice.ErrLogPath = $paths.Err
    Write-Log "VoicePipeline arrancado (PID $($proc.Id)) — log: $($paths.Out)"
}

# ---------------------------------------------------------------------
# 4. Chequeos de salud reales (no sleeps fijos a ciegas)
# ---------------------------------------------------------------------
function Test-RedisReady {
    try {
        $result = wsl.exe -d $WslDistro -- redis-cli ping 2>$null
        return ($result -match "PONG")
    } catch {
        return $false
    }
}

function Test-ApiReady {
    try {
        $response = Invoke-WebRequest -Uri $ApiHealthUrl -TimeoutSec 3 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Until {
    param([scriptblock]$Condition, [int]$TimeoutSeconds, [string]$Description)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 2
    }
    Write-Log "ADVERTENCIA: '$Description' no quedó listo en ${TimeoutSeconds}s — sigo igual, el loop de supervisión lo va a seguir intentando."
    return $false
}

# ---------------------------------------------------------------------
# 5. Reinicio con backoff exponencial (evita machacar un proceso que
#    crashea en loop apenas arranca, ej. config rota)
# ---------------------------------------------------------------------
function Restart-Child {
    param([string]$Name, [scriptblock]$StartFunction)
    $state = $Children[$Name]
    $delay = [Math]::Min($MaxBackoffSeconds, $BaseBackoffSeconds * [Math]::Pow(2, $state.Failures))
    if ($delay -gt 0) {
        Write-Log "Esperando ${delay}s antes de relanzar $Name (intento fallido #$($state.Failures + 1))..."
        Start-Sleep -Seconds $delay
    }
    & $StartFunction
    $state.Failures++
}

# ---------------------------------------------------------------------
# 6. Arranque inicial, en orden, con espera real por salud
# ---------------------------------------------------------------------
Start-WslHolderProcess
Wait-Until -Condition { Test-RedisReady } -TimeoutSeconds $RedisReadyTimeoutSeconds -Description "Redis (PING)" | Out-Null

Start-ApiProcess
Wait-Until -Condition { Test-ApiReady } -TimeoutSeconds $ApiReadyTimeoutSeconds -Description "API (GET /health)" | Out-Null

Start-VoiceProcess

Write-Log "Arranque inicial completo. Entrando al loop de supervisión (cada ${SupervisionIntervalSeconds}s)."

# ---------------------------------------------------------------------
# 7. Loop de supervisión único — API, Voice, holder de WSL y Redis viven
#    ACÁ, todos juntos (punto 1 del diagnóstico: antes el holder de WSL
#    quedaba fuera de cualquier vigilancia post-arranque).
# ---------------------------------------------------------------------
try {
    while ($true) {
        if (Test-Path $StopFlagPath) {
            Write-Log "stop.flag detectado — apagando ordenadamente."
            break
        }

        # -- Holder de WSL (y por lo tanto Redis, indirectamente) --
        if (-not (Test-ProcessAlive $Children.WslHolder.Process)) {
            Write-Log "ALERTA: el holder de WSL murió — sin esto Redis se apaga solo en ~8s. Relanzando."
            Restart-Child -Name "WslHolder" -StartFunction { Start-WslHolderProcess }
        } elseif ($Children.WslHolder.Failures -gt 0 -and
                  ((Get-Date) - $Children.WslHolder.LastStartedAt).TotalSeconds -gt $StableAfterSeconds) {
            Write-Log "Holder de WSL estable hace más de ${StableAfterSeconds}s — reseteo el contador de reintentos."
            $Children.WslHolder.Failures = 0
        }

        # -- Redis en sí (el holder puede estar vivo con redis-server
        #    crasheado adentro) --
        if (-not (Test-RedisReady)) {
            Write-Log "ALERTA: Redis no responde PING (holder de WSL vivo). Intentando reiniciar el servicio dentro de la distro."
            wsl.exe -d $WslDistro -- sudo systemctl restart redis-server 2>&1 | Out-Null
        }

        # -- API --
        if (-not (Test-ProcessAlive $Children.Api.Process)) {
            Write-Log "ALERTA: la API murió. Relanzando."
            Restart-Child -Name "Api" -StartFunction { Start-ApiProcess }
        } elseif ($Children.Api.Failures -gt 0 -and
                  ((Get-Date) - $Children.Api.LastStartedAt).TotalSeconds -gt $StableAfterSeconds) {
            Write-Log "API estable hace más de ${StableAfterSeconds}s — reseteo el contador de reintentos."
            $Children.Api.Failures = 0
        }

        # -- Voice --
        if (-not (Test-ProcessAlive $Children.Voice.Process)) {
            Write-Log "ALERTA: VoicePipeline murió. Relanzando."
            Restart-Child -Name "Voice" -StartFunction { Start-VoiceProcess }
        } elseif ($Children.Voice.Failures -gt 0 -and
                  ((Get-Date) - $Children.Voice.LastStartedAt).TotalSeconds -gt $StableAfterSeconds) {
            Write-Log "VoicePipeline estable hace más de ${StableAfterSeconds}s — reseteo el contador de reintentos."
            $Children.Voice.Failures = 0
        }

        # -- Rotación de logs por tamaño: un reinicio controlado usa el
        #    mismo camino que la recuperación de una caída real. --
        foreach ($name in @("Api", "Voice")) {
            $state = $Children[$name]
            if (-not (Test-ProcessAlive $state.Process)) { continue }
            $tooBig = $false
            foreach ($logPath in @($state.OutLogPath, $state.ErrLogPath)) {
                if ((Test-Path $logPath) -and ((Get-Item $logPath).Length / 1MB -gt $MaxLogSizeMB)) {
                    $tooBig = $true
                }
            }
            if ($tooBig) {
                Write-Log "Log de $name superó ${MaxLogSizeMB}MB — rotando con un reinicio controlado."
                Stop-ChildProcess -Process $state.Process -Name $name
                if ($name -eq "Api") { Start-ApiProcess } else { Start-VoiceProcess }
            }
        }

        # -- Limpieza de logs viejos --
        Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$LogRetentionDays) } |
            Remove-Item -Force -ErrorAction SilentlyContinue

        Start-Sleep -Seconds $SupervisionIntervalSeconds
    }
} finally {
    Write-Log "Apagando Voice, API y el holder de WSL..."
    Stop-ChildProcess -Process $Children.Voice.Process -Name "Voice"
    Stop-ChildProcess -Process $Children.Api.Process -Name "Api"
    Stop-ChildProcess -Process $Children.WslHolder.Process -Name "WslHolder"

    Remove-Item -Path $StopFlagPath -ErrorAction SilentlyContinue
    Remove-Item -Path $SupervisorPidPath -ErrorAction SilentlyContinue

    $mutex.ReleaseMutex() | Out-Null
    $mutex.Dispose()

    Write-Log "=== Supervisor de Aries apagado ==="
}
