from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from ..types import EventData


@dataclass(frozen=True)
class BaseEvent:
    """Modelo base para eventos tipados en Aries OS.

    `event_type` es el nombre corto de la clase y se mantiene por compatibilidad.
    `event_id` es el identificador estable utilizado internamente por el Event Bus
    para evitar colisiones entre eventos definidos en distintos módulos o plugins.

    Nota: toda subclase que agregue campos propios DEBE decorarse con
    `@dataclass(frozen=True)` también, o los campos nuevos no se comportarán como
    campos de dataclass y Python rechazará la herencia.
    """

    metadata: EventData = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", self.__class__.__name__)

    @property
    def event_id(self) -> str:
        """Identificador estable del evento basado en módulo y qualname."""
        return f"{self.__class__.__module__}.{self.__class__.__qualname__}"

    def to_dict(self) -> EventData:
        event_payload = asdict(self)
        event_payload["event_type"] = self.event_type
        event_payload["timestamp"] = self.timestamp.isoformat()
        return event_payload
