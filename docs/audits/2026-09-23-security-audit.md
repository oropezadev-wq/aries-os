# Auditoría de seguridad — Aries OS

Fecha: 2026-09-23
Alcance: análisis de solo lectura (subagente `security`, tools Read/Grep/Glob)
sobre `src/`, `tools/`, `scripts/`, configuración y `.env`; más un escaneo de
CVEs de dependencias de terceros (`pip-audit`, backend OSV, corrido por el
Tech Lead en un venv aparte, sin instalar nada en el entorno del proyecto).
Pedido explícito del usuario. No se modificó ningún archivo durante la
auditoría en sí — las correcciones de este documento se hicieron después,
en commits separados, ya con la re-priorización del usuario/supervisor.

Antecedente revisado: `docs/audits/2026-07-24-diagnostico.md` y
`2026-07-24-pre-commit-review.md` son diagnósticos de completitud/
arquitectura, no auditorías de seguridad — sin superposición real con lo de
abajo. Dato que sí cruza: el diagnóstico de julio marcó `plugins/` como "0%
implementado"; hoy ya tiene código real (`loader.py`, `installer.py`,
`manifest.py`, `registry.py`, `agent_adapter.py`), revisado acá.

---

## Dependencias de terceros (pip-audit, backend OSV)

**156 paquetes escaneados, 0 con vulnerabilidades conocidas.** (Un primer
intento contra el backend PyPI falló por un 503 transitorio en un paquete
puntual; el reintento contra OSV.dev completó limpio.)

---

## Hallazgos, con la re-priorización del usuario/supervisor (2026-09-23)

### CRÍTICO — 1. `POST /message` sin autenticación, bind de red abierto, confirmación controlada por el cliente

**Archivos:** `src/aries/api.py:301-322`, `src/aries/config/settings.py`,
`src/aries/voice/pipeline.py`.

`POST /message` es el único punto de entrada de usuario y no tenía ningún
`Depends(...)` de auth, API key, ni CORS/TrustedHost middleware.
`Settings.secret_key` existe pero no se usa en ningún lado. El texto libre
llega al `Planner` → LLM local arma un plan → `AgentManager.dispatch()` lo
ejecuta contra 4 agentes reales (`ProcessAgent`, `FileSystemAgent`,
`DatabaseAgent`, `GitAgent`), sin sandbox. El único freno
(`requires_confirmation()`) es una heurística de texto que el propio campo
`confirmed: bool` del request puede saltarse sin que medie ningún humano
real — el servidor confía ciegamente en lo que le manda el cliente.

**Explotación concreta (antes del fix de bind):** cualquier dispositivo en
la misma red podía mandar `POST /message` con
`{"user_input": "borra todos los archivos de ...", "confirmed": true}` y,
si el LLM armaba el plan, se ejecutaba con los privilegios del usuario —
sin login, sin token, sin rate limit.

**Disposición (2026-09-23):**

- ✅ **Paso 1, hecho (commit `5f10b1a`):** `api_host` default cambiado de
  `0.0.0.0` a `127.0.0.1` — exponer el API en red pasa a ser opt-in
  explícito, no el default. Verificado que no rompe `start-aries.ps1`
  (su chequeo de salud ya apuntaba a `127.0.0.1:8000` en duro) ni
  `voice_api_base_url` (VoicePipeline ya llamaba a `127.0.0.1:8000`).
- ⏸️ **Pendiente, decisión de diseño no trivial (no implementado
  todavía):** autenticación real de `POST /message` (API key), con dos
  cuidados explícitos del usuario: VoicePipeline necesita poder seguir
  llamando al endpoint con la key, y `GET /health` tiene que quedar
  **sin** autenticar (si no, el gate de arranque de `start-aries.ps1`
  se rompe en el próximo reinicio, porque valida `/health` antes de
  considerar el proceso arriba).
- ⏸️ **Pendiente, decisión de diseño no trivial (no implementado
  todavía):** la confirmación de acciones destructivas. El arreglo
  correcto que pidió el supervisor **no** es mover el `confirmed: bool`
  a otro endpoint — es que el servidor nunca acepte una confirmación que
  venga afirmada por el cliente sin verificación propia. Diseño: el
  servidor devuelve una acción pendiente con un id (no una acción ya
  autorizada), y la confirmación real llega respetando la misma regla
  que ya existe para voz (`CONFIRMATION_PHRASE = "confirmo"`,
  `src/aries/voice/pipeline.py`) — HTTP tiene que respetar esa misma
  regla en vez de un booleano de confianza ciega. Ver sección
  "Decisiones de diseño pendientes" más abajo para el detalle de las
  preguntas abiertas.

### ALTO — 2. `ProcessAgent` sin whitelist de ejecutables

**Archivo:** `src/aries/agents/process/agent.py`.

La inyección de shell está bien resuelta (`shell=False`, argv explícito,
sin interpolación de string). El problema es la ausencia total de control
de acceso sobre *qué* se puede ejecutar — `_looks_destructive()` está
documentada en el propio código como "NO un control de seguridad real".

**Disposición (2026-09-23):** no se implementa todavía. Queda como
**bloqueante explícito** antes de sumar el agente de browsing planeado en
`docs/VISION.md` — ahí es donde deja de ser un riesgo teórico (acotado por
la falta de auth del hallazgo #1) y pasa a ser directamente explotable (un
LLM eligiendo qué ejecutar con contenido web no confiable de por medio).
Anotado en `docs/VISION.md`, sección "Etapa siguiente dentro de la Fase 1".

### ALTO — 3. `FileSystemAgent`/`DatabaseAgent` sin restricción de rutas

