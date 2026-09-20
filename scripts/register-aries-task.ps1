<#
.SYNOPSIS
    Registra (o desregistra) la tarea de Task Scheduler que arranca el
    supervisor de Aries (start-aries.ps1) al iniciar sesión en Windows.

.DESCRIPTION
    Fase 2 del plan de arranque automático. Es idempotente: correrlo de
    nuevo reemplaza la tarea existente.

    Decisiones (cada una con su porqué):
    - Trigger "At log on" del usuario actual, y `LogonType Interactive`
      ("Run only when user is logged on"): VoicePipeline necesita la sesión
      interactiva del usuario para acceder al micrófono/parlante. Un servicio
      de Windows o una tarea "run whether user is logged on or not" corre en
      Session 0, sin acceso fiable al audio.
    - Ventana oculta (`-WindowStyle Hidden`): sin consola a la vista, las
      señales de estado son `logs/supervisor.log` y `GET /health`.
    - `ExecutionTimeLimit` ilimitado: el default de Task Scheduler es 72 h y
      MATA la tarea al cumplirse — un supervisor tiene que vivir
      indefinidamente.
    - Reinicio ante fallo (3 intentos, 1 minuto entre uno y otro): cubre que
      el supervisor mismo caiga (start-aries.ps1 ya vigila y relanza a sus
      hijos por dentro; esto es la red para el supervisor). Un apagado
      ordenado (stop-aries.ps1) sale con código 0 y NO dispara reinicio. Si el
      supervisor sale con código 1 porque ya hay otra instancia (mutex), el
      reinicio reintenta 3 veces y se rinde — inofensivo.
    - `MultipleInstances IgnoreNew`: segunda red, además del mutex del propio
      script, contra dos supervisores.
    - Corre con permisos limitados (`RunLevel Limited`): nada de lo que
      arranca Aries necesita elevación.

.PARAMETER TaskName
    Nombre de la tarea en Task Scheduler.

.PARAMETER Unregister
    Elimina la tarea en vez de registrarla.

.EXAMPLE
    .\scripts\register-aries-task.ps1
    .\scripts\register-aries-task.ps1 -Unregister
#>

[CmdletBinding()]
param(
    [string]$TaskName = "Aries OS",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarea '$TaskName' eliminada."
    } else {
        Write-Host "La tarea '$TaskName' no existe — nada que eliminar."
    }
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start-aries.ps1"
if (-not (Test-Path $StartScript)) {
    Write-Error "No se encontró '$StartScript'."
    exit 1
}

$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`"" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Supervisor de Aries OS (WSL2/Redis + API + Voice) — ver scripts/start-aries.ps1" `
    -Force | Out-Null

Write-Host "Tarea '$TaskName' registrada para '$user' (trigger: al iniciar sesión)."
Write-Host "Probarla ahora sin reiniciar:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Apagarla ordenadamente:        .\scripts\stop-aries.ps1"
