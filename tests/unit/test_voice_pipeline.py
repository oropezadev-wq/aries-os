"""Pruebas de `VoicePipeline` contra la app real de `aries.api` (vía
`httpx.AsyncClient` + `ASGITransport`, sin un servidor de red real
corriendo — mismo principio que `TestClient`, pero async). Todo real:
wake word (`OpenWakeWordProvider`), STT (`FasterWhisperProvider`), TTS
(`PiperProvider`), y el propio `Planner`/`AgentManager` de la app (solo
`ILLMProvider` se sobreescribe con un fake, mismo criterio ya establecido
en `tests/integration/test_api_message.py`, para no depender de un
servidor Ollama real).

**Único mock de todo el módulo de Voice, documentado y justificado:** el
hardware de audio (`MicrophoneListener`/`SpeakerPlayer`). No hay forma
razonable de probar contra un micrófono/parlante físico en una corrida de
`pytest` automatizada — sería no determinístico (depende de silencio/ruido
ambiente real) y perturbador (reproduciría audio real durante la corrida).
Se reemplazan por dobles que devuelven/capturan los mismos datos (frames
de audio reales, generados con Piper) sin tocar hardware.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pytest

from aries.agents.manager import AgentManager
from aries.api import app, get_planner
from aries.contracts.llm import ILLMProvider, LLMResponse
from aries.contracts.message_bus import BusMessage, IMessageBus
from aries.contracts.stt import ISTTProvider
from aries.contracts.tts import ITTSProvider, TTSResult
from aries.contracts.wake_word import IWakeWordProvider
from aries.events import AsyncEventBus
from aries.memory.in_memory import InMemoryStore
from aries.planner import Planner
from aries.routines.manager import ROUTINES_TOPIC
from aries.voice.audio_io import SAMPLE_RATE, wav_bytes_to_pcm
from aries.voice.faster_whisper_provider import FasterWhisperProvider
from aries.voice.openwakeword_provider import OpenWakeWordProvider
from aries.voice.pipeline import CONFIRMATION_PHRASE, VoicePipeline, VoicePipelineConfig
from aries.voice.piper_provider import PiperProvider

FRAME_SIZE = 1280


class FakeMessageBus(IMessageBus):
    """`IMessageBus` fake — estos tests ejercitan `run_once()` directamente
    (wake word -> STT -> POST /message -> TTS), nunca `run_forever()`, así
    que el segundo loop de rutinas (`_consume_routines()`) nunca se llega a
    correr. Solo hace falta satisfacer el contrato para construir el
    `VoicePipeline`."""

    async def publish(self, topic: str, payload: dict) -> str:
        return "0-1"

    async def subscribe(self, topic: str, group: str, consumer: str):
        if False:  # pragma: no cover - nunca se llama en estos tests
            yield
        return

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        return None


class FakeLLMProvider(ILLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        content = self._responses.pop(0) if self._responses else ""
        return LLMResponse(content=content, model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


class FakeSpeakerPlayer:
    """Doble de `SpeakerPlayer`: no reproduce nada, solo guarda el WAV
    recibido para poder verificar qué se le habría dicho al usuario."""

    def __init__(self) -> None:
        self.played: list[bytes] = []

    def play_wav(self, wav_bytes: bytes) -> None:
        self.played.append(wav_bytes)


class ScriptedListener:
    """Doble de `MicrophoneListener`: no toca hardware, devuelve frames
    reales precomputados (audio sintetizado con Piper) en el orden en que
    se los pide. Al agotar el guion, devuelve silencio indefinidamente."""

    def __init__(self, frames: list[np.ndarray], sample_rate: int = SAMPLE_RATE, frame_size: int = FRAME_SIZE) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._frames = frames
        self._index = 0

    def read_frame(self) -> np.ndarray:
        if self._index >= len(self._frames):
            return np.zeros(self.frame_size, dtype=np.int16)
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def __enter__(self) -> "ScriptedListener":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _frames_from_wav(wav_bytes: bytes, frame_size: int = FRAME_SIZE) -> list[np.ndarray]:
    pcm, sample_rate, channels, _width = wav_bytes_to_pcm(wav_bytes)
    assert sample_rate == SAMPLE_RATE and channels == 1
    audio = np.frombuffer(pcm, dtype=np.int16)
    frames = []
    for start in range(0, len(audio), frame_size):
        chunk = audio[start : start + frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)))
        frames.append(chunk)
    return frames


def _silent_frames(count: int, frame_size: int = FRAME_SIZE) -> list[np.ndarray]:
    return [np.zeros(frame_size, dtype=np.int16) for _ in range(count)]


@pytest.fixture()
def real_providers(piper_voice_es_paths, piper_voice_en_paths, whisper_tiny_model, openwakeword_models_ready):
    """Providers reales (sin mocks) para todo el pipeline de voz."""
    es_model_path, es_config_path = piper_voice_es_paths
    return {
        "wake_word": OpenWakeWordProvider(wakeword_models=["hey_jarvis"], threshold=0.5),
        "stt": FasterWhisperProvider(model_size="tiny", model=whisper_tiny_model),
        "tts": PiperProvider(model_path=es_model_path, config_path=es_config_path),
        "es_voice_paths": (es_model_path, es_config_path),
        "en_voice_paths": piper_voice_en_paths,
    }


async def _build_scripted_frames(real_providers, phrase_es: str) -> list[np.ndarray]:
    """Arma el guion de frames: wake word real ("hey jarvis", en inglés,
    repetida 3 veces para asegurar que el detector real la reconozca) +
    utterance real (`phrase_es`, en español) + silencio suficiente para
    disparar el corte por silencio.

    **Detalle importante, encontrado con un test real, no anticipado:** se
    trunca la wake word exactamente en el frame donde un detector de
    verdad la reconoce (en vez de incluir las 3 repeticiones completas).
    Sin esto, las pausas naturales entre repeticiones ("hey jarvis, [pausa]
    hey jarvis, ...") quedan como parte de los frames todavía no
    consumidos por el loop de espera de wake word, y `record_until_silence`
    los interpreta como el comando real — cortando la grabación en una de
    esas pausas, antes de llegar a `phrase_es`. Truncar acá reproduce lo
    que pasaría con un micrófono real: en cuanto se detecta la wake word,
    el usuario ya está diciendo el comando a continuación, sin más "hey
    jarvis" de por medio.
    """
    en_model_path, en_config_path = real_providers["en_voice_paths"]
    wake_word_tts = PiperProvider(model_path=en_model_path, config_path=en_config_path)
    wake_word_audio = await wake_word_tts.synthesize("hey jarvis, hey jarvis, hey jarvis")
    wake_frames_full = _frames_from_wav(wake_word_audio.audio)

    probe = OpenWakeWordProvider(wakeword_models=["hey_jarvis"], threshold=0.5)
    trigger_index = next(
        (i for i, frame in enumerate(wake_frames_full) if probe.process_frame(frame)), None
    )
    assert trigger_index is not None, "la wake word sintetizada no disparó una detección real"
    wake_frames = wake_frames_full[: trigger_index + 1]

    utterance_audio = await real_providers["tts"].synthesize(phrase_es)

    return wake_frames + _frames_from_wav(utterance_audio.audio) + _silent_frames(5)


def _make_pipeline(
    real_providers,
    frames: list[np.ndarray],
    http_client: httpx.AsyncClient,
    player: FakeSpeakerPlayer,
    stt=None,
) -> VoicePipeline:
    listener = ScriptedListener(frames)
    config = VoicePipelineConfig(silence_duration_seconds=0.2, max_utterance_seconds=5.0)
    return VoicePipeline(
        wake_word=real_providers["wake_word"],
        stt=stt or real_providers["stt"],
        tts=real_providers["tts"],
        listener=listener,
        player=player,
        message_bus=FakeMessageBus(),
        config=config,
        http_client=http_client,
    )


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


class TestVoicePipelineRunOnce:
    @pytest.mark.asyncio
    async def test_happy_path_transcribes_calls_api_and_speaks_response(self, real_providers, tmp_path) -> None:
        target = tmp_path / "notas.txt"
        intent = json.dumps(
            {
                "intent": "crear archivo",
                "steps": [
                    {
                        "agent_name": "filesystem",
                        "action": "write_file",
                        "parameters": {"path": str(target), "content": "hola"},
                    }
                ],
            }
        )
        fake_planner = Planner(
            llm_provider=FakeLLMProvider([intent, "Listo, creé el archivo."]),
            agent_manager=AgentManager(),
            event_bus=AsyncEventBus(),
            memory=InMemoryStore(),
        )
        app.dependency_overrides[get_planner] = lambda: fake_planner

        frames = await _build_scripted_frames(real_providers, "abrí un archivo nuevo por favor")
        player = FakeSpeakerPlayer()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://voicetest"
        ) as http_client:
            pipeline = _make_pipeline(real_providers, frames, http_client, player)
            await pipeline.run_once()

        # La wake word real se detectó, el pedido real llegó al Planner
        # real vía HTTP real, el archivo se creó de verdad.
        assert target.read_text(encoding="utf-8") == "hola"
        # Se reprodujo (vía el player fake) la respuesta real del Planner.
        assert len(player.played) == 1
        assert player.played[0][:4] == b"RIFF"

    @pytest.mark.asyncio
    async def test_confirmation_flow_with_exact_phrase_retries_confirmed(
        self, real_providers, whisper_small_model, tmp_path
    ) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        intent = json.dumps(
            {
                "intent": "borrar archivo",
                "steps": [{"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}],
            }
        )
        # `Planner.handle()` re-parsea el intent desde cero en cada
        # llamada (no recuerda el plan entre el pedido sin confirmar y el
        # reintento confirmado) — el pipeline hace 2 POST /message
        # (confirmed=False, después confirmed=True), así que hacen falta
        # 2 parseos de intención + 1 respuesta de Brain (la 1ra llamada,
        # al pedir confirmación, no llega a invocar a Brain).
        fake_planner = Planner(
            llm_provider=FakeLLMProvider([intent, intent, "Listo, lo borré."]),
            agent_manager=AgentManager(),
            event_bus=AsyncEventBus(),
            memory=InMemoryStore(),
        )
        app.dependency_overrides[get_planner] = lambda: fake_planner

        activation_frames = await _build_scripted_frames(real_providers, "borrá el archivo importante")
        # `noise_scale=0.0`/`noise_w_scale=0.0`: síntesis determinística.
        # Piper es estocástico por default (dos llamadas con el mismo
        # texto no producen el mismo audio) -- verificado empíricamente
        # que esto hacía flaky la transcripción exacta de la frase de
        # confirmación (a veces "Confirmo.", a veces "Confirme."). Sin
        # determinismo acá, este test sería no determinístico de verdad,
        # no solo "raro a veces".
        confirmation_audio = await real_providers["tts"].synthesize(
            CONFIRMATION_PHRASE, noise_scale=0.0, noise_w_scale=0.0
        )
        all_frames = activation_frames + _frames_from_wav(confirmation_audio.audio) + _silent_frames(5)
        player = FakeSpeakerPlayer()

        # 'tiny' (usado en el resto de estos tests) transcribió "confirmo"
        # como "Confirme." -- verificado empíricamente. Se usa 'small' acá
        # (el default real de producción, `voice_stt_model_size`) porque
        # este test necesita que la frase de confirmación transcriba
        # exacto para probar el reintento con `confirmed=True`.
        precise_stt = FasterWhisperProvider(model_size="small", model=whisper_small_model)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://voicetest"
        ) as http_client:
            pipeline = _make_pipeline(real_providers, all_frames, http_client, player, stt=precise_stt)
            await pipeline.run_once()

        # El Planner solo recibió confirmed=True en el 2do llamado si el
        # archivo efectivamente se borró.
        assert not target.exists()
        # Se le anunció la confirmación pendiente Y la respuesta final: 2 síntesis reproducidas.
        assert len(player.played) == 2

    @pytest.mark.asyncio
    async def test_confirmation_flow_wrong_phrase_cancels_action(self, real_providers, tmp_path) -> None:
        target = tmp_path / "importante.txt"
        target.write_text("no me borres", encoding="utf-8")
        intent = json.dumps(
            {
                "intent": "borrar archivo",
                "steps": [{"agent_name": "filesystem", "action": "delete_file", "parameters": {"path": str(target)}}],
            }
        )
        fake_planner = Planner(
            llm_provider=FakeLLMProvider([intent]),
            agent_manager=AgentManager(),
            event_bus=AsyncEventBus(),
            memory=InMemoryStore(),
        )
        app.dependency_overrides[get_planner] = lambda: fake_planner

        activation_frames = await _build_scripted_frames(real_providers, "borrá el archivo importante")
        # Una frase distinta a "confirmo" -- debe cancelar, no reintentar.
        wrong_confirmation_audio = await real_providers["tts"].synthesize("no, de ninguna manera")
        all_frames = activation_frames + _frames_from_wav(wrong_confirmation_audio.audio) + _silent_frames(5)
        player = FakeSpeakerPlayer()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://voicetest"
        ) as http_client:
            pipeline = _make_pipeline(real_providers, all_frames, http_client, player)
            await pipeline.run_once()

        # No se confirmó -- el archivo destructivo nunca se ejecutó.
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "no me borres"

    @pytest.mark.asyncio
    async def test_run_once_never_raises_when_api_is_unreachable(self, real_providers) -> None:
        """Red de seguridad final: si `POST /message` falla a nivel de red,
        `run_once()` no debe propagar la excepción."""
        frames = await _build_scripted_frames(real_providers, "hola")
        player = FakeSpeakerPlayer()

        async def _failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("conexión rechazada", request=request)

        transport = httpx.MockTransport(_failing_handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://voicetest") as http_client:
            pipeline = _make_pipeline(real_providers, frames, http_client, player)
            await pipeline.run_once()  # no debe lanzar

        assert player.played == []  # nunca llegó a sintetizar una respuesta


class FakeWakeWordProvider(IWakeWordProvider):
    """Doble mínimo — `_consume_routines()` no lo usa en absoluto, solo
    hace falta satisfacer el constructor de `VoicePipeline`."""

    def process_frame(self, frame):  # pragma: no cover - nunca se llama
        raise NotImplementedError

    def frame_size(self) -> int:
        return FRAME_SIZE

    async def is_available(self) -> bool:
        return True

    def get_wake_words(self) -> list[str]:
        return ["hey_jarvis"]


class FakeSTTProvider(ISTTProvider):
    """Doble mínimo — mismo criterio que `FakeWakeWordProvider` arriba."""

    async def transcribe(self, audio, language=None, **kwargs):  # pragma: no cover - nunca se llama
        raise NotImplementedError

    async def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake"


class FakeTTSProvider(ITTSProvider):
    """TTS fake — evita depender de un modelo de Piper real solo para
    probar `_consume_routines()`, que no ejercita nada de wake word/STT."""

    def __init__(self) -> None:
        self.synthesized: list[str] = []

    async def synthesize(self, text: str, voice=None, **kwargs) -> TTSResult:
        self.synthesized.append(text)
        return TTSResult(audio=b"RIFF....WAVEfake", sample_rate=16000, voice="fake")

    async def is_available(self) -> bool:
        return True

    def get_voice_name(self) -> str:
        return "fake"


class ScriptedMessageBus(IMessageBus):
    """`IMessageBus` fake que entrega un guion fijo de mensajes vía
    `subscribe()` (el generador termina solo al agotarlos, sin necesitar
    cancelación — a diferencia de `RedisStreamsMessageBus`, que es de
    duración infinita) y registra cada `ack()` recibido, para poder
    verificar el orden exacto (hablar-o-descartar, LUEGO ack) sin depender
    de Redis real."""

    def __init__(self, messages: list) -> None:
        self._messages = messages
        self.acked: list[str] = []

    async def publish(self, topic: str, payload: dict) -> str:
        return "0-1"

    async def subscribe(self, topic: str, group: str, consumer: str):
        for message in self._messages:
            yield message

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        self.acked.append(message_id)


def _make_consume_routines_pipeline(bus: ScriptedMessageBus, tts: FakeTTSProvider, player: FakeSpeakerPlayer) -> VoicePipeline:
    return VoicePipeline(
        wake_word=FakeWakeWordProvider(),
        stt=FakeSTTProvider(),
        tts=tts,
        listener=ScriptedListener([]),
        player=player,
        message_bus=bus,
    )


class TestVoicePipelineConsumeRoutines:
    """`_consume_routines()` — el segundo loop de `run_forever()` que
    consume `"routines.due"` (docs/specs/Routines.spec.md sección 4,
    docs/specs/MessageBus.spec.md sección 6). Pedido explícito del usuario
    al aprobar el diseño: el camino de mensaje vencido también debe hacer
    `ack()`, si no queda reintentándose en cada arranque sin resolverse
    nunca."""

    @pytest.mark.asyncio
    async def test_speaks_non_stale_message_and_acks_after(self) -> None:
        message = BusMessage(
            id="1-0",
            topic=ROUTINES_TOPIC,
            payload={
                "routine_id": "buenos-dias",
                "occurrence": datetime.now(UTC).isoformat(),
                "valid_until": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                "text": "Buenos días",
            },
        )
        bus = ScriptedMessageBus([message])
        tts = FakeTTSProvider()
        player = FakeSpeakerPlayer()
        pipeline = _make_consume_routines_pipeline(bus, tts, player)

        await pipeline._consume_routines()

        assert tts.synthesized == ["Buenos días"]
        assert len(player.played) == 1
        assert bus.acked == ["1-0"]

    @pytest.mark.asyncio
    async def test_stale_message_is_discarded_without_speaking_but_still_acked(self) -> None:
        """El caso que el usuario pidió confirmar explícitamente: un
        mensaje con `valid_until` ya vencido NO se habla, pero de todas
        formas se hace `ack()` — si no, quedaría atascado repitiéndose en
        cada arranque sin resolverse nunca (MessageBus.spec.md 6.1)."""
        message = BusMessage(
            id="2-0",
            topic=ROUTINES_TOPIC,
            payload={
                "routine_id": "buenos-dias",
                "occurrence": (datetime.now(UTC) - timedelta(hours=6)).isoformat(),
                "valid_until": (datetime.now(UTC) - timedelta(hours=5, minutes=30)).isoformat(),
                "text": "Buenos días",
            },
        )
        bus = ScriptedMessageBus([message])
        tts = FakeTTSProvider()
        player = FakeSpeakerPlayer()
        pipeline = _make_consume_routines_pipeline(bus, tts, player)

        await pipeline._consume_routines()

        assert tts.synthesized == []  # nunca se sintetizó ni se habló
        assert player.played == []
        assert bus.acked == ["2-0"]  # pero SÍ se confirmó, igual

    @pytest.mark.asyncio
    async def test_multiple_messages_each_get_their_own_ack_in_order(self) -> None:
        fresh = BusMessage(
            id="3-0",
            topic=ROUTINES_TOPIC,
            payload={
                "routine_id": "a",
                "occurrence": datetime.now(UTC).isoformat(),
                "valid_until": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                "text": "primera",
            },
        )
        stale = BusMessage(
            id="4-0",
            topic=ROUTINES_TOPIC,
            payload={
                "routine_id": "b",
                "occurrence": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                "valid_until": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "text": "segunda",
            },
        )
        bus = ScriptedMessageBus([fresh, stale])
        tts = FakeTTSProvider()
        player = FakeSpeakerPlayer()
        pipeline = _make_consume_routines_pipeline(bus, tts, player)

        await pipeline._consume_routines()

        assert tts.synthesized == ["primera"]
        assert len(player.played) == 1
        assert bus.acked == ["3-0", "4-0"]
