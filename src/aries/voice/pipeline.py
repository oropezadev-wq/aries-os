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
from typing import Any, Optional
from uuid import uuid4

import httpx
import numpy as np  # TEMPORAL: solo para el log de diagnóstico de audio, ver _listen_for_activation_sync

from ..exceptions import VoiceError
from ..logging import get_logger
from .audio_io import MicrophoneListener, SpeakerPlayer, record_until_silence
from ..contracts.stt import ISTTProvider
from ..contracts.tts import ITTSProvider
from ..contracts.wake_word import IWakeWordProvider

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
        config: Optional[VoicePipelineConfig] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.listener = listener
        self.player = player
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
            # TEMPORAL: diagnóstico de captura de audio, remover después de
            # confirmar si el problema es "no llega audio del micrófono" o
            # "llega audio pero la wake word nunca dispara".
            self.logger.info("escuchando...")
            while True:
                frame = self.listener.read_frame()
                nivel = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
                self.logger.info(f"audio detectado, nivel: {nivel:.1f}")
                if self.wake_word.process_frame(frame):
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

    async def run_forever(self) -> None:
        """Corre `run_once()` en loop hasta que se cancele la tarea."""
        self.logger.info(
            "Pipeline de voz arrancado, esperando wake word",
            wake_words=self.wake_word.get_wake_words(),
        )
        try:
            while True:
                await self.run_once()
        finally:
            await self.close()
