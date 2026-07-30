"""Implementación persistente del contrato IMemory usando SQLite vía
SQLAlchemy Core (no ORM) — mismo patrón ya establecido por
`agents/database/agent.py` (SQLAlchemy Core, sin ORM, sin agregar
dependencias nuevas: `sqlalchemy>=2.0` ya está en `pyproject.toml`).

Alcance deliberado: **solo SQLite, un único archivo fijado en el
constructor** (a diferencia de `DatabaseAgent`, que recibe `db_path` por
llamada porque es un agente genérico contra bases arbitrarias) — acá el
motor se crea una sola vez en `__init__` y vive lo que vive el objeto,
igual que `InMemoryStore` mantiene su `dict` en memoria durante toda su
vida: es un store de un solo propósito, no un ejecutor SQL genérico.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text
from structlog.stdlib import BoundLogger

from ..contracts.memory import IMemory, MemoryItem
from ..logging import get_logger


class SQLiteMemoryStore(IMemory):
    """Almacén de memoria persistente en un archivo SQLite.

    Sobrevive a reinicios del proceso: dos instancias apuntando al mismo
    `db_path` (ej. una antes de apagar, otra después de volver a arrancar)
    ven los mismos datos — es justamente lo que `InMemoryStore` no puede
    ofrecer (su `dict` vive y muere con el proceso).
    """

    def __init__(self, db_path: str | Path) -> None:
        if not isinstance(db_path, (str, Path)) or not str(db_path).strip():
            raise ValueError("db_path no puede estar vacío")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger: BoundLogger = get_logger(self.__class__.__name__)

        self._engine = sa.create_engine(f"sqlite:///{self.db_path}")
        self._metadata_obj = MetaData()
        self._table = Table(
            "memory_items",
            self._metadata_obj,
            Column("id", String, primary_key=True),
            Column("type", String, nullable=False),
            Column("content", Text, nullable=False),
            Column("metadata", JSON, nullable=False, default=dict),
            Column("created_at", DateTime, nullable=False),
            Column("updated_at", DateTime, nullable=False),
            Column("importance", Integer, nullable=False),
            Column("expires_at", DateTime, nullable=True),
        )
        self._metadata_obj.create_all(self._engine)

    def close(self) -> None:
        """Libera el engine/conexiones de SQLAlchemy — no forma parte del
        contrato `IMemory` (no hay nada que cerrar en `InMemoryStore`),
        pero hace falta acá: en Windows, el archivo `.db` queda bloqueado
        mientras el engine siga vivo (relevante sobre todo para tests con
        `tmp_path`, que intentan borrar el directorio temporal después)."""
        self._engine.dispose()

    # ------------------------------------------------------------------
    # IMemory
    # ------------------------------------------------------------------

    async def store(
        self,
        content: str,
        memory_type: str,
        metadata: Optional[dict] = None,
        importance: int = 1,
        expires_at: Optional[datetime] = None,
    ) -> MemoryItem:
        if not isinstance(content, str):
            raise TypeError("El contenido debe ser una cadena")
        if not isinstance(memory_type, str):
            raise TypeError("El tipo de memoria debe ser una cadena")
        if not isinstance(importance, int):
            raise TypeError("La importancia debe ser un entero")
        if importance < 1 or importance > 10:
            raise ValueError("La importancia debe estar entre 1 y 10")
        if expires_at is not None and not isinstance(expires_at, datetime):
            raise TypeError("expires_at debe ser un datetime o None")

        item = MemoryItem(
            id=str(uuid.uuid4()),
            type=memory_type,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now(),
            updated_at=datetime.now(),
            importance=importance,
            expires_at=expires_at,
        )

        await asyncio.to_thread(self._store_sync, item)
        self.logger.info("Elemento de memoria almacenado", memory_id=item.id, type=memory_type)
        return item

    def _store_sync(self, item: MemoryItem) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._table.insert().values(
                    id=item.id,
                    type=item.type,
                    content=item.content,
                    metadata=item.metadata,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    importance=item.importance,
                    expires_at=item.expires_at,
                )
            )

    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        if not isinstance(memory_id, str):
            raise TypeError("El ID de memoria debe ser una cadena")

        item = await asyncio.to_thread(self._retrieve_sync, memory_id)
        if item is None:
            self.logger.warning("Elemento de memoria no encontrado", memory_id=memory_id)
        return item

    def _retrieve_sync(self, memory_id: str) -> Optional[MemoryItem]:
        stmt = sa.select(self._table).where(self._table.c.id == memory_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._row_to_item(row) if row is not None else None

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

        return await asyncio.to_thread(self._search_sync, query, memory_type, limit)

    def _search_sync(self, query: str, memory_type: Optional[str], limit: int) -> list[MemoryItem]:
        # El filtro de subcadena (`query in item.content`) se hace en
        # Python, no con `LIKE`/`GLOB` de SQL, a propósito: `LIKE` en
        # SQLite es case-insensitive por default para ASCII y `GLOB`
        # necesita escapar `*`/`?`/`[`/`]` del texto buscado — cualquiera
        # de los dos cambiaría el comportamiento respecto a `InMemoryStore`
        # (`query in item.content`, substring literal, case-sensitive).
        # El filtro por `type` sí se empuja a SQL, es una igualdad simple
        # sin ninguna de esas trampas. Orden determinístico por
        # `created_at` para que el resultado no dependa del orden físico
        # de las filas en el archivo.
        stmt = sa.select(self._table).order_by(self._table.c.created_at)
        if memory_type:
            stmt = stmt.where(self._table.c.type == memory_type)

        results: list[MemoryItem] = []
        with self._engine.connect() as conn:
            for row in conn.execute(stmt).mappings():
                if query in row["content"]:
                    results.append(self._row_to_item(row))
                    if len(results) >= limit:
                        break
        return results

    async def delete(self, memory_id: str) -> bool:
        if not isinstance(memory_id, str):
            raise TypeError("El ID de memoria debe ser una cadena")

        deleted = await asyncio.to_thread(self._delete_sync, memory_id)
        if deleted:
            self.logger.info("Elemento de memoria eliminado", memory_id=memory_id)
        else:
            self.logger.warning(
                "Solicitud de eliminación para un ID de memoria desconocido", memory_id=memory_id
            )
        return deleted

    def _delete_sync(self, memory_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(self._table.delete().where(self._table.c.id == memory_id))
            return result.rowcount > 0

    async def clear_expired(self) -> int:
        count = await asyncio.to_thread(self._clear_expired_sync)
        if count:
            self.logger.info("Elementos de memoria vencidos eliminados", count=count)
        return count

    def _clear_expired_sync(self) -> int:
        now = datetime.now()
        stmt = self._table.delete().where(
            sa.and_(self._table.c.expires_at.isnot(None), self._table.c.expires_at <= now)
        )
        with self._engine.begin() as conn:
            result = conn.execute(stmt)
            return result.rowcount

    async def get_by_type(self, memory_type: str) -> list[MemoryItem]:
        if not isinstance(memory_type, str):
            raise TypeError("El tipo de memoria debe ser una cadena")

        return await asyncio.to_thread(self._get_by_type_sync, memory_type)

    def _get_by_type_sync(self, memory_type: str) -> list[MemoryItem]:
        stmt = (
            sa.select(self._table)
            .where(self._table.c.type == memory_type)
            .order_by(self._table.c.created_at)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: Any) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            type=row["type"],
            content=row["content"],
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            importance=row["importance"],
            expires_at=row["expires_at"],
        )
