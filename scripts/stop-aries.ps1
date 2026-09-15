<#
.SYNOPSIS
    Apaga ordenadamente el supervisor de Aries (start-aries.ps1) y todo
    lo que administra.

.DESCRIPTION
    Punto 2 del diagnóstico de sesión (2026-09-15): matar los PIDs de
    API/Voice/holder de WSL directamente NO alcanza mientras el
    supervisor siga corriendo — el loop de vigilancia de
    start-aries.ps1 los va a detectar caídos y relanzarlos, exactamente
    el comportamiento correcto ante cualquier OTRA causa de caída. Por
    eso este script nunca mata hijos directamente: le señala al
    SUPERVISOR que se apague (vía `.aries/stop.flag`) y espera a que él
    mismo baje a Voice, la API y el holder de WSL en su bloque `finally`
    — recién eso es un "stop" real, no una pelea con el propio
    supervisor.

.PARAMETER TimeoutSeconds
    Cuánto esperar el apagado ordenado antes de forzar.

.EXAMPLE
    .\scripts\stop-aries.ps1
#>

[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 30
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".aries"
$StopFlagPath = Join-Path $StateDir "stop.flag"
$SupervisorPidPath = Join-Path $StateDir "supervisor.pid"

if (-not (Test-Path $SupervisorPidPath)) {
    Write-Host "No hay ningún supervisor registrado ($SupervisorPidPath no existe) — nada que parar."
    exit 0
}

$supervisorProcessId = Get-Content -Path $SupervisorPidPath -ErrorAction SilentlyContinue
$supervisorProcess = if ($supervisorProcessId) { Get-Process -Id $supervisorProcessId -ErrorAction SilentlyContinue } else { $null }

if (-not $supervisorProcess) {
    Write-Host "El PID guardado ($supervisorProcessId) ya no está vivo — limpio el estado viejo (no hay nada corriendo)."
    Remove-Item -Path $SupervisorPidPath, $StopFlagPath -ErrorAction SilentlyContinue
    exit 0
}

Write-Host "Señalando apagado ordenado al supervisor (PID $supervisorProcessId)..."
New-Item -ItemType File -Path $StopFlagPath -Force | Out-Null

$elapsed = 0
while ((Get-Process -Id $supervisorProcessId -ErrorAction SilentlyContinue) -and $elapsed -lt $TimeoutSeconds) {
    Start-Sleep -Seconds 1
    $elapsed++
}

if (Get-Process -Id $supervisorProcessId -ErrorAction SilentlyContinue) {
    Write-Warning "El supervisor no bajó solo en ${TimeoutSeconds}s — forzando su cierre."
    Write-Warning "Esto puede dejar API/Voice/el holder de WSL huérfanos (el supervisor no llegó a su bloque de apagado) — revisá con Get-Process/'wsl -l -v' si hace falta limpiar a mano."
    Stop-Process -Id $supervisorProcessId -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $SupervisorPidPath, $StopFlagPath -ErrorAction SilentlyContinue
} else {
    Write-Host "Aries se apagó limpio."
}
