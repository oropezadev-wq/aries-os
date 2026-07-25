from __future__ import annotations

from dataclasses import dataclass

from ..events.event import BaseEvent


@dataclass(frozen=True)
class KernelInitializedEvent(BaseEvent):
    """Evento publicado cuando el kernel se inicializa correctamente."""
    pass


@dataclass(frozen=True)
class KernelShutdownEvent(BaseEvent):
    """Evento publicado cuando el kernel se apaga correctamente."""
    pass
