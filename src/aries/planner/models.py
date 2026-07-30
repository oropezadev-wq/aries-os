"""Formas de datos del Planner: la intención estructurada que se le pide al
LLM (validada con Pydantic — `docs/specs/Planner.spec.md`, decisión 2) y el
resultado que `Planner.handle()` devuelve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.agent import ActionResult


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
    error: str | None = None
