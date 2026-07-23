"""Implementación en memoria del contrato IMemory."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from structlog import BoundLogger

from ..contracts.memory import IMemory, MemoryItem
from ..logging import get_logger


class InMemoryStore(IMemory):
    """Almacén de memoria en memoria pura compatible con IMemory."""

    def __init__(self) -> None:
        self._store: dict[str, MemoryItem] = {}
        self._lock = asyncio.Lock()
        self.logger: BoundLogger = get_logger(self.__class__.__name__)

    async def store(
        self,
        content: str,
        memory_type: str,
        metadata: Optional[dict] = None,
        importance: int = 1,
    ) -> MemoryItem:
        if not isinstance(content, str):
            raise TypeError("El contenido debe ser una cadena")
        if not isinstance(memory_type, str):
            raise TypeError("El tipo de memoria debe ser una cadena")
        if not isinstance(importance, int):
            raise TypeError("La importancia debe ser un entero")
        if importance < 1 or importance > 10:
            raise ValueError("La importancia debe estar entre 1 y 10")

        memory_id = str(uuid.uuid4())
        item = MemoryItem(
            id=memory_id,
            type=memory_type,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now(),
            updated_at=datetime.now(),
            importance=importance,
        )

        async with self._lock:
            self._store[memory_id] = item
            self.logger.info(
                "Elemento de memoria almacenado",
                memory_id=memory_id,
                type=memory_type,
            )

        return item

    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        if not isinstance(memory_id, str):
            raise TypeError("El ID de memoria debe ser una cadena")

        async with self._lock:
            item = self._store.get(memory_id)
            if item is None:
                self.logger.warning(
                    "Elemento de memoria no encontrado",
                    memory_id=memory_id,
                )
            return item

    async def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryItem]:
        if not isinstance(query, str):
            raise TypeError("La consulta debe ser una cadena")
        if memory_type is not None and not isinstance(memory_type, str):
            raise TypeError("El tipo de memoria debe ser una cadena o None")
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("El límite debe ser un entero positivo")

        results: list[MemoryItem] = []
        async with self._lock:
            for item in self._store.values():
                if memory_type and item.type != memory_type:
                    continue
                if query in item.content:
                    results.append(item)
                    if len(results) >= limit:
                        break

        # TODO: En fases futuras, conectar aquí la búsqueda semántica con embeddings/vectores.
        return results

    async def delete(self, memory_id: str) -> bool:
        if not isinstance(memory_id, str):
            raise TypeError("El ID de memoria debe ser una cadena")

        async with self._lock:
            if memory_id not in self._store:
                self.logger.warning(
                    "Solicitud de eliminación para un ID de memoria desconocido",
                    memory_id=memory_id,
                )
                return False
            del self._store[memory_id]
            self.logger.info("Elemento de memoria eliminado", memory_id=memory_id)
            return True

    async def clear_expired(self) -> int:
        async with self._lock:
            # No hay política de expiración definida en MemoryItem actualmente.
            self.logger.debug(
                "clear_expired invocado pero no hay política de expiración definida"
            )
            return 0

    async def get_by_type(self, memory_type: str) -> list[MemoryItem]:
        if not isinstance(memory_type, str):
            raise TypeError("El tipo de memoria debe ser una cadena")

        results: list[MemoryItem] = []
        async with self._lock:
            for item in self._store.values():
                if item.type == memory_type:
                    results.append(item)
        return results
