from __future__ import annotations


class AriesException(Exception):
    """Excepción base para errores generales de Aries OS."""


class ConfigError(AriesException):
    """Error de configuración o inicialización del entorno."""


class KernelError(AriesException):
    """Error en el ciclo de vida del kernel."""


class PluginError(AriesException):
    """Error en la carga o ejecución de plugins."""


class MemoryError(AriesException):
    """Error en el subsistema de memoria."""


class AgentError(AriesException):
    """Error en la gestión de agentes."""


class LLMError(AriesException):
    """Error en la integración con proveedores LLM."""


class VoiceError(AriesException):
    """Error en el subsistema de voz."""


__all__ = [
    "AriesException",
    "ConfigError",
    "KernelError",
    "PluginError",
    "MemoryError",
    "AgentError",
    "LLMError",
    "VoiceError",
]
