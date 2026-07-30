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
    voice_enabled: bool = Field(True, description="Activa el soporte de voz")
    api_host: str = Field("0.0.0.0", description="Host de la API")
    api_port: int = Field(8000, description="Puerto de la API")
    secret_key: SecretStr = Field(SecretStr("change-me-in-production"), description="Clave secreta para la aplicación")
    kernel_housekeeping_interval_seconds: float = Field(
        60.0, description="Intervalo en segundos entre ciclos de housekeeping del Kernel (ej. limpieza de memoria expirada)"
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
    memory_db_path: str = Field(
        "aries_memory.db",
        description="Ruta del archivo SQLite (relativa al directorio de trabajo, o absoluta) usado por SQLiteMemoryStore, el backend persistente de IMemory. Distinto de database_url (Postgres, sin uso todavía) — este es específicamente el store de Memory",
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
