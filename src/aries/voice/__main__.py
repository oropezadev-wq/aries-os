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

    audio_device: int | str | None = settings.voice_audio_device or None
    if isinstance(audio_device, str) and audio_device.strip().lstrip("-").isdigit():
        audio_device = int(audio_device.strip())

    return VoicePipeline(
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        listener=MicrophoneListener(device=audio_device),
        player=SpeakerPlayer(),
        config=config,
    )


async def main() -> None:
    settings = Settings()
    if not settings.voice_enabled:
        LOGGER.warning("voice_enabled está en False, no se arranca el pipeline de voz")
        return

    # Versión de onnxruntime logueada siempre al arrancar — un bug real ya
    # nos costó tiempo de diagnóstico porque nadie registró qué versión
    # estaba activa durante una corrida (ver PROGRESS.md, "Validación de
    # VoicePipeline con hardware real": onnxruntime==1.28.0 da scores de
    # wake word pegados en ~0.000001 sin importar el audio; 1.17.3/1.20.0
    # no tienen ese problema). Sin este log, cualquier corrida futura deja
    # la misma duda sin forma de resolverla después de los hechos.
    try:
        import onnxruntime

        LOGGER.info("Versión de onnxruntime activa", version=onnxruntime.__version__)
    except ImportError:
        LOGGER.warning("No se pudo importar onnxruntime para loguear su versión")

    pipeline = _build_pipeline(settings)
    await pipeline.run_forever()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
