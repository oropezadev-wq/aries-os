"""voice/pipeline.py — orquesta el flujo completo de Voice: wake word ->
captura -> STT -> `POST /message` (ya existente, sin cambios) ->
confirmación (si hace falta) -> TTS -> reproducción.

Decisión 2 de `docs/specs/Voice.spec.md`: este pipeline corre como un
proceso cliente HTTP más de la API — no se agregó ningún endpoint nuevo
en `api.py`, ni se tocó `Planner`/`Brain`/`Kernel`.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

import httpx

from ..exceptions import VoiceError
from ..logging import get_logger
from ..routines.manager import ROUTINES_TOPIC
from .audio_io import MicrophoneListener, SpeakerPlayer, record_until_silence
from ..contracts.message_bus import IMessageBus
from ..contracts.stt import ISTTProvider
from ..contracts.tts import ITTSProvider
from ..contracts.wake_word import IWakeWordProvider

# docs/specs/MessageBus.spec.md sección 6.4: nombre de consumidor fijo, no
# hostname+pid — un nombre que cambia en cada reinicio huérfana el PEL del
# consumidor anterior. v1 asume un solo proceso VoicePipeline corriendo a
# la vez (mismo documento).
ROUTINES_CONSUMER_GROUP = "voice-pipeline"
ROUTINES_CONSUMER_NAME = "main"

# Decisión 5 de Voice.spec.md: frase de confirmación EXACTA, no un "sí"
# suelto — mitiga (sin eliminar del todo) el riesgo de que STT transcriba
# mal una respuesta corta y ambigua.
CONFIRMATION_PHRASE = "confirmo"

_NO_ENTENDI = "No te escuché bien, decime de nuevo."
_ACCION_CANCELADA = "No escuché la confirmación exacta, cancelo la acción."
_SIN_RESPUESTA_TTS = "Listo."


def _normalize_confirmation_text(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación — para no fallar por un signo
    de puntuación o mayúscula fantasma de la transcripción."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", "", text.lower())
    return text.strip()


@dataclass
class VoicePipelineConfig:
    """Configuración del pipeline de Voice."""

    api_base_url: str = "http://127.0.0.1:8000"
    language: Optional[str] = "es"
    max_utterance_seconds: float = 10.0
    silence_duration_seconds: float = 1.0
    confirmation_timeout_seconds: float = 8.0


class VoicePipeline:
    """Orquesta el ciclo completo de una interacción de voz.

    Nunca deja escapar una excepción no controlada fuera de `run_once()`
    ni de `run_forever()` — cualquier falla de un proveedor (wake word/
    STT/TTS) o de la llamada HTTP se loguea y el turno actual se descarta;
    el loop vuelve a esperar la próxima wake word. Mismo criterio que
    `IAgent.execute()`/`PluginRegistry.load()` en el resto del proyecto.
    """

    def __init__(
        self,
        wake_word: IWakeWordProvider,
        stt: ISTTProvider,
        tts: ITTSProvider,
        listener: MicrophoneListener,
        player: SpeakerPlayer,
        message_bus: IMessageBus,
        config: Optional[VoicePipelineConfig] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.listener = listener
        self.player = player
        # Mismo patrón que wake_word/stt/tts (docs/specs/Routines.spec.md
        # sección 4): recibido por parámetro, nunca construido acá, para
        # compartir el mismo `IMessageBus`/Redis que usa `RoutineManager`
        # en el otro proceso.
        self.message_bus = message_bus
        self.config = config or VoicePipelineConfig()
        self.logger = get_logger(self.__class__.__name__)
        self._http_client = http_client
        self._owns_http_client = http_client is None

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(base_url=self.config.api_base_url, timeout=30.0)
        return self._http_client

    # ------------------------------------------------------------------
    # Captura de audio (bloqueante, corre en un hilo aparte vía to_thread)
    # ------------------------------------------------------------------

    def _listen_for_activation_sync(self) -> bytes:
        """Bloquea hasta detectar una wake word y graba la utterance en el
        MISMO stream ya abierto (sin reabrir) para no perder los primeros
        frames de la orden justo después de la wake word."""
        with self.listener:
            self.logger.info("escuchando...")
            while True:
                frame = self.listener.read_frame()
                detections = self.wake_word.process_frame(frame)
                if detections:
                    break
            return record_until_silence(
                self.listener,
                max_seconds=self.config.max_utterance_seconds,
                silence_duration_seconds=self.config.silence_duration_seconds,
            )

    def _record_utterance_sync(self, max_seconds: float) -> bytes:
        """Graba una utterance sin esperar wake word — usado para
        recolectar la frase de confirmación (el usuario ya está en medio
        de una interacción, no hace falta volver a despertar al pipeline)."""
        with self.listener:
            return record_until_silence(
                self.listener,
                max_seconds=max_seconds,
                silence_duration_seconds=self.config.silence_duration_seconds,
            )

    # ------------------------------------------------------------------
    # HTTP: cliente de POST /message, igual que cualquier otro consumidor
    # ------------------------------------------------------------------

    async def _post_message(self, user_input: str, session_id: str, confirmed: bool) -> dict[str, Any]:
        client = await self._get_http_client()
        response = await client.post(
            "/message",
            json={"user_input": user_input, "session_id": session_id, "confirmed": confirmed},
        )
        response.raise_for_status()
        return response.json()

    async def _speak(self, text: str) -> None:
        tts_result = await self.tts.synthesize(text)
        await asyncio.to_thread(self.player.play_wav, tts_result.audio)

    # ------------------------------------------------------------------
    # Confirmación de acciones destructivas (decisión 5)
    # ------------------------------------------------------------------

    async def _handle_confirmation(
        self, user_text: str, session_id: str, response: dict[str, Any]
    ) -> dict[str, Any]:
        warning = response.get("error") or "Se necesita confirmación para continuar."
        await self._speak(f"{warning} Decí '{CONFIRMATION_PHRASE}' para continuar.")

        confirmation_audio = await asyncio.to_thread(
            self._record_utterance_sync, self.config.confirmation_timeout_seconds
        )
        confirmation_result = await self.stt.transcribe(confirmation_audio, language=self.config.language)
        heard = _normalize_confirmation_text(confirmation_result.text)

        if heard != CONFIRMATION_PHRASE:
            self.logger.info("Confirmación por voz no coincide, se cancela la acción", heard=heard)
            await self._speak(_ACCION_CANCELADA)
            return response

        return await self._post_message(user_text, session_id, confirmed=True)

    # ------------------------------------------------------------------
    # Ciclo completo
    # ------------------------------------------------------------------

    async def run_once(self) -> None:
        """Un ciclo completo: espera wake word, graba, transcribe, llama a
        `POST /message`, maneja confirmación si hace falta, sintetiza y
        reproduce la respuesta. Nunca propaga excepciones."""
        session_id = f"voice-{uuid4()}"  # nuevo por activación, decisión 8
        try:
            audio_wav = await asyncio.to_thread(self._listen_for_activation_sync)
            stt_result = await self.stt.transcribe(audio_wav, language=self.config.language)
            user_text = stt_result.text.strip()

            if not user_text:
                self.logger.info("STT no transcribió nada inteligible, se descarta el turno")
                await self._speak(_NO_ENTENDI)
                return

            self.logger.info("Utterance transcripta", text=user_text, session_id=session_id)
            response = await self._post_message(user_text, session_id, confirmed=False)

            if response.get("needs_confirmation"):
                response = await self._handle_confirmation(user_text, session_id, response)

            text_to_speak = response.get("response_text") or response.get("error") or _SIN_RESPUESTA_TTS
            await self._speak(text_to_speak)
        except VoiceError as error:
            self.logger.error("Error del pipeline de voz, se descarta el turno", error=str(error))
        except httpx.HTTPError as error:
            self.logger.error("Error de red al llamar a POST /message", error=str(error))
        except Exception as error:  # red de seguridad final — nunca debe tumbar run_forever()
            self.logger.exception("Error inesperado en el pipeline de voz", error=str(error))

    # ------------------------------------------------------------------
    # Consumo de rutinas proactivas (docs/specs/Routines.spec.md sección 4,
    # docs/specs/MessageBus.spec.md sección 6)
    # ------------------------------------------------------------------

    async def _consume_routines(self) -> None:
        """Segundo loop concurrente de `run_forever()`: consume
        `"routines.due"` y habla cada `SpeakAction` publicada por
        `RoutineManager` (proceso de la API, posiblemente caído/desconectado
        por un rato — de ahí Redis Streams en vez de pub/sub).

        Comportamiento exacto, no negociable, especificado en
        `MessageBus.spec.md` sección 6 — repetido acá en código, no solo en
        docs:
        - `ack()` se hace SIEMPRE después de terminar (hablado o
          descartado), nunca antes de leer (6.2) — si el proceso crashea a
          mitad de la síntesis, el mensaje queda en el PEL y se vuelve a
          entregar al reconectar (6.4), en vez de perderse.
        - Un mensaje vencido (`now > valid_until`) se descarta SIN hablar,
          pero de todas formas se hace `ack()` (6.1) — dejarlo sin ack lo
          dejaría reintentándose para siempre sin motivo.
        - Nunca deja escapar una excepción no controlada, mismo criterio
          que `run_once()` — un error puntual (payload malformado, TTS que
          falla) no debe tumbar este loop de fondo.
        """
        subscription = self.message_bus.subscribe(
            ROUTINES_TOPIC, group=ROUTINES_CONSUMER_GROUP, consumer=ROUTINES_CONSUMER_NAME
        )
        async for message in subscription:
            try:
                payload = message.payload
                valid_until = datetime.fromisoformat(payload["valid_until"])
                if datetime.now(UTC) > valid_until:
                    self.logger.warning(
                        "Rutina vencida, se descarta sin hablar",
                        routine_id=payload.get("routine_id"),
                        valid_until=payload["valid_until"],
                    )
                else:
                    await self._speak(payload["text"])
            except Exception as error:  # red de seguridad — nunca debe tumbar el loop
                self.logger.exception(
                    "Error inesperado consumiendo un mensaje de rutina, se descarta", error=str(error)
                )
            try:
                await self.message_bus.ack(ROUTINES_TOPIC, ROUTINES_CONSUMER_GROUP, message.id)
            except Exception as error:
                # Un ack() fallido (ej. Redis caído justo en ese instante) no
                # debe tumbar este loop de fondo — el mensaje queda en el PEL
                # y se reintrega en la próxima conexión (6.4), consistente
                # con la decisión ya tomada de preferir duplicar antes que
                # perder (sección 4 de MessageBus.spec.md).
                self.logger.warning(
                    "No se pudo confirmar (ack) un mensaje de rutina", message_id=message.id, error=str(error)
                )

    async def run_forever(self) -> None:
        """Corre `run_once()` (wake word) y `_consume_routines()` (rutinas
        proactivas) como dos tasks concurrentes hasta que se cancele la
        tarea — factible sin reescribir nada del loop de wake word:
        `_listen_for_activation_sync` ya corre en un hilo aparte vía
        `asyncio.to_thread`, así que el event loop principal queda libre
        para el segundo task."""
        self.logger.info(
            "Pipeline de voz arrancado, esperando wake word",
            wake_words=self.wake_word.get_wake_words(),
        )
        routines_task = asyncio.create_task(self._consume_routines())
        try:
            while True:
                await self.run_once()
        finally:
            routines_task.cancel()
            try:
                await routines_task
            except asyncio.CancelledError:
                pass
            await self.close()
