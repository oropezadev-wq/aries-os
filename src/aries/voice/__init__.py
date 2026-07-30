"""Sistema de Voice de Aries OS — ver docs/specs/Voice.spec.md.

Proceso cliente standalone (decisión 2 del spec): consume `POST /message`
como cualquier otro cliente HTTP, sin cambios en `api.py`/`Planner`/
`Brain`/`Kernel`.
"""

from .audio_io import MicrophoneListener, SpeakerPlayer, pcm_to_wav_bytes, wav_bytes_to_pcm
from .faster_whisper_provider import FasterWhisperProvider
from .openwakeword_provider import OpenWakeWordProvider
from .pipeline import VoicePipeline, VoicePipelineConfig
from .piper_provider import PiperProvider

__all__ = [
    "FasterWhisperProvider",
    "MicrophoneListener",
    "OpenWakeWordProvider",
    "PiperProvider",
    "SpeakerPlayer",
    "VoicePipeline",
    "VoicePipelineConfig",
    "pcm_to_wav_bytes",
    "wav_bytes_to_pcm",
]
