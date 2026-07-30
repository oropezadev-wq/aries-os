"""voice/piper_provider.py — implementación default de `ITTSProvider`
usando `piper-tts` (ver `docs/contracts/ITTSProvider.md`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from ..contracts.tts import ITTSProvider, TTSResult
from ..exceptions import VoiceError
from ..logging import get_logger
from .audio_io import pcm_to_wav_bytes


class PiperProvider(ITTSProvider):
    """Sintetiza audio usando `piper` (paquete `piper-tts`).

    `piper` se importa de forma diferida (dentro de `__init__`) —
    dependencia pesada opcional (extra `voice`). Requiere un modelo de voz
    ya descargado en disco (`.onnx` + `.onnx.json`) — no se descarga
    automáticamente (ver `python -m piper.download_voices`).
    """

    def __init__(
        self,
        model_path: str | Path,
        config_path: Optional[str | Path] = None,
        voice_name: Optional[str] = None,
    ) -> None:
        try:
            from piper import PiperVoice
        except ImportError as error:
            raise VoiceError(
                "piper-tts no está instalado — instalar el extra 'voice' del proyecto"
            ) from error

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise VoiceError(f"No existe el modelo de voz de Piper: {self.model_path}")

        self._voice_name = voice_name or self.model_path.stem
        self.logger = get_logger(self.__class__.__name__)

        try:
            self._voice = PiperVoice.load(
                str(self.model_path),
                config_path=str(config_path) if config_path else None,
            )
        except Exception as error:
            raise VoiceError(f"No se pudo cargar la voz de Piper '{self.model_path}': {error}") from error

    async def synthesize(
        self, text: str, voice: Optional[str] = None, **kwargs: Any
    ) -> TTSResult:
        if not isinstance(text, str) or not text.strip():
            raise VoiceError("El texto a sintetizar no puede estar vacío")

        try:
            wav_bytes, sample_rate = await asyncio.to_thread(self._synthesize_sync, text, kwargs)
        except VoiceError:
            raise
        except Exception as error:
            self.logger.error("Error al sintetizar audio", error=str(error))
            raise VoiceError(f"Error al sintetizar audio: {error}") from error

        return TTSResult(audio=wav_bytes, sample_rate=sample_rate, voice=voice or self._voice_name)

    def _synthesize_sync(self, text: str, synthesis_kwargs: dict[str, Any]) -> tuple[bytes, int]:
        # `**kwargs` del contrato (`ITTSProvider.synthesize`) se reenvía tal
        # cual a `piper.config.SynthesisConfig` — ej. `noise_scale=0.0,
        # noise_w_scale=0.0` para síntesis determinística (Piper es
        # estocástico por default: dos llamadas con el mismo texto NO
        # producen el mismo audio — verificado empíricamente). Sin kwargs,
        # se usa el comportamiento default de Piper (voz más natural).
        syn_config = None
        if synthesis_kwargs:
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(**synthesis_kwargs)

        chunks = list(self._voice.synthesize(text, syn_config=syn_config))
        if not chunks:
            raise VoiceError("Piper no generó ningún audio para el texto dado")

        pcm = b"".join(chunk.audio_int16_bytes for chunk in chunks)
        sample_rate = chunks[0].sample_rate
        return pcm_to_wav_bytes(pcm, sample_rate=sample_rate, channels=chunks[0].sample_channels), sample_rate

    async def is_available(self) -> bool:
        return self._voice is not None

    def get_voice_name(self) -> str:
        return self._voice_name
