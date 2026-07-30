"""Pruebas unitarias para brain/generate_response."""

from __future__ import annotations

import pytest

from aries.brain import generate_response
from aries.contracts.llm import ILLMProvider, LLMResponse


class FakeLLMProvider(ILLMProvider):
    def __init__(self, content: str | None = None, raises: bool = False) -> None:
        self.content = content
        self.raises = raises
        self.prompts: list[str] = []

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        if self.raises:
            raise RuntimeError("LLM no disponible")
        return LLMResponse(content=self.content or "", model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_returns_llm_content_on_success(self) -> None:
        llm = FakeLLMProvider(content="Listo, se hizo lo que pediste.")

        result = await generate_response(llm, "hace algo", True, ["Acción completada."])

        assert result == "Listo, se hizo lo que pediste."

    @pytest.mark.asyncio
    async def test_prompt_includes_user_input_and_step_summaries(self) -> None:
        llm = FakeLLMProvider(content="ok")

        await generate_response(llm, "borrame el archivo x", True, ["Archivo eliminado: x"])

        assert "borrame el archivo x" in llm.prompts[0]
        assert "Archivo eliminado: x" in llm.prompts[0]

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception_success_case(self) -> None:
        llm = FakeLLMProvider(raises=True)

        result = await generate_response(llm, "algo", True, [])

        assert result == "Listo, se completó la acción solicitada."

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception_failure_case(self) -> None:
        llm = FakeLLMProvider(raises=True)

        result = await generate_response(llm, "algo", False, [])

        assert result == "No se pudo completar la acción solicitada."

    @pytest.mark.asyncio
    async def test_fallback_when_llm_returns_empty_content(self) -> None:
        llm = FakeLLMProvider(content="   ")

        result = await generate_response(llm, "algo", True, [])

        assert result == "Listo, se completó la acción solicitada."

    @pytest.mark.asyncio
    async def test_never_propagates_exception(self) -> None:
        llm = FakeLLMProvider(raises=True)

        # No debe lanzar, pase lo que pase.
        result = await generate_response(llm, "algo", False, ["paso 1"])

        assert isinstance(result, str)
