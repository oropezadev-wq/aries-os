"""Contrato: Plugin (extensión del sistema)

Los plugins agregan nuevas capacidades sin modificar el kernel.
Deben ser independientes e instalables en runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PluginMetadata:
    """Metadatos de un plugin."""
    name: str
    version: str
    author: str
    description: str
    requires: list[str] = field(default_factory=list)
    entry_point: str = ""


@dataclass
class PluginHooks:
    """Hooks que registra un plugin."""
    event_type: str
    handler: Callable[..., Any]


class IPlugin(ABC):
    """Interface para plugins.

    Responsabilidades:
    - Definir metadatos
    - Inicializarse
    - Registrar hooks/capacidades
    - Limpiarse al descargar
    """

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Retorna metadatos del plugin.

        Returns:
            PluginMetadata con información del plugin
        """
        ...

    @abstractmethod
    async def initialize(self, context: dict[str, Any]) -> bool:
        """Inicializar el plugin.

        Args:
            context: Contexto del kernel contiene:
                - logger: Instance de logger
                - event_bus: Bus de eventos
                - di_container: Contenedor de inyección
                - settings: Configuración

        Returns:
            True si inicializó exitosamente, False en error
        """
        ...

    @abstractmethod
    async def shutdown(self) -> bool:
        """Limpiar recursos del plugin.

        Se ejecuta cuando se descarga el plugin.
        Limpiar: threads, conexiones, archivos abiertos.

        Returns:
            True si limpió exitosamente
        """
        ...

    @abstractmethod
    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        """Registrar hooks que el plugin maneja.

        Returns:
            Dict mapping event_type → handler_function
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """Listar nuevas capacidades que agrega el plugin.

        Estas capacidades se registran en el sistema.

        Returns:
            Lista de nombres de capacidades/acciones
        """
        ...

    @abstractmethod
    def is_compatible(self, kernel_version: str) -> bool:
        """Validar compatibilidad con versión del kernel.

        Args:
            kernel_version: Versión actual del kernel (ej: "0.1.0")

        Returns:
            True si es compatible
        """
        ...
