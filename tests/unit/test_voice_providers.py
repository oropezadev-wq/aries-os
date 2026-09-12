"""Pruebas reales (sin mocks) de los 3 proveedores de Voice:
`OpenWakeWordProvider`, `FasterWhisperProvider`, `PiperProvider`.

Nada mockeado: modelos ONNX/ctranslate2 reales, cargados de verdad,
corriendo inferencia real sobre audio real (generado con Piper mismo, o
silencio real). La única excepción a "no mockear" en todo el proyecto de
Voice es el hardware de audio en sí (micrófono/parlante) — ver
`test_voice_pipeline.py` — no las librerías de IA, que corren completas
acá.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aries.contracts.stt import STTResult
from aries.contracts.tts import TTSResult
from aries.contracts.wake_word import WakeWordDetection
from aries.exceptions import VoiceError
from aries.voice.faster_whisper_provider import FasterWhisperProvider
from aries.voice.openwakeword_provider import OpenWakeWordProvider
from aries.voice.piper_provider import PiperProvider


class TestPiperProvider:
    @pytest.mark.asyncio
    async def test_synthesize_returns_real_wav_audio(self, piper_voice_es_paths: tuple[Path, Path]) -> None:
        model_path, config_path = piper_voice_es_paths
        tts = PiperProvider(model_path=model_path, config_path=config_path)

        result = await tts.synthesize("Hola, esto es una prueba.")

        assert isinstance(result, TTSResult)
        assert result.audio[:4] == b"RIFF"
        assert result.sample_rate > 0
        assert result.voice == model_path.stem

    @pytest.mark.asyncio
    async def test_synthesize_empty_text_raises_voice_error(self, piper_voice_es_paths: tuple[Path, Path]) -> None:
        model_path, config_path = piper_voice_es_paths
        tts = PiperProvider(model_path=model_path, config_path=config_path)

        with pytest.raises(VoiceError):
            await tts.synthesize("   ")

    def test_missing_model_path_raises_voice_error(self, tmp_path: Path) -> None:
        with pytest.raises(VoiceError):
            PiperProvider(model_path=tmp_path / "no_existe.onnx")

    @pytest.mark.asyncio
    async def test_is_available_and_voice_name(self, piper_voice_es_paths: tuple[Path, Path]) -> None:
        model_path, config_path = piper_voice_es_paths
        tts = PiperProvider(model_path=model_path, config_path=config_path, voice_name="mi-voz")

        assert await tts.is_available() is True
        assert tts.get_voice_name() == "mi-voz"


class TestFasterWhisperProvider:
    @pytest.mark.asyncio
    async def test_transcribe_round_trip_with_real_piper_audio(
        self, piper_voice_es_paths: tuple[Path, Path], whisper_tiny_model
    ) -> None:
        """Round-trip real: Piper sintetiza una frase conocida, Whisper la
        transcribe — sin mocks en ninguno de los dos lados."""
        model_path, config_path = piper_voice_es_paths
        tts = PiperProvider(model_path=model_path, config_path=config_path)
        synthesized = await tts.synthesize("hola mundo, abrí el archivo por favor")

        stt = FasterWhisperProvider(model_size="tiny", model=whisper_tiny_model)

        result = await stt.transcribe(synthesized.audio, language="es")

        assert isinstance(result, STTResult)
        text_lower = result.text.lower()
        assert "archivo" in text_lower
        assert "favor" in text_lower
        assert result.language == "es"

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio_raises_voice_error(self, whisper_tiny_model) -> None:
        stt = FasterWhisperProvider(model_size="tiny", model=whisper_tiny_model)

        with pytest.raises(VoiceError):
            await stt.transcribe(b"")

    def test_get_model_name(self, whisper_tiny_model) -> None:
        stt = FasterWhisperProvider(model_size="tiny", model=whisper_tiny_model)

        assert stt.get_model_name() == "faster-whisper-tiny"


class TestOpenWakeWordProvider:
    @pytest.mark.asyncio
    async def test_detects_real_wake_word_from_synthesized_audio(
        self, piper_voice_en_paths: tuple[Path, Path], openwakeword_models_ready: None
    ) -> None:
        """Detección real: Piper sintetiza "hey jarvis" en inglés,
        openWakeWord corre inferencia ONNX real sobre esos frames — sin
        mocks en ninguno de los dos lados."""
        model_path, config_path = piper_voice_en_paths
        tts = PiperProvider(model_path=model_path, config_path=config_path)
        synthesized = await tts.synthesize("hey jarvis, hey jarvis, hey jarvis")

        from aries.voice.audio_io import wav_bytes_to_pcm

        pcm, sample_rate, _channels, _width = wav_bytes_to_pcm(synthesized.audio)
        assert sample_rate == 16000  # openWakeWord espera 16kHz
        audio = np.frombuffer(pcm, dtype=np.int16)

        wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"], threshold=0.5)
        frame_size = wake_word.frame_size()

        detections: list[WakeWordDetection] = []
        for start in range(0, len(audio) - frame_size, frame_size):
            frame = audio[start : start + frame_size]
            detections.extend(wake_word.process_frame(frame))

        assert any(d.name == "hey_jarvis" for d in detections)
        assert all(d.score is not None and d.score >= 0.5 for d in detections)

    def test_does_not_detect_on_silence(self, openwakeword_models_ready: None) -> None:
        wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"], threshold=0.5)
        silence = np.zeros(wake_word.frame_size(), dtype=np.int16)

        detections = wake_word.process_frame(silence)

        assert detections == []

    def test_frame_size_and_wake_words(self, openwakeword_models_ready: None) -> None:
        wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"])

        assert wake_word.frame_size() == 1280
        assert wake_word.get_wake_words() == ["hey_jarvis"]

    def test_process_frame_wrong_type_raises_voice_error(self, openwakeword_models_ready: None) -> None:
        wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"])

        with pytest.raises(VoiceError):
            wake_word.process_frame([1, 2, 3])  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_is_available(self, openwakeword_models_ready: None) -> None:
        wake_word = OpenWakeWordProvider(wakeword_models=["hey_jarvis"])

        assert await wake_word.is_available() is True
