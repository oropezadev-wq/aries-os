"""Contrato: Agente (ejecutor de acciones)

Un agente puede ejecutar acciones en sistemas específicos.
Ejemplos: Windows, Docker, Git, Email, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ActionStatus(str, Enum):
    """Estados de ejecución de acciones."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ActionResult:
    """Resultado de ejecutar una acción."""
    status: ActionStatus
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    execution_time_ms: float = 0.0


class IAgent(ABC):
    """Interface para agentes ejecutores.

    Responsabilidades:
    - Ejecutar acciones en sistemas específicos
    - Reportar estado y progreso
    - Manejar errores gracefully
    - Validar permisos
    """

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> ActionResult:
        """Ejecutar una acción.

        Args:
            action: Nombre de la acción (ej: "open_file", "run_command")
            **kwargs: Parámetros específicos de la acción

        Returns:
            ActionResult con estado y resultado

        Raises:
            PermissionError: Si falta permiso
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """Listar acciones que puede ejecutar.

        Returns:
            Lista de nombres de acciones disponibles
        """
        ...

    @abstractmethod
    def requires_confirmation(self, action: str) -> bool:
        """Verifica si una acción requiere confirmación.

        Acciones peligrosas (eliminar, modificar) regresan True.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Verifica que el agente puede funcionar.

        Ej: Windows agent verifica SO, Docker agent verifica daemon.
        """
        ...

    @abstractmethod
    def get_agent_name(self) -> str:
        """Nombre único del agente."""
        ...
