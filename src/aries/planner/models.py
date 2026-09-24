"""Formas de datos del Planner: la intención estructurada que se le pide al
LLM (validada con Pydantic — `docs/specs/Planner.spec.md`, decisión 2) y el
resultado que `Planner.handle()` devuelve.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.agent import ActionResult

# Auditoría de seguridad 2026-09-23 (hallazgo CRÍTICO #1): frase de
# confirmación EXACTA para acciones destructivas — antes vivía solo en
# `voice/pipeline.py` (decisión 5 de `docs/specs/Voice.spec.md`), movida
# acá porque ahora la verifica el propio Planner (fuente única de verdad
# para cualquier consumidor — voz, HTTP directo, lo que sea — en vez de
# confiar en un `confirmed: bool` que el cliente podía afirmar sin que
# mediara ninguna confirmación real). Ver `Planner.confirm()`.
CONFIRMATION_PHRASE = "confirmo"


def normalize_confirmation_text(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación — para no fallar por un signo
    de puntuación o mayúscula fantasma de la transcripción."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", "", text.lower())
    return text.strip()


class PlannedStep(BaseModel):
    """Un paso del plan: qué agente, qué acción, con qué parámetros."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ParsedIntent(BaseModel):
    """La intención estructurada que el LLM debe devolver como JSON.

    `steps` vacío significa "ninguna capacidad disponible cubre este
    pedido" — el Planner lo trata como fallo explícito, nunca como éxito
    silencioso (`docs/specs/Planner.spec.md`, sección 2, punto 4).
    """

    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float | None = None
    steps: list[PlannedStep] = Field(default_factory=list)


@dataclass
class PlanExecutionResult:
    """Lo que devuelve `Planner.handle()`. Ver `docs/specs/Planner.spec.md`,
    sección 4 — normalizado a `ActionResult` (decisión 8)."""

    plan_id: str
    success: bool
    steps: list[ActionResult] = field(default_factory=list)
    response_text: str | None = None
    needs_confirmation: bool = False
    # Id opaco de la acción pendiente cuando needs_confirmation=True — se
    # manda de vuelta a `Planner.confirm()`, nunca a `handle()`. Auditoría
    # de seguridad 2026-09-23, hallazgo CRÍTICO #1.
    confirmation_id: str | None = None
    error: str | None = None
