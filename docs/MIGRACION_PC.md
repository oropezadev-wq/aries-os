# Migración de PC — disco M.2 externo

> Checklist armado el 2026-09-26 antes de mover el disco M.2 externo (donde
> vive todo este repo) a una PC nueva. Guardado en el repo para no depender
> de tenerlo apuntado a mano — viaja con el disco, así que va a estar
> disponible en la PC nueva también.

## 1. Rutas absolutas verificadas (ya corregido)

Se revisó todo el repo (código, scripts, configs, docs) buscando rutas con
letra de unidad hardcodeada (ej. `E:\Proyectos\...`) que se rompan si el
disco cambia de letra en la PC nueva.

**Encontrado y corregido:** `.env` tenía
`VOICE_TTS_MODEL_PATH=E:\Proyectos\Aries\Aries_OS\es_MX-claude-high.onnx`
— se cambió a ruta relativa (`VOICE_TTS_MODEL_PATH=es_MX-claude-high.onnx`).
Resuelve bien porque `start-aries.ps1` siempre arranca los procesos con el
directorio de trabajo en la raíz del repo (`$RepoRoot`, calculado
dinámicamente desde `$PSScriptRoot`, nunca hardcodeado) — una ruta relativa
ahí no depende de la letra de unidad. `.env` no se versiona, pero viaja con
el disco igual, así que este fix ya está en el archivo real.

**Todo lo demás ya estaba bien por diseño, verificado explícitamente:**

- Los 3 scripts de PowerShell (`scripts/start-aries.ps1`,
  `scripts/stop-aries.ps1`, `scripts/register-aries-task.ps1`) calculan
  `$RepoRoot` dinámicamente vía `Split-Path -Parent $PSScriptRoot` — nunca
  una ruta fija.
- `src/aries/config/settings.py` — todos los campos de ruta
  (`memory_db_path`, `plugins_dir`, `filesystem_allowed_root`, etc.) tienen
  defaults relativos o vacíos (fail-closed), ninguno con letra de unidad
  hardcodeada.
- `tools/wake_word_training/*.py` resuelven todo relativo a
  `Path(__file__).resolve().parent`, no al directorio de trabajo ni a una
  ruta fija.
- `CLAUDE.md`, `.github/`, `docs/specs/`, `docs/contracts/`,
  `docs/01_ARCHITECTURE.md` — sin referencias a rutas absolutas del repo.

**Ojo con esto — no es código, pero rompe igual si no se repite el paso:**
si en algún momento se registra la tarea de Task Scheduler
(`register-aries-task.ps1`), esa tarea graba una ruta absoluta en su
definición al momento de registrarla. Si se migra con la tarea ya
registrada desde la PC vieja, va a apuntar a la letra de unidad vieja. Al
2026-09-26 la tarea está desregistrada, así que no es un problema
inmediato — pero **hay que registrarla de nuevo en la PC nueva** (paso 5
más abajo), no asumir que la vieja sirve.

## 2. Qué reinstalar en la PC nueva

Nada de esto vive en el disco externo — hay que rehacerlo a mano. En orden
recomendado:

### 2.1 Imprescindible para que Aries arranque

1. **Python 3.13.14.** El venv actual (`.venv-313`) apunta a
   `C:\Users\orphalyx\AppData\Local\Programs\Python\Python313` — la unidad
   C: de la PC vieja, no el disco externo. **No copiar el venv y esperar
   que funcione** (`pyvenv.cfg` tiene esa ruta vieja grabada, y puede que
   la PC nueva ni tenga el mismo nombre de usuario de Windows). Recrearlo
   fresco:
   ```powershell
   python -m venv .venv-313
   .venv-313\Scripts\pip install -e ".[dev,voice,voice-training]"
   ```
   Esos son los extras realmente en uso — `desktop` y `docs` nunca se
   instalaron en esta máquina, no hace falta repetirlos salvo que se vayan
   a usar.

2. **Ollama.** Se instala en `C:\Users\...`, no en el disco externo.
   Reinstalar desde [ollama.com](https://ollama.com).

3. **Los 3 modelos de Ollama.** `OLLAMA_MODELS` apunta a
   `C:\Users\orphalyx\.ollama\models`.
   ```powershell
   ollama pull qwen2.5:3b
   ollama pull neural-chat
   ollama pull llama3.2:1b
   ```
   (~7,3 GB total de descarga.)

4. **WSL2 + distro Ubuntu + Redis.** WSL instala en la unidad de sistema.
   ```powershell
   wsl --install -d Ubuntu
   ```
   Adentro de la distro: instalar `redis-server` y habilitarlo:
   ```bash
   sudo apt update && sudo apt install redis-server
   sudo systemctl enable redis-server
   ```

5. **`%USERPROFILE%\.wslconfig`.** Vive en el perfil de Windows, no en el
   repo. Recrear con:
   ```ini
   [wsl2]
   memory=1GB
   ```
   (el tope que evita que WSL2 se coma media RAM en una máquina de 8GB —
   ver PROGRESS.md, sección de mitigación de memoria del 2026-09-20).

6. **`OLLAMA_KEEP_ALIVE=-1`.** Variable de usuario de Windows (`setx`), no
   del repo.
   ```powershell
   setx OLLAMA_KEEP_ALIVE -1
   ```
   Después hace falta reiniciar Ollama (o la PC) para que tome efecto.

### 2.2 Para que Voice funcione bien

7. **Drivers de GPU**, si la PC nueva tiene NVIDIA. **Ojo:** la GPU de la
   PC vieja (RTX 3070) resultó no acelerar nada (medido: ~5-6 tok/s con
   `num_gpu:0` forzado, prácticamente igual que con GPU — ver PROGRESS.md,
   "HALLAZGO CRÍTICO — la GPU no acelera nada y crasheó bajo carga") y
   crasheó bajo carga real. No asumir que una GPU nueva "simplemente
   funciona" — medir el throughput real (con y sin `num_gpu:0`) antes de
   confiar en ella para nada.

8. **Permisos de micrófono en Windows** — "Permitir que las apps accedan
   al micrófono". Por dispositivo, no viaja con el disco.

9. **Mejoras de audio de Windows desactivadas** para el micrófono real —
   Panel de Sonido → Grabación → dispositivo → Propiedades → Mejoras de
   audio. El fix real del 2026-09-13 (ver PROGRESS.md, "Resolución final")
   es específico del dispositivo/driver de audio de la PC vieja —
   revisarlo de nuevo en la nueva, puede tener otro nombre de mejora o
   estar en otro lado según el driver.

### 2.3 Si se usan (verificar si aplica)

10. **Tarea de Task Scheduler** — re-registrar con
    `scripts\register-aries-task.ps1` desde la PC nueva. No reusar ni
    copiar nada de la vieja (ver nota de la sección 1).

11. **Git, `gh` CLI, Claude Code** — herramientas de desarrollo estándar,
    se asume que ya están o se van a instalar igual.

## 3. Qué SÍ viaja con el disco (para no preocuparse de más)

- Todo el código y la configuración versionada (todo lo que está en git).
- `.env` — con la API key y la ruta de Piper ya corregida a relativa.
- Los modelos custom entrenados (`tools/wake_word_training/output/*.onnx`).
- Las voces de Piper descargadas (`piper_voices/`, `es_MX-claude-high.onnx`
  en la raíz del repo).
- El dataset de grabaciones (`tools/wake_word_training/dataset/`).
- La base SQLite de memoria (`aries_memory.db`).
- Los logs (`logs/`) y el estado del supervisor (`.aries/`), si importa
  conservar el historial.
