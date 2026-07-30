"""Contrato: Proveedor de STT (Speech-to-Text)

Define cómo transcribir audio a texto sin acoplar el resto del sistema a
un motor específico — ver `docs/contracts/ISTTProvider.md`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class STTResult:
    """Resultado de una transcripción."""

    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None


class ISTTProvider(ABC):
    """Interface para proveedores de reconocimiento de voz (STT)."""

    @abstractmethod
    async def transcribe(
        self, audio: bytes, language: Optional[str] = None, **kwargs: Any
    ) -> STTResult:
        """Transcribe audio a texto.

        Args:
            audio: WAV completo (con header), mono, 16kHz, PCM 16-bit —
                ver `docs/contracts/ISTTProvider.md` para el porqué del
                formato (verificado empíricamente: PCM sin header falla).
            language: código ISO 639-1, o `None` para autodetección.

        Returns:
            STTResult con el texto transcripto.

        Raises:
            VoiceError: error del proveedor.
            TimeoutError: se agotó el tiempo de transcripción.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Verifica que el modelo esté cargado y listo."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Nombre/tamaño del modelo cargado."""
        ...
