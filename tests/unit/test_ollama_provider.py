"""Pruebas unitarias para OllamaProvider."""

from __future__ import annotations

import json

import httpx
import pytest

from aries.config.settings import Settings
from aries.exceptions import LLMError
from aries.llm.ollama_provider import OllamaProvider


@pytest.fixture
def settings() -> Settings:
    return Settings(llm_base_url="http://localhost:11434", llm_model="neural-chat")


@pytest.mark.asyncio
async def test_complete_success(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert request.url.path == "/api/generate"
        assert body["model"] == "neural-chat"
        assert body["prompt"] == "Hola"
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0.7

        return httpx.Response(
            200,
            json={"response": "Hola mundo", "eval_count": 10, "prompt_eval_count": 2},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    result = await provider.complete("Hola")

    assert result.content == "Hola mundo"
    assert result.model == "neural-chat"
    assert result.tokens_used == 12

    await client.aclose()


@pytest.mark.asyncio
async def test_complete_respects_num_predict(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert request.url.path == "/api/generate"
        assert body["options"]["num_predict"] == 50

        return httpx.Response(
            200,
            json={"response": "Hola mundo", "eval_count": 10, "prompt_eval_count": 2},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    result = await provider.complete("Hola", max_tokens=50)

    assert result.tokens_used == 12

    await client.aclose()


@pytest.mark.asyncio
async def test_complete_sends_format_at_top_level(settings: Settings) -> None:
    """`format` es un campo de nivel superior en la API de Ollama (junto a
    `model`/`prompt`/`options`), no una opción de sampling — verifica que
    no termine metido dentro de `options` junto con `temperature` (bug
    real encontrado 2026-09-25: `options.update(kwargs)` sin sacarlo
    primero lo mandaba mal ubicado, donde Ollama lo ignora en silencio)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["format"] == "json"
        assert "format" not in body["options"]

        return httpx.Response(
            200,
            json={"response": '{"ok": true}', "eval_count": 10, "prompt_eval_count": 2},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    result = await provider.complete("Hola", format="json")

    assert result.content == '{"ok": true}'

    await client.aclose()


@pytest.mark.asyncio
async def test_client_respects_configured_timeout(settings: Settings) -> None:
    """Hallazgo del supervisor (2026-09-25, medido con Invoke-WebRequest
    real): una carga en frío de Ollama tarda ~65s — el default anterior
    de 30s garantizaba fallo en cualquier camino frío. Sin este test, el
    valor pasado por `api.py` (`settings.llm_request_timeout_seconds`)
    podría quedar sin usarse y nadie lo notaría hasta production."""
    provider = OllamaProvider(settings, timeout=90.0)

    assert provider._client.timeout.read == 90.0

    await provider.close()


@pytest.mark.asyncio
async def test_embed_success(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert request.url.path == "/api/embed"
        assert body["model"] == "neural-chat"
        assert body["input"] == "hola"

        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    embedding = await provider.embed("hola")

    assert embedding == [0.1, 0.2, 0.3]

    await client.aclose()


@pytest.mark.asyncio
async def test_is_available_returns_true(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    assert await provider.is_available() is True

    await client.aclose()


@pytest.mark.asyncio
async def test_is_available_returns_false_on_error(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    assert await provider.is_available() is False

    await client.aclose()


@pytest.mark.asyncio
async def test_complete_raises_llm_error_on_http_exception(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    with pytest.raises(LLMError):
        await provider.complete("Hola")

    await client.aclose()


@pytest.mark.asyncio
async def test_embed_raises_llm_error_on_http_exception(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://localhost:11434", transport=transport)
    provider = OllamaProvider(settings)
    provider._client = client

    with pytest.raises(LLMError):
        await provider.embed("hola")

    await client.aclose()
