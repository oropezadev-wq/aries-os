"""Contrato: Herramienta del sistema.

Las herramientas son acciones específicas que el planner puede ejecutar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolMetadata:
    """Metadatos de una herramienta."""
    name: str
    version: str
    description: str
    category: str
    requires_authorization: bool
    entry_point: str = ""
    requires: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Resultado de la ejecución de una herramienta."""
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class ITool(ABC):
    """Interface para herramientas del sistema.

    Responsabilidades:
    - Exponer acciones específicas
    - Ejecutar operaciones concretas
    - Reportar resultados estructurados
    - Validar disponibilidad
    - Declarar autorización por acción
    """

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Retorna información de la herramienta.

        Debe incluir:
        - name
        - description
        - version
        - category
        - requires_authorization
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Ejecuta la herramienta.

        Returns:
            Dict con:
              - success: bool
              - result: Resultado específico
              - error: Mensaje de error si hubo fallo
              - execution_time_ms: Tiempo de ejecución
        """
        ...

    @abstractmethod
    def get_actions(self) -> list[str]:
        """Lista acciones específicas que la herramienta proporciona.

        Ejemplo:
            ["read", "write", "delete", "list_directory", "create_directory"]
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Valida que la herramienta puede ejecutarse.

        Verifica:
        - Recursos disponibles
        - Conectividad (si aplica)
        - Servicios dependientes
        """
        ...

    @abstractmethod
    def requires_confirmation(self, action: str) -> bool:
        """Verifica si una acción es peligrosa y requiere confirmación.

        Mismo nombre de método que `IAgent.requires_confirmation` — unificado
        el 2026-07-25 (ver `docs/specs/Planner.spec.md`, decisión 4) para que
        el Planner no tenga que normalizar dos nombres distintos para el
        mismo concepto. Antes se llamaba `requires_authorization`.

        Retorna True para: delete, format, uninstall, shutdown, etc.
        """
        ...

    @abstractmethod
    def get_tool_name(self) -> str:
        """Identificador único de la herramienta.

        Ejemplo: "file-system", "email-sender", "web-scraper"
        """
        ...
