"""Pruebas de `voice/audio_io.py`.

`pcm_to_wav_bytes`/`wav_bytes_to_pcm` y `record_until_silence` no tocan
hardware real — se prueban con datos/objetos de prueba de verdad (no
mocks), sin necesitar `MicrophoneListener` real. El hardware de audio en
sí (`sounddevice`) recién se mockea en `test_voice_pipeline.py`, que sí
necesita orquestar `MicrophoneListener`/`SpeakerPlayer` completos.
"""

from __future__ import annotations

import numpy as np

from aries.voice.audio_io import (
    SAMPLE_RATE,
    _prefer_wasapi_input_device,
    _resample_frame,
    pcm_to_wav_bytes,
    record_until_silence,
    wav_bytes_to_pcm,
)


class FakeListener:
    """Doble de `MicrophoneListener`: mismo `sample_rate`/`frame_size`/
    `read_frame()`, pero devuelve frames predefinidos en vez de leer un
    micrófono real."""

    def __init__(self, frames: list[np.ndarray], sample_rate: int = SAMPLE_RATE, frame_size: int = 160) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._frames = list(frames)
        self._index = 0

    def read_frame(self) -> np.ndarray:
        frame = self._frames[self._index] if self._index < len(self._frames) else self._frames[-1]
        self._index += 1
        return frame


def _loud_frame(frame_size: int) -> np.ndarray:
    return np.full(frame_size, 10000, dtype=np.int16)


def _silent_frame(frame_size: int) -> np.ndarray:
    return np.zeros(frame_size, dtype=np.int16)


class TestPreferWasapiInputDevice:
    def test_returns_wasapi_default_input_device_when_present(self) -> None:
        hostapis = [
            {"name": "MME", "default_input_device": 1},
            {"name": "Windows WASAPI", "default_input_device": 15},
        ]

        assert _prefer_wasapi_input_device(hostapis) == 15

    def test_returns_none_when_no_wasapi_hostapi(self) -> None:
        hostapis = [{"name": "MME", "default_input_device": 1}]

        assert _prefer_wasapi_input_device(hostapis) is None

    def test_returns_none_when_wasapi_has_no_input_device(self) -> None:
        hostapis = [{"name": "Windows WASAPI", "default_input_device": -1}]

        assert _prefer_wasapi_input_device(hostapis) is None


class TestResampleFrame:
    def test_downsamples_to_exact_target_length(self) -> None:
        # 48kHz -> 16kHz (ratio 3:1), como el caso real que motivó esto.
        native_rate, target_rate, target_length = 48000, 16000, 1280
        frame = (np.sin(np.linspace(0, 2 * np.pi * 10, target_length * 3)) * 10000).astype(np.int16)

        resampled = _resample_frame(frame, native_rate, target_rate, target_length)

        assert resampled.shape == (target_length,)
        assert resampled.dtype == np.int16

    def test_preserves_signal_energy_roughly(self) -> None:
        native_rate, target_rate, target_length = 48000, 16000, 1280
        frame = np.full(target_length * 3, 10000, dtype=np.int16)

        resampled = _resample_frame(frame, native_rate, target_rate, target_length)

        # Una señal constante fuerte no debería colapsar a (casi) silencio
        # tras el resampleo — la falla original era exactamente esto.
        assert np.abs(resampled.astype(np.float64)).mean() > 5000


class TestPcmWavRoundTrip:
    def test_round_trip_preserves_pcm_and_metadata(self) -> None:
        pcm = np.array([1, -1, 100, -100, 32000, -32000], dtype=np.int16).tobytes()

        wav_bytes = pcm_to_wav_bytes(pcm, sample_rate=22050, channels=1, sample_width=2)

        assert wav_bytes[:4] == b"RIFF"
        recovered_pcm, sample_rate, channels, sample_width = wav_bytes_to_pcm(wav_bytes)
        assert recovered_pcm == pcm
        assert sample_rate == 22050
        assert channels == 1
        assert sample_width == 2


class TestRecordUntilSilence:
    def test_stops_after_silence_duration(self) -> None:
        frame_size = 160  # 10ms @ 16kHz, para que el test sea rápido de armar
        # 1 frame de habla + 3 de silencio (duración de silencio pedida: 2 frames)
        frames = [_loud_frame(frame_size), _silent_frame(frame_size), _silent_frame(frame_size), _loud_frame(frame_size)]
        listener = FakeListener(frames, sample_rate=SAMPLE_RATE, frame_size=frame_size)
        silence_duration_seconds = 2 * frame_size / SAMPLE_RATE  # exactamente 2 frames

        wav_bytes = record_until_silence(
            listener, max_seconds=10.0, silence_threshold=300.0, silence_duration_seconds=silence_duration_seconds
        )

        pcm, sample_rate, channels, _width = wav_bytes_to_pcm(wav_bytes)
        # Debe cortar en el frame 3 (índice 2), sin llegar al 4to frame (loud) que sigue.
        assert len(pcm) // 2 == frame_size * 3
        assert sample_rate == SAMPLE_RATE
        assert channels == 1

    def test_stops_at_max_seconds_if_never_silent(self) -> None:
        frame_size = 160
        listener = FakeListener([_loud_frame(frame_size)] * 100, sample_rate=SAMPLE_RATE, frame_size=frame_size)
        max_seconds = 5 * frame_size / SAMPLE_RATE  # exactamente 5 frames

        wav_bytes = record_until_silence(
            listener, max_seconds=max_seconds, silence_threshold=300.0, silence_duration_seconds=100.0
        )

        pcm, _sample_rate, _channels, _width = wav_bytes_to_pcm(wav_bytes)
        assert len(pcm) // 2 == frame_size * 5
