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
from math import gcd

import numpy as np

from ..logging import get_logger

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16
FRAME_SIZE = 1280  # 80ms @ 16kHz — tamaño de frame que espera openWakeWord

logger = get_logger("voice.audio_io")


def _prefer_wasapi_input_device(hostapis: list[dict]) -> int | None:
    """Dado `sounddevice.query_hostapis()`, devuelve el índice del
    dispositivo de entrada default de la hostapi WASAPI, si existe.

    En Windows, el dispositivo de entrada "default" que PortAudio elige
    sin más contexto suele resolver a la hostapi MME — que, para al menos
    un micrófono probado con hardware real (Razer Seiren Mini), devolvía
    audio casi silencioso (RMS ~0.5 constante, sin importar el volumen
    real) mientras que el mismo dispositivo por WASAPI capturaba bien
    (ver PROGRESS.md, sección "Validación de VoicePipeline con hardware
    real"). No es un bug de esta librería, es un problema conocido del
    backend MME con ciertos drivers/dispositivos — WASAPI es el backend
    de audio moderno de Windows y no tiene ese problema, así que se
    prefiere activamente en vez de confiar en el default "crudo".
    En sistemas sin hostapi WASAPI (no-Windows) devuelve `None` y el
    llamador cae al comportamiento default de PortAudio."""
    for hostapi in hostapis:
        if hostapi.get("name") == "Windows WASAPI":
            index = hostapi.get("default_input_device", -1)
            if index is not None and index >= 0:
                return index
    return None


def _resample_frame(frame: np.ndarray, native_rate: int, target_rate: int, target_length: int) -> np.ndarray:
    """Resamplea `frame` (int16) de `native_rate` a `target_rate`,
    ajustando el resultado a exactamente `target_length` muestras.

    Usa `scipy.signal.resample_poly` (filtro FIR polifásico con
    anti-aliasing) en vez de decimación cruda — descartar muestras sin
    filtrar introduciría aliasing, degradando la señal de la misma forma
    que el problema que se está resolviendo (audio que "parece" tener
    señal pero no sirve para el modelo de wake word). Se aplica por
    frame de forma independiente (sin estado de filtro entre llamadas);
    el orden del filtro es chico respecto al tamaño de frame (80ms), así
    que el artefacto de borde en cada límite de frame es mínimo."""
    from scipy.signal import resample_poly

    divisor = gcd(native_rate, target_rate)
    up, down = target_rate // divisor, native_rate // divisor
    resampled = resample_poly(frame.astype(np.float64), up, down)

    if len(resampled) > target_length:
        resampled = resampled[:target_length]
    elif len(resampled) < target_length:
        resampled = np.pad(resampled, (0, target_length - len(resampled)))

    return np.clip(resampled, -32768, 32767).astype(np.int16)


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

    `read_frame()` siempre devuelve `frame_size` muestras a `sample_rate`
    (16kHz por default), sea cual sea el sample rate nativo del
    dispositivo elegido — la captura real ocurre al rate nativo del
    dispositivo (algunos backends de audio en Windows fuerzan un rate
    fijo, típicamente 48kHz o 44.1kHz, e ignoran/degradan un pedido
    explícito de 16kHz) y se resamplea a `sample_rate` en `read_frame()`.
    Ver `_resample_frame` y `_prefer_wasapi_input_device`.
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
        self._native_rate = sample_rate
        self._native_frame_size = frame_size

    def open(self) -> None:
        import sounddevice as sd

        resolved_device = self.device
        if resolved_device is None:
            resolved_device = _prefer_wasapi_input_device(sd.query_hostapis())

        device_info = sd.query_devices(resolved_device, "input")
        self._native_rate = int(round(device_info["default_samplerate"]))
        self._native_frame_size = max(1, round(self.frame_size * self._native_rate / self.sample_rate))

        self._stream = sd.InputStream(
            samplerate=self._native_rate,
            channels=1,
            dtype="int16",
            blocksize=self._native_frame_size,
            device=resolved_device,
        )
        self._stream.start()

    def read_frame(self) -> np.ndarray:
        """Lee (bloqueante) el equivalente a `frame_size` muestras a
        `sample_rate`, resampleadas desde el rate nativo de captura si
        hace falta."""
        if self._stream is None:
            raise RuntimeError("MicrophoneListener no está abierto — llamar open() primero")
        frame, overflowed = self._stream.read(self._native_frame_size)
        if overflowed:
            logger.warning("Buffer de captura de audio desbordado (overflow)")
        frame = frame.reshape(-1)
        if self._native_rate != self.sample_rate:
            frame = _resample_frame(frame, self._native_rate, self.sample_rate, self.frame_size)
        return frame

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
