"""Contrato: Sistema de Memoria

Define cómo almacenar y recuperar información.
Tipos: conversación, preferencias, perfil, documentos, aprendizaje.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class MemoryItem:
    """Elemento individual de memoria."""
    id: str
    type: str  # "conversation", "preference", "profile", "document", "learning"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    importance: int = 1  # 1-10
    expires_at: Optional[datetime] = None


class IMemory(ABC):
    """Interface para sistema de memoria.

    Responsabilidades:
    - Almacenar información
    - Recuperar información
    - Buscar información
    - Limpiar información expirada
    - Categorizar información
    """

    @abstractmethod
    async def store(
        self,
        content: str,
        memory_type: str,
        metadata: Optional[dict] = None,
        importance: int = 1,
        expires_at: Optional[datetime] = None,
    ) -> MemoryItem:
        """Almacenar información en memoria.

        Args:
            content: Información a guardar
            memory_type: Tipo ("conversation", "preference", etc)
            metadata: Datos adicionales
            importance: Nivel de importancia (1-10)
            expires_at: Momento en que el item deja de ser válido. `None`
                (por defecto) significa que el item no expira.

        Returns:
            MemoryItem creado
        """
        ...

    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        """Recuperar información por ID."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """Buscar información.

        Args:
            query: Términos a buscar
            memory_type: Filtrar por tipo (opcional)
            limit: Máximo de resultados

        Returns:
            Lista de MemoryItems coincidentes
        """
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Eliminar información."""
        ...

    @abstractmethod
    async def clear_expired(self) -> int:
        """Limpiar información expirada.

        Returns:
            Cantidad de items eliminados
        """
        ...

    @abstractmethod
    async def get_by_type(self, memory_type: str) -> list[MemoryItem]:
        """Obtener todos los items de un tipo."""
        ...
