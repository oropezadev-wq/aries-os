"""Proveedor Ollama para ILLMProvider.

Usa la API HTTP de Ollama con httpx.AsyncClient y expone un cleanup explícito.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config.settings import Settings
from ..contracts.llm import ILLMProvider, LLMResponse
from ..exceptions import LLMError
from ..logging import get_logger


class OllamaProvider(ILLMProvider):
    """Proveedor Ollama que implementa ILLMProvider."""

    def __init__(
        self,
        settings: Settings,
        timeout: float = 30.0,
    ) -> None:
        self.settings = settings
        self.timeout = timeout
        self.base_url = str(settings.llm_base_url).rstrip("/")
        self.model = settings.llm_model
        self.logger = get_logger(self.__class__.__name__)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout))

    async def close(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaProvider":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if not isinstance(prompt, str):
            raise TypeError("El prompt debe ser una cadena")

        options: dict[str, Any] = {"temperature": temperature}
        options.update(kwargs)

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        self.logger.info("Enviando solicitud de completado a Ollama", model=self.model)

        try:
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.error("Error de red en complete()", error=str(exc))
            raise LLMError("Error al llamar a Ollama para completar texto.") from exc

        data = response.json()
        content = data.get("response", "")
        eval_count = data.get("eval_count")
        prompt_eval_count = data.get("prompt_eval_count")
        tokens_used = None
        if isinstance(eval_count, int) and isinstance(prompt_eval_count, int):
            tokens_used = eval_count + prompt_eval_count
        elif isinstance(eval_count, int):
            tokens_used = eval_count
        elif isinstance(prompt_eval_count, int):
            tokens_used = prompt_eval_count

        self.logger.info(
            "Completado recibido de Ollama",
            model=self.model,
            tokens_used=tokens_used,
        )

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_used=tokens_used,
        )

    async def embed(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("El texto debe ser una cadena")

        self.logger.info("Enviando solicitud de embedding a Ollama", model=self.model)

        try:
            response = await self._client.post("/api/embed", json={"model": self.model, "input": text})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.error("Error de red en embed()", error=str(exc))
            raise LLMError("Error al llamar a Ollama para generar embeddings.") from exc

        data = response.json()
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
            self.logger.error("Respuesta inválida de embeddings de Ollama", payload=data)
            raise LLMError("Respuesta inválida de Ollama al generar embeddings.")

        vector = embeddings[0]
        self.logger.info(
            "Embedding generado por Ollama",
            model=self.model,
            dimension=len(vector),
        )
        return [float(value) for value in vector]

    async def is_available(self) -> bool:
        self.logger.info("Verificando disponibilidad de Ollama")

        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            self.logger.debug("Ollama disponible según /api/tags")
            return True
        except httpx.HTTPError as exc:
            self.logger.warning("Ollama no disponible", error=str(exc))
            return False

    def get_model_name(self) -> str:
        return self.model
