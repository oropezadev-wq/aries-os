"""Pruebas reales (SQLite en disco, sin mocks) de `SQLiteMemoryStore`.

Foco principal: persistencia real a través de reinicios — una instancia
nueva de `SQLiteMemoryStore` apuntando al mismo archivo debe ver los
mismos datos que guardó una instancia anterior, ya destruida (simula
apagar y volver a prender `python -m aries`). También se cubre el
contrato `IMemory` estándar, para confirmar paridad razonable de
comportamiento con `InMemoryStore` (`tests/unit/test_in_memory_store.py`).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aries.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "memory.db"


class TestPersistenceAcrossRestart:
    @pytest.mark.asyncio
    async def test_stored_item_survives_new_instance_same_file(self, db_path: Path) -> None:
        store1 = SQLiteMemoryStore(db_path)
        item = await store1.store(
            "hola persistente", "context", metadata={"session_id": "abc"}, importance=5
        )
        store1.close()

        # "Reinicio": instancia completamente nueva contra el mismo archivo
        # — nada comparte estado en memoria con `store1`, solo el archivo.
        store2 = SQLiteMemoryStore(db_path)
        recovered = await store2.retrieve(item.id)
        store2.close()

        assert recovered is not None
        assert recovered.id == item.id
        assert recovered.content == "hola persistente"
        assert recovered.metadata == {"session_id": "abc"}
        assert recovered.importance == 5
        assert isinstance(recovered.created_at, datetime)
        assert recovered.expires_at is None

    @pytest.mark.asyncio
    async def test_get_by_type_survives_restart(self, db_path: Path) -> None:
        store1 = SQLiteMemoryStore(db_path)
        await store1.store("a", "conversation")
        await store1.store("b", "conversation")
        await store1.store("c", "preference")
        store1.close()

        store2 = SQLiteMemoryStore(db_path)
        items = await store2.get_by_type("conversation")
        store2.close()

        assert {item.content for item in items} == {"a", "b"}

    @pytest.mark.asyncio
    async def test_search_survives_restart(self, db_path: Path) -> None:
        store1 = SQLiteMemoryStore(db_path)
        await store1.store("el archivo importante", "context")
        await store1.store("otra cosa sin relación", "context")
        store1.close()

        store2 = SQLiteMemoryStore(db_path)
        results = await store2.search("archivo")
        store2.close()

        assert len(results) == 1
        assert results[0].content == "el archivo importante"

    @pytest.mark.asyncio
    async def test_delete_persists_across_restart(self, db_path: Path) -> None:
        store1 = SQLiteMemoryStore(db_path)
        item = await store1.store("a borrar", "context")
        deleted = await store1.delete(item.id)
        store1.close()
        assert deleted is True

        store2 = SQLiteMemoryStore(db_path)
        recovered = await store2.retrieve(item.id)
        store2.close()

        assert recovered is None

    @pytest.mark.asyncio
    async def test_clear_expired_persists_across_restart(self, db_path: Path) -> None:
        store1 = SQLiteMemoryStore(db_path)
        expired = await store1.store(
            "viejo", "context", expires_at=datetime.now() - timedelta(seconds=1)
        )
        fresh = await store1.store("nuevo", "context")
        removed = await store1.clear_expired()
        store1.close()
        assert removed == 1

        store2 = SQLiteMemoryStore(db_path)
        assert await store2.retrieve(expired.id) is None
        assert await store2.retrieve(fresh.id) is not None
        store2.close()

    @pytest.mark.asyncio
    async def test_creates_parent_directories_if_missing(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "nested" / "dir" / "memory.db"
        store = SQLiteMemoryStore(nested_path)
        await store.store("x", "context")
        store.close()

        assert nested_path.exists()


class TestContractBehavior:
    """Comportamiento del contrato IMemory en sí — no específico de
    persistencia, pero debe funcionar igual que en `InMemoryStore`."""

    @pytest.mark.asyncio
    async def test_store_validates_importance_range(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        with pytest.raises(ValueError):
            await store.store("x", "context", importance=11)
        store.close()

    @pytest.mark.asyncio
    async def test_store_rejects_non_string_content(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        with pytest.raises(TypeError):
            await store.store(123, "context")  # type: ignore[arg-type]
        store.close()

    @pytest.mark.asyncio
    async def test_retrieve_unknown_id_returns_none(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        result = await store.retrieve("no-existe")
        store.close()
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_unknown_id_returns_false(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        result = await store.delete("no-existe")
        store.close()
        assert result is False

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        for i in range(5):
            await store.store(f"archivo {i}", "context")
        results = await store.search("archivo", limit=2)
        store.close()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_is_case_sensitive_substring_like_in_memory_store(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        await store.store("Archivo Importante", "context")
        results_exact = await store.search("Archivo")
        results_wrong_case = await store.search("archivo")
        store.close()
        assert len(results_exact) == 1
        assert len(results_wrong_case) == 0

    @pytest.mark.asyncio
    async def test_metadata_dict_round_trips_through_json_column(self, db_path: Path) -> None:
        store = SQLiteMemoryStore(db_path)
        item = await store.store("x", "context", metadata={"nested": {"a": 1}, "list": [1, 2, 3]})
        recovered = await store.retrieve(item.id)
        store.close()
        assert recovered is not None
        assert recovered.metadata == {"nested": {"a": 1}, "list": [1, 2, 3]}

    def test_empty_db_path_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            SQLiteMemoryStore("")
