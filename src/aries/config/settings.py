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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Devuelve la configuración como diccionario con datos seguros ocultados."""
        config = super().dict(*args, **kwargs)
        config["secret_key"] = "****"
        return config
