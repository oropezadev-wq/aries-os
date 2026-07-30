"""Planner: interpreta el texto del usuario, arma un plan de pasos
(agente + acción + parámetros), lo ejecuta vía `AgentManager` y devuelve una
respuesta en lenguaje natural (generada por `brain.generate_response`).

Implementa las 9 decisiones de `docs/specs/Planner.spec.md` — cada método
de acá referencia la decisión que sigue, no las repite en prosa.

Mismo nivel de rigor que los `IAgent` concretos: `handle()` **nunca
propaga excepciones** — cualquier fallo (LLM caído, JSON inválido, agente
desconocido, acción no soportada, excepción inesperada) se captura y se
retorna como `PlanExecutionResult(success=False, error=...)`.

**Memory conectada (2026-07-26):** cada llamada a `handle()` guarda un
`MemoryItem` tipo `"conversation"` con el `user_input` y la respuesta (o el
error, si no hubo respuesta) del intercambio, y recupera los últimos
intercambios de la misma `session_id` antes de interpretar un nuevo pedido
— ver `_remember_exchange()`/`_recent_context()`. `session_id` sigue
viviendo en `metadata`, nunca en un campo dedicado (decisión 1).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError
from structlog.stdlib import BoundLogger

from ..agents.manager import AgentManager
from ..brain import generate_response
from ..contracts.agent import ActionResult, ActionStatus
from ..contracts.event_bus import IEventBus
from ..contracts.llm import ILLMProvider
from ..contracts.memory import IMemory
from ..events.event import BaseEvent
from ..logging import get_logger
from .events import (
    ActionCompletedEvent,
    ActionFailedEvent,
    ActionStartedEvent,
    ErrorOccurredEvent,
    IntentDetectedEvent,
    MemoryStoredEvent,
    PlanCreatedEvent,
    PlanExecutedEvent,
)
from .models import ParsedIntent, PlanExecutionResult, PlannedStep

_MAX_INTENT_ATTEMPTS = 2  # intento inicial + 1 reintento de corrección (decisión 2)
_RECENT_CONTEXT_LIMIT = 5  # últimos N intercambios de la sesión que se incluyen en el prompt


class Planner:
    """Orquesta: texto de usuario -> intención -> plan -> ejecución -> respuesta."""

    def __init__(
        self,
        llm_provider: ILLMProvider,
        agent_manager: AgentManager,
        event_bus: IEventBus,
        memory: IMemory,
    ) -> None:
        self.llm_provider = llm_provider
        self.agent_manager = agent_manager
        self.event_bus = event_bus
        self.memory = memory
        self.logger: BoundLogger = get_logger(self.__class__.__name__)

    async def handle(
        self,
        user_input: str,
        session_id: str | None = None,
        confirmed: bool = False,
    ) -> PlanExecutionResult:
        """Punto de entrada único del Planner. Nunca lanza excepciones."""
        if not isinstance(user_input, str) or not user_input.strip():
            return PlanExecutionResult(plan_id="", success=False, error="user_input no puede estar vacío")

        try:
            result = await self._handle_impl(user_input, session_id, confirmed)
        except Exception as error:  # red de seguridad final, ver docstring de clase
            self.logger.error("Error inesperado en Planner.handle", error=str(error))
            await self._safe_publish(
                ErrorOccurredEvent(source="Planner.handle", error=str(error), metadata=self._meta(session_id))
            )
            result = PlanExecutionResult(plan_id="", success=False, error=f"Error inesperado: {error}")

        await self._remember_exchange(user_input, session_id, result)
        return result

    async def _handle_impl(
        self, user_input: str, session_id: str | None, confirmed: bool
    ) -> PlanExecutionResult:
        plan_id = str(uuid.uuid4())
        meta = self._meta(session_id)

        context = await self._recent_context(session_id)
        parsed = await self._parse_intent(user_input, context)
        if parsed is None:
            error = "No se pudo interpretar la intención del usuario (el LLM no devolvió JSON válido tras reintentar)"
            await self._safe_publish(ErrorOccurredEvent(source="Planner.parse_intent", error=error, metadata=meta))
            return PlanExecutionResult(plan_id=plan_id, success=False, error="No se pudo interpretar tu pedido.")

        await self._safe_publish(
            IntentDetectedEvent(
                intent=parsed.intent, confidence=parsed.confidence, raw_input=user_input, metadata=meta
            )
        )

        if not parsed.steps:
            error = f"No encontré ninguna capacidad disponible para: {parsed.intent!r}"
            await self._safe_publish(ErrorOccurredEvent(source="Planner", error=error, metadata=meta))
            return PlanExecutionResult(plan_id=plan_id, success=False, error=error)

        steps_payload = [step.model_dump() for step in parsed.steps]
        await self._safe_publish(
            PlanCreatedEvent(plan_id=plan_id, steps=steps_payload, intent=parsed.intent, metadata=meta)
        )

        return await self._execute_plan(plan_id, parsed.steps, user_input, confirmed, meta)

    async def _execute_plan(
        self,
        plan_id: str,
        steps: list[PlannedStep],
        user_input: str,
        confirmed: bool,
        meta: dict[str, Any],
    ) -> PlanExecutionResult:
        results: list[ActionResult] = []

        for step in steps:
            agent = self.agent_manager.get_agent(step.agent_name)
            if agent is None:
                error = f"Agente desconocido: '{step.agent_name}'"
                await self._safe_publish(ErrorOccurredEvent(source="Planner", error=error, metadata=meta))
                await self._safe_publish(
                    PlanExecutedEvent(plan_id=plan_id, success=False, results=results, metadata=meta)
                )
                return PlanExecutionResult(plan_id=plan_id, success=False, steps=results, error=error)

            # Decisión 3 (Planner.spec.md): un Tool con la misma acción
            # tendría prioridad acá, antes de resolver contra AgentManager.
            # No hay ningún ITool concreto hoy, así que no hay nada que
            # consultar — este es el único punto de extensión para cuando
            # exista un ToolRegistry real.

            if agent.requires_confirmation(step.action, **step.parameters) and not confirmed:
                return PlanExecutionResult(
                    plan_id=plan_id,
                    success=False,
                    steps=results,
                    needs_confirmation=True,
                    error=(
                        f"La acción '{step.action}' de '{step.agent_name}' requiere "
                        "confirmación. Reintentá el mismo pedido con confirmed=True."
                    ),
                )

            await self._safe_publish(
                ActionStartedEvent(actor_type="agent", actor_name=step.agent_name, action=step.action, metadata=meta)
            )
            result = await self.agent_manager.dispatch(step.agent_name, step.action, **step.parameters)
            results.append(result)

            if result.status == ActionStatus.SUCCESS:
                await self._safe_publish(
                    ActionCompletedEvent(
                        actor_type="agent", actor_name=step.agent_name, action=step.action, metadata=meta
                    )
                )
                continue

            # Decisión 6 (Planner.spec.md): abortar el plan completo en el
            # primer fallo, sin ejecutar los pasos restantes.
            await self._safe_publish(
                ActionFailedEvent(
                    actor_type="agent",
                    actor_name=step.agent_name,
                    action=step.action,
                    error=result.error or "",
                    metadata=meta,
                )
            )
            await self._safe_publish(
                PlanExecutedEvent(plan_id=plan_id, success=False, results=results, metadata=meta)
            )
            response_text = await generate_response(
                self.llm_provider, user_input, False, [self._summarize(r) for r in results]
            )
            return PlanExecutionResult(
                plan_id=plan_id,
                success=False,
                steps=results,
                response_text=response_text,
                error=result.error or "La acción falló.",
            )

        await self._safe_publish(PlanExecutedEvent(plan_id=plan_id, success=True, results=results, metadata=meta))
        response_text = await generate_response(
            self.llm_provider, user_input, True, [self._summarize(r) for r in results]
        )
        return PlanExecutionResult(plan_id=plan_id, success=True, steps=results, response_text=response_text)

    # --- Interpretación de la intención (decisión 2) -----------------------

    async def _parse_intent(self, user_input: str, context: list[str]) -> ParsedIntent | None:
        prompt = self._build_intent_prompt(user_input, context)

        for attempt in range(_MAX_INTENT_ATTEMPTS):
            try:
                response = await self.llm_provider.complete(prompt, temperature=0.0)
            except Exception as error:
                self.logger.error("El LLM falló al interpretar la intención", error=str(error))
                return None

            parsed = self._try_parse(response.content)
            if parsed is not None:
                return parsed

            self.logger.warning(
                "Respuesta del LLM no validó contra ParsedIntent, reintentando" if attempt == 0 else
                "Segundo intento de interpretación también falló",
                attempt=attempt,
            )
            prompt = self._build_correction_prompt(user_input, response.content)

        return None

    @staticmethod
    def _try_parse(raw_text: str) -> ParsedIntent | None:
        try:
            data = json.loads(_extract_json(raw_text))
        except json.JSONDecodeError:
            return None
        try:
            return ParsedIntent.model_validate(data)
        except ValidationError:
            return None

    def _build_intent_prompt(self, user_input: str, context: list[str]) -> str:
        capabilities = self.agent_manager.list_agents()
        catalog = "\n".join(f"- {name}: {', '.join(actions)}" for name, actions in capabilities.items())
        schema = (
            '{"intent": "string", "confidence": number_or_null, '
            '"steps": [{"agent_name": "string", "action": "string", "parameters": {}}]}'
        )
        context_block = ""
        if context:
            history = "\n".join(context)
            context_block = f"\nContexto reciente de esta conversación (más antiguo primero):\n{history}\n"
        return (
            "Sos el módulo de planificación de Aries OS. Interpretá el pedido "
            "del usuario y devolvé ÚNICAMENTE un JSON (sin texto adicional, "
            f"sin bloques de markdown) con este esquema exacto:\n{schema}\n\n"
            f"Agentes disponibles y sus acciones:\n{catalog}\n"
            f"{context_block}\n"
            'Si el pedido no se puede cumplir con ninguna acción disponible, '
            'devolvé "steps": [].\n\n'
            f'Pedido del usuario: "{user_input}"'
        )

    @staticmethod
    def _build_correction_prompt(user_input: str, previous_response: str) -> str:
        return (
            "Tu respuesta anterior no era JSON válido para el esquema pedido:\n"
            f"{previous_response}\n\n"
            "Respondé de nuevo, ÚNICAMENTE con un JSON válido, sin texto "
            "adicional ni bloques de markdown, para este pedido:\n"
            f'"{user_input}"'
        )

    # --- Memoria de conversación ---------------------------------------------

    async def _recent_context(self, session_id: str | None, limit: int = _RECENT_CONTEXT_LIMIT) -> list[str]:
        """Últimos `limit` intercambios de la misma sesión, más antiguo
        primero. `IMemory` no soporta filtrar por `metadata` de forma
        nativa (decisión 1 de `Planner.spec.md`: `session_id` vive en
        `metadata`, no en un campo indexable) — se filtra del lado del
        Planner sobre `get_by_type("conversation")`. Nunca propaga
        excepciones: si Memory falla, sigue sin contexto en vez de romper
        el pedido actual."""
        if not session_id:
            return []

        try:
            items = await self.memory.get_by_type("conversation")
        except Exception as error:
            self.logger.error("No se pudo leer contexto de memoria", error=str(error))
            return []

        session_items = [item for item in items if item.metadata.get("session_id") == session_id]
        session_items.sort(key=lambda item: item.created_at)
        return [item.content for item in session_items[-limit:]]

    async def _remember_exchange(
        self, user_input: str, session_id: str | None, result: PlanExecutionResult
    ) -> None:
        """Guarda el intercambio completo en Memory y publica
        `MemoryStoredEvent`. Se salta explícitamente cuando
        `needs_confirmation` es `True` — todavía no pasó nada que valga la
        pena recordar como "intercambio terminado"; el próximo llamado con
        `confirmed=True` sí se guarda. Nunca propaga excepciones."""
        if result.needs_confirmation:
            return

        response_text = result.response_text or result.error or "(sin respuesta)"
        content = f"Usuario: {user_input}\nAries: {response_text}"
        metadata = {
            "session_id": session_id,
            "user_input": user_input,
            "response_text": result.response_text,
            "success": result.success,
            "plan_id": result.plan_id,
        }

        try:
            item = await self.memory.store(content, "conversation", metadata=metadata)
        except Exception as error:
            self.logger.error("No se pudo guardar el intercambio en memoria", error=str(error))
            return

        await self._safe_publish(
            MemoryStoredEvent(memory_id=item.id, memory_type=item.type, metadata=self._meta(session_id))
        )

    # --- Utilidades ----------------------------------------------------------

    @staticmethod
    def _summarize(result: ActionResult) -> str:
        if result.status == ActionStatus.SUCCESS:
            return result.output or "Acción completada."
        return f"Error: {result.error or 'desconocido'}"

    @staticmethod
    def _meta(session_id: str | None) -> dict[str, Any]:
        # Decisión 1 (Planner.spec.md): session_id vive en metadata, no en
        # un campo dedicado.
        return {"session_id": session_id} if session_id else {}

    async def _safe_publish(self, event: BaseEvent) -> None:
        try:
            await self.event_bus.publish(event)
        except Exception as error:
            self.logger.error("Fallo al publicar evento del Planner", event_type=type(event).__name__, error=str(error))


def _extract_json(text: str) -> str:
    """Heurística de mejor esfuerzo para extraer JSON de una respuesta de
    LLM que puede venir envuelta en texto/markdown alrededor."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]
