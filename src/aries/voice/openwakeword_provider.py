"""voice/openwakeword_provider.py — implementación default de
`IWakeWordProvider` usando `openwakeword` (ver
`docs/contracts/IWakeWordProvider.md`, decisión 1 de
`docs/specs/Voice.spec.md`).
"""

from __future__ import annotations

import numpy as np

from ..contracts.wake_word import IWakeWordProvider, WakeWordDetection
from ..exceptions import VoiceError
from ..logging import get_logger

FRAME_SIZE = 1280  # 80ms @ 16kHz — tamaño de frame fijo que openWakeWord espera

DEFAULT_WAKE_WORD_MODEL = "hey_jarvis"  # no existe todavía un modelo "Aries" entrenado


class OpenWakeWordProvider(IWakeWordProvider):
    """Detecta wake words sobre frames de audio usando `openwakeword`.

    `openwakeword`/`onnxruntime` se importan de forma diferida (dentro de
    `__init__`, no a nivel de módulo) — dependencia pesada opcional (extra
    `voice`).
    """

    def __init__(
        self,
        wakeword_models: list[str] | None = None,
        threshold: float = 0.5,
        inference_framework: str = "onnx",
    ) -> None:
        try:
            from openwakeword.model import Model
        except ImportError as error:
            raise VoiceError(
                "openwakeword no está instalado — instalar el extra 'voice' del proyecto"
            ) from error

        self._threshold = threshold
        self._wakeword_names = list(wakeword_models) if wakeword_models else [DEFAULT_WAKE_WORD_MODEL]
        self.logger = get_logger(self.__class__.__name__)

        try:
            # `Model.__init__` muta en el lugar la lista `wakeword_models`
            # que recibe (reemplaza el nombre amigable por la ruta
            # resuelta del archivo) — verificado empíricamente con un test
            # real, no documentado por la librería. Se le pasa una copia
            # para que `self._wakeword_names` conserve los nombres
            # amigables originales (lo que `get_wake_words()` debe
            # devolver).
            self._model = Model(
                wakeword_models=list(self._wakeword_names), inference_framework=inference_framework
            )
        except Exception as error:
            raise VoiceError(f"No se pudo cargar el/los modelo(s) de wake word: {error}") from error

    def process_frame(self, frame: np.ndarray) -> list[WakeWordDetection]:
        if not isinstance(frame, np.ndarray):
            raise VoiceError("El frame de audio debe ser un numpy.ndarray")

        try:
            predictions = self._model.predict(frame)
        except Exception as error:
            raise VoiceError(f"Error al procesar el frame de audio: {error}") from error

        detections = [
            WakeWordDetection(name=name, score=float(score))
            for name, score in predictions.items()
            if score >= self._threshold
        ]
        if detections:
            self.logger.info(
                "Wake word detectada",
                detections=[(d.name, d.score) for d in detections],
            )
        return detections

    def frame_size(self) -> int:
        return FRAME_SIZE

    async def is_available(self) -> bool:
        return self._model is not None

    def get_wake_words(self) -> list[str]:
        return list(self._wakeword_names)
