"""Pruebas unitarias para InMemoryStore."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from aries.memory.in_memory import InMemoryStore
from aries.config.settings import Settings


@pytest.mark.asyncio
async def test_store_and_retrieve_memory_item() -> None:
    store = InMemoryStore()

    item = await store.store("hola mundo", "conversation", {"lang": "es"}, importance=5)

    assert item.id is not None
    assert item.type == "conversation"
    assert item.content == "hola mundo"

    retrieved = await store.retrieve(item.id)
    assert retrieved is not None
    assert retrieved.id == item.id


@pytest.mark.asyncio
async def test_retrieve_missing_returns_none() -> None:
    store = InMemoryStore()

    result = await store.retrieve("non-existent-id")
    assert result is None


@pytest.mark.asyncio
async def test_search_items_by_query_and_type() -> None:
    store = InMemoryStore()
    await store.store("hello world", "conversation")
    await store.store("another world", "conversation")
    await store.store("hello again", "note")

    results = await store.search("hello", memory_type="conversation", limit=10)
    assert len(results) == 1
    assert results[0].content == "hello world"


@pytest.mark.asyncio
async def test_search_no_results() -> None:
    store = InMemoryStore()
    await store.store("hello world", "conversation")

    results = await store.search("missing", limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_delete_existing_and_missing() -> None:
    store = InMemoryStore()
    item = await store.store("hola", "conversation")

    deleted = await store.delete(item.id)
    assert deleted is True
    assert await store.retrieve(item.id) is None

    deleted_missing = await store.delete("non-existent-id")
    assert deleted_missing is False


@pytest.mark.asyncio
async def test_get_by_type() -> None:
    store = InMemoryStore()
    await store.store("note 1", "note")
    await store.store("note 2", "note")
    await store.store("chat 1", "conversation")

    notes = await store.get_by_type("note")
    assert len(notes) == 2
    assert all(item.type == "note" for item in notes)


@pytest.mark.asyncio
async def test_clear_expired_returns_zero() -> None:
    store = InMemoryStore()
    await store.store("hola", "conversation")

    deleted = await store.clear_expired()
    assert deleted == 0


@pytest.mark.asyncio
async def test_importance_validation_raises_value_error() -> None:
    store = InMemoryStore()

    with pytest.raises(ValueError):
        await store.store("hola", "conversation", importance=0)

    with pytest.raises(ValueError):
        await store.store("hola", "conversation", importance=11)


@pytest.mark.asyncio
async def test_concurrent_access_is_safe() -> None:
    store = InMemoryStore()

    async def writer(content: str) -> None:
        await store.store(content, "conversation")

    tasks = [writer(f"message {i}") for i in range(20)]
    await asyncio.gather(*tasks)

    results = await store.search("message", limit=20)
    assert len(results) == 20


@pytest.mark.asyncio
async def test_store_without_expires_at_defaults_to_none() -> None:
    store = InMemoryStore()

    item = await store.store("hola", "conversation")

    assert item.expires_at is None


@pytest.mark.asyncio
async def test_store_rejects_non_datetime_expires_at() -> None:
    store = InMemoryStore()

    with pytest.raises(TypeError):
        await store.store("hola", "conversation", expires_at="not-a-datetime")


@pytest.mark.asyncio
async def test_clear_expired_removes_only_items_past_expiration() -> None:
    store = InMemoryStore()
    now = datetime.now()

    expired = await store.store(
        "vencido", "context", expires_at=now - timedelta(seconds=1)
    )
    fresh = await store.store(
        "vigente", "context", expires_at=now + timedelta(hours=1)
    )
    permanent = await store.store("sin vencimiento", "context")

    deleted = await store.clear_expired()

    assert deleted == 1
    assert await store.retrieve(expired.id) is None
    assert await store.retrieve(fresh.id) is not None
    assert await store.retrieve(permanent.id) is not None


@pytest.mark.asyncio
async def test_clear_expired_is_idempotent() -> None:
    store = InMemoryStore()
    await store.store(
        "vencido", "context", expires_at=datetime.now() - timedelta(seconds=1)
    )

    first_pass = await store.clear_expired()
    second_pass = await store.clear_expired()

    assert first_pass == 1
    assert second_pass == 0