**Archivos:** `src/aries/agents/filesystem/agent.py:129+`,
`src/aries/agents/database/agent.py:203-207`.

Ningún agente valida que `path`/`db_path`/`repo_path` estén dentro de un
directorio permitido — path traversal / acceso a cualquier archivo o
`.db` del disco.

**Disposición (2026-09-23):** mecanismo de arreglo confirmado y validado
hoy mismo (no implementado todavía — decisión de diseño pendiente sobre
la raíz permitida, ver más abajo): `Path.resolve()` + `is_relative_to()`
contra una raíz configurable, **no** comparación de strings. Se probó en
esta máquina (Windows) antes de proponerlo:

- Nombres 8.3 (`C:\PROGRA~1`) se resuelven correctamente a la forma larga
  canónica (`C:\Program Files`) — sin necesitar código extra.
- Mayúsculas/minúsculas: `Path.resolve()` normaliza para comparación de
  igualdad en Windows (`C:\Users\orphalyx` == `c:\users\ORPHALYX`).
- Rutas UNC (`\\localhost\C$\Windows`): `is_relative_to()` contra una raíz
  con letra de unidad (`C:\...`) da `False` de forma estructural (ancla
  distinta), incluso cuando la ruta UNC apunta al mismo contenido físico
  vía un share administrativo — **falla cerrado**, no es una vía de
  bypass. Contrapartida (no es un problema de seguridad, sí de
  usabilidad): si la raíz permitida se configura como ruta UNC, una
  petición con ruta de letra de unidad al mismo contenido se rechazaría
  igual — hay que ser consistente en cómo se expresa la raíz.
- Trampa de prefijo de texto (`C:\Users\orphalyx` vs.
  `C:\Users\orphalyxEvil`): `is_relative_to()` la rechaza correctamente
  (compara componentes de ruta, no substring) — confirma que la
  recomendación del supervisor (no comparar strings) es la correcta.

### MEDIO — 4. `.env` con una línea placeholder sin reemplazar

Correctamente gitignoreado, sin secretos reales — higiene, no fuga.
**Disposición:** sin acción (no la pidió nadie, no es de seguridad).

### MEDIO — 5. Historial de conversación en SQLite sin cifrado en reposo

**Archivo:** `src/aries/memory/sqlite_store.py`.

**Disposición (2026-09-23), decisión explícita del usuario: no se hace
nada.** En una máquina personal de un solo usuario, el cifrado de disco
del sistema operativo ya cubre este caso — agregar cifrado a nivel de
aplicación (SQLCipher u otro) sería una capa redundante sin un atacante
realista nuevo que la justifique en este contexto. Revisar si esto deja
de ser así el día que Aries maneje datos de más de un usuario o corra en
una máquina que el usuario no controla físicamente (ninguno de los dos es
el caso hoy, y no está planeado en `docs/VISION.md` Fase 1).

### BAJO — 6. Dependencias sin techo de versión en `pyproject.toml`

**Disposición (2026-09-23): subido de BAJO a prioridad alta, ya hecho
(commit `861384a`).** El usuario lo marcó como "el mismo tipo de bug que
ya nos costó semanas" (referencia directa al incidente de
`onnxruntime==1.28.0` roto en Windows, ver `pyproject.toml`). Se agregó
techo `<siguiente_major` a las ~40 dependencias que no lo tenían.
Hallazgo de paso, no corregido (fuera de alcance de "agregar techo"):
`mkdocs-material>=10.0` parece un piso roto (última versión publicada
9.7.7 — el rango nunca fue satisfacible, probable typo por "9.0"),
flageado en un comentario, no corregido sin que se pida explícitamente.

### BAJO — 7. Sin rate limiting en el API

**Disposición (2026-09-23): se queda en BAJO, sin implementar, pero con
el motivo real corregido.** No es (solo) un riesgo de seguridad
abstracto — ya tuvimos un incidente concreto de auto-DoS: el 2026-09-20,
67 falsos disparos de wake word en una mañana generaron 53 llamadas a
Ollama y coincidieron con 2 de las 3 caídas del equipo ese día (ver
`PROGRESS.md`, "Diagnóstico de Voice del 2026-09-20" — correlación, no
causa demostrada, pero el patrón de carga es real y ya ocurrió sin que
mediara ningún atacante). El motivo para eventualmente implementarlo es
**estabilidad del propio sistema bajo carga inesperada**, no únicamente
contener a un tercero malicioso.

---

## Categorías sin hallazgos

Secretos hardcodeados, inyección de shell, deserialización insegura e
inyección SQL — ninguno encontrado. Detalle de la verificación empírica
de cada uno en el reporte original del subagente (no repetido acá; ver
historial de la sesión si hace falta el detalle línea por línea).

---

## Decisiones de diseño pendientes (no implementadas — frenado antes de escribir código, a pedido del usuario)

Tres piezas quedan sin resolver porque son decisiones de arquitectura, no
ejecución mecánica. Ver el resto de la conversación de esta sesión para
las preguntas concretas planteadas al usuario sobre cada una:

1. **API key en `POST /message`** — dónde vive la key, cómo la obtiene
   VoicePipeline, `GET /health` excluido.
2. **Confirmación de acciones destructivas server-side** — acción
   pendiente con id + la misma regla de frase de voz ya existente,
   aplicada también a HTTP, en vez de un `confirmed: bool` de confianza
   ciega.
3. **Raíz permitida por defecto para `FileSystemAgent`/`DatabaseAgent`**
   — el mecanismo (`resolve()` + `is_relative_to()`) ya está validado
   (ver hallazgo ALTO #3); falta decidir el valor de la raíz por
   defecto (o si no hay default y hay que configurarla explícitamente).
