"""voice/faster_whisper_provider.py — implementación default de
`ISTTProvider` usando `faster-whisper` (ver
`docs/contracts/ISTTProvider.md`).
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Optional

from ..contracts.stt import ISTTProvider, STTResult
from ..exceptions import VoiceError
from ..logging import get_logger


class FasterWhisperProvider(ISTTProvider):
    """Transcribe audio usando `faster-whisper`.

    `faster_whisper` se importa de forma diferida (dentro de `__init__`)
    — dependencia pesada opcional (extra `voice`).
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Optional[str] = None,
        model: Optional[Any] = None,
    ) -> None:
        self.model_size = model_size
        self.logger = get_logger(self.__class__.__name__)

        if model is not None:
            # Inyección de un `WhisperModel` ya cargado — solo para tests,
            # para no pagar el costo de cargar el mismo modelo dos veces
            # (ver tests/unit/test_voice_providers.py). El uso normal
            # siempre carga su propio modelo, abajo.
            self._model = model
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise VoiceError(
                "faster-whisper no está instalado — instalar el extra 'voice' del proyecto"
            ) from error

        try:
            self._model = WhisperModel(
                model_size, device=device, compute_type=compute_type, download_root=download_root
            )
        except Exception as error:
            raise VoiceError(f"No se pudo cargar el modelo faster-whisper '{model_size}': {error}") from error

    async def transcribe(
        self, audio: bytes, language: Optional[str] = None, **kwargs: Any
    ) -> STTResult:
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            raise VoiceError("El audio a transcribir no puede estar vacío")

        try:
            segments, info = await asyncio.to_thread(self._transcribe_sync, bytes(audio), language)
        except VoiceError:
            raise
        except Exception as error:
            self.logger.error("Error al transcribir audio", error=str(error))
            raise VoiceError(f"Error al transcribir audio: {error}") from error

        text = " ".join(segment.text.strip() for segment in segments).strip()
        return STTResult(text=text, language=info.language, confidence=info.language_probability)

    def _transcribe_sync(self, audio: bytes, language: Optional[str]) -> tuple[list[Any], Any]:
        # `vad_filter=True`: Silero VAD embebido en faster-whisper (ONNX,
        # sin dependencia de `torch`) — ver decisión 4/6 de
        # docs/specs/Voice.spec.md.
        segments, info = self._model.transcribe(io.BytesIO(audio), language=language, vad_filter=True)
        return list(segments), info

    async def is_available(self) -> bool:
        return self._model is not None

    def get_model_name(self) -> str:
        return f"faster-whisper-{self.model_size}"
