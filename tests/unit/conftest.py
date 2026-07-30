"""Fixtures compartidas para tests/unit/ — hoy solo las de Voice.

Descargan modelos reales (Piper, faster-whisper, openWakeWord) una sola
vez por sesión de test y los cachean en `tests/.cache/` (gitignored) para
no volver a bajarlos en cada corrida. Ningún test de Voice mockea estos
modelos — la única excepción autorizada a "no mockear" en todo el
proyecto es el hardware de audio en sí (`MicrophoneListener`/
`SpeakerPlayer`, ver `tests/unit/test_voice_pipeline.py`), no las
librerías de IA.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CACHE_DIR = Path(__file__).parent.parent / ".cache"
PIPER_VOICES_DIR = CACHE_DIR / "piper_voices"
WHISPER_MODELS_DIR = CACHE_DIR / "whisper_models"

SPANISH_VOICE = "es_ES-carlfm-x_low"
ENGLISH_VOICE = "en_US-lessac-low"  # para generar "hey jarvis" real en tests de wake word


def _download_piper_voice(name: str) -> tuple[Path, Path]:
    from piper.download_voices import download_voice

    model_path = PIPER_VOICES_DIR / f"{name}.onnx"
    config_path = PIPER_VOICES_DIR / f"{name}.onnx.json"
    if not model_path.exists() or not config_path.exists():
        PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        download_voice(name, PIPER_VOICES_DIR)
    return model_path, config_path


@pytest.fixture(scope="session")
def piper_voice_es_paths() -> tuple[Path, Path]:
    """Voz en español más liviana disponible — usada como voz default de
    `PiperProvider` en los tests."""
    return _download_piper_voice(SPANISH_VOICE)


@pytest.fixture(scope="session")
def piper_voice_en_paths() -> tuple[Path, Path]:
    """Voz en inglés — usada solo para sintetizar "hey jarvis" real y
    probar detección de wake word sin depender de un archivo de audio
    grabado a mano."""
    return _download_piper_voice(ENGLISH_VOICE)


@pytest.fixture(scope="session")
def whisper_tiny_model():
    """`WhisperModel` real, tamaño 'tiny' (el más chico) para que los
    tests corran rápido — la precisión de 'tiny' no es representativa de
    producción (`voice_stt_model_size` default es 'small'), pero alcanza
    para confirmar que el pipeline funciona de punta a punta."""
    from faster_whisper import WhisperModel

    WHISPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return WhisperModel("tiny", device="cpu", compute_type="int8", download_root=str(WHISPER_MODELS_DIR))


@pytest.fixture(scope="session")
def whisper_small_model():
    """`WhisperModel` real, tamaño 'small' — el default de producción
    (`voice_stt_model_size`). Usado solo donde la precisión de 'tiny' no
    alcanza (ej. transcribir una sola palabra corta y crítica como la
    frase de confirmación) — verificado empíricamente: 'tiny' transcribió
    "confirmo" (sintetizado con Piper) como "Confirme.", 'base' como
    "Confirma.", y recién 'small' como "Confirmo." correctamente."""
    from faster_whisper import WhisperModel

    WHISPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return WhisperModel("small", device="cpu", compute_type="int8", download_root=str(WHISPER_MODELS_DIR))


@pytest.fixture(scope="session")
def openwakeword_models_ready() -> None:
    """Descarga (una sola vez) los modelos pre-entrenados de openWakeWord,
    incluida su wake word default del proyecto (`hey_jarvis`)."""
    from openwakeword.utils import download_models

    download_models(["hey_jarvis"])
