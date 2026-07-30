"""Contrato: Proveedor de detección de wake word

Define cómo detectar una palabra/frase de activación sobre un stream de
audio continuo sin acoplar el resto del sistema a un motor específico —
ver `docs/contracts/IWakeWordProvider.md`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class WakeWordDetection:
    """Una wake word detectada en un frame de audio."""

    name: str
    score: Optional[float] = None


class IWakeWordProvider(ABC):
    """Interface para proveedores de detección de wake word.

    `process_frame()` es deliberadamente síncrono (a diferencia del resto
    de los contratos de proveedores de este proyecto) — ver
    `docs/contracts/IWakeWordProvider.md` para el porqué: se llama en un
    loop de tiempo real, frame a frame, en lockstep con una lectura
    bloqueante del micrófono.
    """

    @abstractmethod
    def process_frame(self, frame: np.ndarray) -> list[WakeWordDetection]:
        """Procesa un frame de audio (int16, mono, `frame_size()` samples)
        y devuelve las wake words detectadas en él (vacía si ninguna)."""
        ...

    @abstractmethod
    def frame_size(self) -> int:
        """Cantidad exacta de samples que `process_frame()` espera."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Verifica que el/los modelo(s) estén cargados y listos."""
        ...

    @abstractmethod
    def get_wake_words(self) -> list[str]:
        """Nombres de las wake words que este proveedor puede detectar."""
        ...
