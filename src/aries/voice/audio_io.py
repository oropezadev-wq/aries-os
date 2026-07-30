"""voice/audio_io.py — captura/reproducción de audio real vía `sounddevice`
(decisión 3 de `docs/specs/Voice.spec.md`) y utilidades de conversión
PCM↔WAV.

Único punto del pipeline de Voice donde se mockea hardware en los tests
(`MicrophoneListener`/`SpeakerPlayer`) — todo lo demás (wake word, STT,
TTS, HTTP) es real. No porque no haya hardware de audio disponible (sí lo
hay en la máquina de desarrollo), sino porque grabar/reproducir audio real
en una corrida de tests automatizada sería no determinístico (depende de
silencio/ruido ambiente real) y perturbador (reproduce sonido real durante
`pytest`) — la misma razón por la que no se testea contra un micrófono
real en ningún proyecto de este tipo.
"""

from __future__ import annotations

import io
import wave

import numpy as np

from ..logging import get_logger

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16
FRAME_SIZE = 1280  # 80ms @ 16kHz — tamaño de frame que espera openWakeWord

logger = get_logger("voice.audio_io")


def pcm_to_wav_bytes(
    pcm: bytes,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    sample_width: int = SAMPLE_WIDTH,
) -> bytes:
    """Envuelve PCM crudo (int16) en un WAV completo (con header) en
    memoria. Necesario porque `faster-whisper` rechaza PCM sin header
    (`InvalidDataError`, verificado empíricamente) — ver decisión 4 de
    `docs/specs/Voice.spec.md`."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buffer.getvalue()


def wav_bytes_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
    """Extrae `(pcm, sample_rate, channels, sample_width)` de un WAV
    completo en memoria."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        pcm = wf.readframes(wf.getnframes())
        return pcm, wf.getframerate(), wf.getnchannels(), wf.getsampwidth()


class MicrophoneListener:
    """Captura de audio real desde el micrófono, vía `sounddevice`.

    `sounddevice` se importa de forma diferida (dentro de `open()`, no a
    nivel de módulo) porque es una dependencia pesada opcional (extra
    `voice` de `pyproject.toml`) — el resto de `aries` no debe fallar al
    importarse si no está instalada.
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        frame_size: int = FRAME_SIZE,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.device = device
        self._stream = None

    def open(self) -> None:
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_size,
            device=self.device,
        )
        self._stream.start()

    def read_frame(self) -> np.ndarray:
        """Lee (bloqueante) exactamente `frame_size` samples del micrófono."""
        if self._stream is None:
            raise RuntimeError("MicrophoneListener no está abierto — llamar open() primero")
        frame, overflowed = self._stream.read(self.frame_size)
        if overflowed:
            logger.warning("Buffer de captura de audio desbordado (overflow)")
        return frame.reshape(-1)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "MicrophoneListener":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class SpeakerPlayer:
    """Reproducción de audio real por parlante, vía `sounddevice`."""

    def play_wav(self, wav_bytes: bytes) -> None:
        """Reproduce (bloqueante hasta que termina) un WAV completo."""
        import sounddevice as sd

        pcm, sample_rate, channels, _sample_width = wav_bytes_to_pcm(wav_bytes)
        audio = np.frombuffer(pcm, dtype=np.int16).reshape(-1, channels)
        sd.play(audio, samplerate=sample_rate)
        sd.wait()


def record_until_silence(
    listener: MicrophoneListener,
    max_seconds: float = 10.0,
    silence_threshold: float = 300.0,
    silence_duration_seconds: float = 1.0,
) -> bytes:
    """Graba desde `listener` (ya abierto por el llamador) hasta detectar
    `silence_duration_seconds` seguidos de energía por debajo de
    `silence_threshold` (RMS simple sobre cada frame — no un VAD dedicado,
    decisión 6 de `docs/specs/Voice.spec.md`), o hasta `max_seconds` como
    límite duro. Devuelve WAV completo (con header).

    El silencio **antes** de que el usuario empiece a hablar no cuenta
    para el corte — solo el silencio que viene *después* de detectar al
    menos un frame con energía por encima de `silence_threshold`. Sin
    esto, una pausa natural antes de empezar a responder (ej. tras
    escuchar la pregunta de confirmación) cortaría la grabación antes de
    que se dijera una sola palabra — bug real encontrado con un test end
    a end, no hipotético (ver `tests/unit/test_voice_pipeline.py`)."""
    frames: list[np.ndarray] = []
    silence_frames_needed = max(
        1, int(silence_duration_seconds * listener.sample_rate / listener.frame_size)
    )
    max_frames = max(1, int(max_seconds * listener.sample_rate / listener.frame_size))
    silent_run = 0
    speech_started = False

    for _ in range(max_frames):
        frame = listener.read_frame()
        frames.append(frame)
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        if rms < silence_threshold:
            if speech_started:
                silent_run += 1
                if silent_run >= silence_frames_needed:
                    break
        else:
            speech_started = True
            silent_run = 0

    pcm = np.concatenate(frames).astype(np.int16).tobytes() if frames else b""
    return pcm_to_wav_bytes(pcm, sample_rate=listener.sample_rate)
