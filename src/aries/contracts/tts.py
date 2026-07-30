"""Contrato: Proveedor de TTS (Text-to-Speech)

Define cómo convertir texto a audio sin acoplar el resto del sistema a un
motor específico — ver `docs/contracts/ITTSProvider.md`. Diseñado a
propósito para aceptar proveedores de pago/nube más adelante (ej.
ElevenLabs) sin romper al pipeline, mismo intercambio que `ILLMProvider`
ya permite entre Ollama y proveedores cloud.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TTSResult:
    """Resultado de una síntesis de voz."""

    audio: bytes
    sample_rate: int
    voice: str


class ITTSProvider(ABC):
    """Interface para proveedores de síntesis de voz (TTS)."""

    @abstractmethod
    async def synthesize(
        self, text: str, voice: Optional[str] = None, **kwargs: Any
    ) -> TTSResult:
        """Sintetiza texto a audio.

        Args:
            text: texto a sintetizar.
            voice: nombre/id de voz específico del proveedor, o `None`
                para la voz default configurada.

        Returns:
            TTSResult con audio WAV completo (con header) — ver
            `docs/contracts/ITTSProvider.md` para el formato exacto.

        Raises:
            VoiceError: error del proveedor (texto vacío, voz inexistente, etc.).
            TimeoutError: se agotó el tiempo de síntesis.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Verifica que el modelo/voz estén listos para sintetizar."""
        ...

    @abstractmethod
    def get_voice_name(self) -> str:
        """Nombre de la voz default configurada."""
        ...
