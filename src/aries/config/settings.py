"""Definición de la configuración de la aplicación usando Pydantic."""

from __future__ import annotations

from typing import Any

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración de Aries OS cargada desde variables de entorno y .env."""

    app_name: str = Field("aries-os", description="Nombre de la aplicación")
    environment: str = Field("development", description="Entorno de despliegue")
    debug: bool = Field(True, description="Activa modo debug")
    log_level: str = Field("DEBUG", description="Nivel de logging")
    database_url: str = Field("postgresql://user:password@localhost:5432/aries", description="URL de la base de datos")
    database_echo: bool = Field(False, description="Habilita el eco de SQLAlchemy")
    redis_url: str = Field("redis://localhost:6379/0", description="URL de Redis")
    llm_provider: str = Field("ollama", description="Proveedor LLM")
    llm_model: str = Field("neural-chat", description="Modelo LLM")
    llm_base_url: HttpUrl = Field(HttpUrl("http://localhost:11434"), description="URL base del proveedor LLM")
    intent_llm_max_tokens: int = Field(
        512,
        description="Techo de tokens (num_predict de Ollama) para la llamada del Planner que interpreta"
        " la intención del usuario como JSON. Hallazgo del supervisor (2026-09-25): sin techo, un modelo"
        " que no emite su token de parada (visto con neural-chat, se inventó una conversación entera de"
        " 4 turnos en vez de responder JSON) cuelga hasta el timeout completo del cliente HTTP (~30s) en"
        " vez de fallar en un par de segundos con salida truncada.",
    )
    llm_request_timeout_seconds: float = Field(
        90.0,
        description="Timeout del cliente HTTP de OllamaProvider hacia Ollama. Medido 2026-09-25 con"
        " qwen2.5:3b (Invoke-WebRequest real, no Measure-Command): carga en frío ~65s, generación en"
        " caliente ~7 tokens/s. 30s (el default anterior) garantiza fallo en cualquier camino frío. OJO:"
        " a ~7 tok/s, el techo de intent_llm_max_tokens (512) sumado a una carga en frío puede superar"
        " estos 90s si el modelo llega a generar el máximo — este valor cubre el caso típico (carga fría"
        " + una respuesta razonable), no el peor caso combinado; OLLAMA_KEEP_ALIVE=-1 + la precarga en"
        " start-aries.ps1 son la mitigación real de la carga fría, este timeout es el resguardo residual.",
    )
    voice_enabled: bool = Field(True, description="Activa el soporte de voz")
    api_host: str = Field(
        "127.0.0.1",
        description="Host de la API. Default loopback-only (auditoría de seguridad 2026-09-23,"
        " docs/audits/2026-09-23-security-audit.md): POST /message no tiene autenticación todavía"
        " (pendiente de diseño), así que escuchar en 0.0.0.0 exponía ejecución de comandos/acceso a"
        " archivos sin login a cualquier dispositivo en la red. Exponerlo en red es opt-in explícito"
        " (setear esta variable), no el default.",
    )
    api_port: int = Field(8000, description="Puerto de la API")
    secret_key: SecretStr = Field(SecretStr("change-me-in-production"), description="Clave secreta para la aplicación")
    api_key: SecretStr = Field(
        SecretStr(""),
        description="Clave requerida (header X-API-Key) para POST /message y POST /message/confirm —"
        " GET /health queda siempre sin autenticar (start-aries.ps1 depende de poder consultarlo sin"
        " configuración previa). Vacío = el servidor RECHAZA todos los pedidos a esos dos endpoints"
        " (falla cerrado, no hay default inseguro tipo 'change-me-in-production' que nadie cambia) —"
        " ver docs/audits/2026-09-23-security-audit.md, hallazgo CRÍTICO #1.",
    )
    filesystem_allowed_root: str = Field(
        "",
        description="Raíz permitida (path absoluto) para FileSystemAgent/DatabaseAgent. Vacío = sin"
        " raíz configurada, esos dos agentes fallan cerrado en cualquier acción de archivo/DB en vez"
        " de operar sobre cualquier ruta del disco — ver docs/audits/2026-09-23-security-audit.md,"
        " hallazgo ALTO #3. Se valida con Path.resolve() + is_relative_to(), nunca comparación de texto.",
    )
    kernel_housekeeping_interval_seconds: float = Field(
        60.0, description="Intervalo en segundos entre ciclos de housekeeping del Kernel (ej. limpieza de memoria expirada)"
    )
    pending_confirmation_ttl_seconds: float = Field(
        120.0,
        description="TTL en Redis de una acción pendiente de confirmación (Planner.confirm) — pasado este"
        " tiempo sin confirmar, confirmation_id deja de ser válido. Auditoría de seguridad 2026-09-23,"
        " hallazgo CRÍTICO #1.",
    )
    plugins_dir: str = Field(
        "installed_plugins",
        description="Directorio (relativo al directorio de trabajo, o absoluto) donde Kernel.initialize() busca plugins válidos para cargar. Si no existe al arrancar, no se cargan plugins — no es un error",
    )
    voice_wake_word_model: str = Field(
        "hey_jarvis",
        description="Nombre del modelo pre-entrenado de wake word (openWakeWord) a usar por defecto — no existe todavía un modelo 'Aries' propio",
    )
    voice_wake_word_threshold: float = Field(
        0.5, description="Score mínimo (0-1) para considerar detectada una wake word"
    )
    voice_hotkey_enabled: bool = Field(
        True,
        description="Activa push-to-talk (hotkey global, además de la wake word). No cuenta para la"
        " condición 3 del contador de la Fase 1 (docs/VISION.md) — esa exige manos libres.",
    )
    voice_hotkey_combo: str = Field(
        "ctrl+alt+shift+v",
        description="Combinación de teclas para push-to-talk (ej. 'ctrl+alt+shift+v') — ver"
        " aries.voice.hotkey_listener.parse_hotkey_combo. Elegida rara a propósito para no pisar"
        " atajos de Windows/VSCode/otras apps; cambiar acá si colisiona con algo en tu máquina.",
    )
    voice_stt_model_size: str = Field(
        "small", description="Tamaño del modelo de faster-whisper a cargar (tiny/base/small/medium/large-v3)"
    )
    voice_tts_model_path: str = Field(
        "", description="Ruta al archivo .onnx del modelo de voz de Piper. Vacío = PiperProvider no se puede construir hasta configurarlo (el modelo no se descarga automáticamente)"
    )
    voice_tts_config_path: str = Field(
        "", description="Ruta al .onnx.json de configuración de la voz de Piper. Vacío = se infiere '<voice_tts_model_path>.json'"
    )
    voice_api_base_url: str = Field(
        "http://127.0.0.1:8000",
        description="URL base de la API (POST /message) que el pipeline de Voice consume como cliente HTTP — ver docs/specs/Voice.spec.md, decisión 2",
    )
    voice_api_request_timeout_seconds: float = Field(
        90.0,
        description="Timeout del cliente HTTP de VoicePipeline hacia POST /message — capa distinta pero"
        " mismo motivo que llm_request_timeout_seconds (OllamaProvider): si Voice corta a los 30s "
        " mientras la API todavía espera a Ollama con un timeout más generoso, una rutina disparada tras"
        " horas sin uso (el caso que motiva todo esto, docs/specs/Routines.spec.md) sigue fallando en frío"
        " aunque el timeout de Ollama ya esté arreglado — hallazgo propio al implementar el pedido del"
        " supervisor (2026-09-25), no fue parte del pedido original.",
    )
    voice_audio_device: str = Field(
        "",
        description="Dispositivo de entrada de audio a usar (índice numérico, nombre, o 'nombre, hostapi' tal como los "
        "acepta sounddevice/PortAudio). Vacío = autodetección: MicrophoneListener prefiere el dispositivo de entrada "
        "default de la hostapi WASAPI en vez del default 'crudo' del sistema, que en Windows suele resolver al backend "
        "MME — ver PROGRESS.md, sección 'Validación de VoicePipeline con hardware real': MME devolvió audio casi "
        "silencioso para un micrófono que funcionaba bien por WASAPI. Setear esta variable si la autodetección elige "
        "el dispositivo equivocado.",
    )
    memory_db_path: str = Field(
        "aries_memory.db",
        description="Ruta del archivo SQLite (relativa al directorio de trabajo, o absoluta) usado por SQLiteMemoryStore, el backend persistente de IMemory. Distinto de database_url (Postgres, sin uso todavía) — este es específicamente el store de Memory",
    )
    routines_dir: str = Field(
        "routines",
        description="Directorio (relativo al directorio de trabajo, o absoluto) donde Kernel.initialize() busca archivos de rutina válidos (uno por archivo .json) para cargar. Si no existe al arrancar, no se cargan rutinas — no es un error, mismo criterio que plugins_dir. Ver docs/specs/Routines.spec.md sección 3",
    )
    routines_check_interval_seconds: float = Field(
        30.0,
        description="Intervalo en segundos entre evaluaciones de RoutineManager.check_due() dentro del tick de Kernel.run() — separado de kernel_housekeeping_interval_seconds para que una rutina programada a horario fijo no se retrase hasta el próximo ciclo de housekeeping general. Ver docs/specs/Routines.spec.md sección 5",
    )
    routines_max_staleness_seconds: float = Field(
        1800.0,
        description="Máxima antigüedad (en segundos) que puede tener una ocurrencia de rutina vencida antes de descartarse en vez de ejecutarse tarde — evaluada tanto al publicar (RoutineManager.check_due()) como al consumir (VoicePipeline, vía el valid_until que viaja en el payload). Ver docs/specs/MessageBus.spec.md secciones 3 y 6.1",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Devuelve la configuración como diccionario con datos seguros ocultados."""
        config = super().dict(*args, **kwargs)
        config["secret_key"] = "****"
        return config
