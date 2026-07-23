"""Contrato: Proveedor de LLM (Modelo de Lenguaje)

Define cómo comunicarse con proveedores de IA sin dependencias específicas.
Soporta: Ollama, OpenAI, Claude, Gemini, LM Studio, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """Respuesta de un proveedor LLM."""
    content: str
    model: str
    tokens_used: Optional[int] = None
    stop_reason: Optional[str] = None


class ILLMProvider(ABC):
    """Interface para proveedores de LLM.

    Responsabilidades:
    - Generar texto desde prompts
    - Generar embeddings (vectores)
    - Validar disponibilidad
    - Manejar timeouts y errores
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """Generar completación de texto.

        Args:
            prompt: Texto a procesar
            temperature: Creatividad (0-1, default 0.7)
            max_tokens: Límite de tokens generados

        Returns:
            LLMResponse con el texto generado

        Raises:
            TimeoutError: Si se agota el tiempo
        """
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generar embedding (vector) de texto.

        Args:
            text: Texto a vectorizar

        Returns:
            Lista de floats representando el vector
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Verificar de forma asíncrona si el proveedor puede operar.

        Debe validar conectividad y estado mínimo del proveedor.

        Returns:
            True si está disponible; False en caso de error o timeout
        """
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Obtener nombre del modelo actual."""
        ...
