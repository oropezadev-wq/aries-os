"""Punto de entrada para correr el pipeline de Voice como proceso
standalone (decisión 2 de `docs/specs/Voice.spec.md`) — cliente HTTP de
`POST /message`, no un endpoint nuevo ni parte de `Kernel.run()`.

Requiere el extra `voice` instalado (`pip install aries-os[voice]`) y un
modelo de voz de Piper ya descargado en disco
(`python -m piper.download_voices <nombre-de-voz>`,
`settings.voice_tts_model_path` apuntando ahí) — ninguno de los dos se
hace automáticamente.
"""

from __future__ import annotations

import asyncio

from ..config.settings import Settings
from ..logging import get_logger
from .audio_io import MicrophoneListener, SpeakerPlayer
from .faster_whisper_provider import FasterWhisperProvider
from .openwakeword_provider import OpenWakeWordProvider
from .pipeline import VoicePipeline, VoicePipelineConfig
from .piper_provider import PiperProvider

LOGGER = get_logger("aries.voice.__main__")


def _build_pipeline(settings: Settings) -> VoicePipeline:
    if not settings.voice_tts_model_path:
        raise SystemExit(
            "settings.voice_tts_model_path no está configurado — descargar una voz de "
            "Piper (`python -m piper.download_voices <nombre>`) y apuntar la variable de "
            "entorno VOICE_TTS_MODEL_PATH al archivo .onnx resultante."
        )

    wake_word = OpenWakeWordProvider(
        wakeword_models=[settings.voice_wake_word_model],
        threshold=settings.voice_wake_word_threshold,
    )
    stt = FasterWhisperProvider(model_size=settings.voice_stt_model_size)
    tts = PiperProvider(
        model_path=settings.voice_tts_model_path,
        config_path=settings.voice_tts_config_path or None,
    )
    config = VoicePipelineConfig(api_base_url=settings.voice_api_base_url)

    return VoicePipeline(
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        listener=MicrophoneListener(),
        player=SpeakerPlayer(),
        config=config,
    )


async def main() -> None:
    settings = Settings()
    if not settings.voice_enabled:
        LOGGER.warning("voice_enabled está en False, no se arranca el pipeline de voz")
        return

    pipeline = _build_pipeline(settings)
    await pipeline.run_forever()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
