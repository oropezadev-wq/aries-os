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

import dataclasses
import json
import uuid
from typing import Any

import redis.asyncio as redis_asyncio
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
from .models import (
    CONFIRMATION_PHRASE,
    ParsedIntent,
    PlanExecutionResult,
    PlannedStep,
    normalize_confirmation_text,
)

_MAX_INTENT_ATTEMPTS = 2  # intento inicial + 1 reintento de corrección (decisión 2)
_RECENT_CONTEXT_LIMIT = 5  # últimos N intercambios de la sesión que se incluyen en el prompt
_PENDING_CONFIRMATION_KEY_PREFIX = "aries:pending_confirmation:"


class Planner:
    """Orquesta: texto de usuario -> intención -> plan -> ejecución -> respuesta."""

    def __init__(
        self,
        llm_provider: ILLMProvider,
        agent_manager: AgentManager,
        event_bus: IEventBus,
        memory: IMemory,
        redis_client: redis_asyncio.Redis | None = None,
        pending_confirmation_ttl_seconds: float = 120.0,
        intent_llm_max_tokens: int = 512,
    ) -> None:
        self.llm_provider = llm_provider
        self.agent_manager = agent_manager
        self.event_bus = event_bus
        self.memory = memory
        self._intent_llm_max_tokens = intent_llm_max_tokens
        # Auditoría de seguridad 2026-09-23, hallazgo CRÍTICO #1: dónde vive
        # una acción pendiente de confirmación entre el pedido original y
        # `confirm()`. Opcional (default None) para no romper la
        # construcción de un Planner en contextos que no ejercitan
        # confirmación — sin cliente, cualquier acción que la necesite
        # falla con un error explícito en vez de fingir que puede
        # confirmarse (ver `_execute_plan`).
        self._redis_client = redis_client
        self._pending_confirmation_ttl_seconds = pending_confirmation_ttl_seconds
        self.logger: BoundLogger = get_logger(self.__class__.__name__)

    async def handle(self, user_input: str, session_id: str | None = None) -> PlanExecutionResult:
        """Punto de entrada único para un pedido NUEVO del usuario. Nunca
        lanza excepciones. Ya no acepta `confirmed: bool` (auditoría de
        seguridad 2026-09-23, hallazgo CRÍTICO #1) — una acción que
        necesita confirmación se confirma vía `confirm()`, nunca
        reafirmando este mismo pedido con un flag que el propio cliente
        controla sin que medie ninguna verificación real."""
        if not isinstance(user_input, str) or not user_input.strip():
            return PlanExecutionResult(plan_id="", success=False, error="user_input no puede estar vacío")

        try:
            result = await self._handle_impl(user_input, session_id)
        except Exception as error:  # red de seguridad final, ver docstring de clase
            self.logger.error("Error inesperado en Planner.handle", error=str(error))
            await self._safe_publish(
                ErrorOccurredEvent(source="Planner.handle", error=str(error), metadata=self._meta(session_id))
            )
            result = PlanExecutionResult(plan_id="", success=False, error=f"Error inesperado: {error}")

        await self._remember_exchange(user_input, session_id, result)
        return result

    async def confirm(
        self, confirmation_id: str, confirmation_text: str, session_id: str | None = None
    ) -> PlanExecutionResult:
        """Confirma (o rechaza) una acción pendiente de `handle()`. Nunca
        lanza excepciones — mismo criterio que `handle()`.

        Auditoría de seguridad 2026-09-23, hallazgo CRÍTICO #1: el servidor
        NUNCA acepta una confirmación que el cliente simplemente afirme —
        `confirmation_id` referencia una acción concreta ya propuesta
        (guardada en Redis, de un solo uso, con TTL — `_pop_pending_confirmation`
        la borra al leerla, así que un id ya usado o vencido no sirve dos
        veces), y `confirmation_text` se compara acá, del lado del
        servidor, contra `CONFIRMATION_PHRASE` — la MISMA regla que ya
        exigía la voz (antes solo la verificaba `VoicePipeline`, nunca el
        servidor; ver `docs/specs/Voice.spec.md` decisión 5 y
        `docs/audits/2026-09-23-security-audit.md`)."""
        user_input_for_memory = f'(confirmación, id={confirmation_id})'  # fallback si el id no existe/expiró
        try:
            result, user_input_for_memory = await self._confirm_impl(confirmation_id, confirmation_text, session_id)
        except Exception as error:  # red de seguridad final, mismo criterio que handle()
            self.logger.error("Error inesperado en Planner.confirm", error=str(error))
            await self._safe_publish(
                ErrorOccurredEvent(source="Planner.confirm", error=str(error), metadata=self._meta(session_id))
            )
            result = PlanExecutionResult(plan_id="", success=False, error=f"Error inesperado: {error}")

        await self._remember_exchange(user_input_for_memory, session_id, result)
        return result

    async def _confirm_impl(
        self, confirmation_id: str, confirmation_text: str, session_id: str | None
    ) -> tuple[PlanExecutionResult, str]:
        pending = await self._pop_pending_confirmation(confirmation_id)
        if pending is None:
            result = PlanExecutionResult(
                plan_id="",
                success=False,
                error="La acción pendiente no existe, ya se usó, o expiró — no se ejecutó nada.",
            )
            return result, f"(confirmación, id={confirmation_id})"

        user_input = pending["user_input"]
        plan_id = pending["plan_id"]
        meta = self._meta(pending.get("session_id"))
        results = [_action_result_from_dict(d) for d in pending["completed_results"]]

        if normalize_confirmation_text(confirmation_text) != CONFIRMATION_PHRASE:
            self.logger.info("Confirmación no coincide, se cancela la acción pendiente", confirmation_id=confirmation_id)
            result = PlanExecutionResult(
                plan_id=plan_id,
                success=False,
                steps=results,
                error="La confirmación no coincide, no se ejecutó nada.",
            )
            return result, user_input

        remaining_steps = [PlannedStep.model_validate(d) for d in pending["remaining_steps"]]
        result = await self._execute_plan(
            plan_id,
            remaining_steps,
            user_input,
            meta,
            results,
            session_id=pending.get("session_id"),
            skip_confirmation_for_first_step=True,
        )
        return result, user_input

    async def _handle_impl(self, user_input: str, session_id: str | None) -> PlanExecutionResult:
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

        return await self._execute_plan(plan_id, parsed.steps, user_input, meta, [], session_id=session_id)

    async def _execute_plan(
        self,
        plan_id: str,
        steps: list[PlannedStep],
        user_input: str,
        meta: dict[str, Any],
        results: list[ActionResult],
        session_id: str | None = None,
        skip_confirmation_for_first_step: bool = False,
    ) -> PlanExecutionResult:
        for index, step in enumerate(steps):
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

            # `skip_confirmation_for_first_step`: `confirm()` resume esta
            # llamada empezando justo por el paso que el usuario acaba de
            # aprobar — sin este chequeo, `requires_confirmation()` vuelve
            # a dar True para ESE MISMO paso y pide confirmación de nuevo
            # en loop. Solo aplica al primero (`index == 0`): si el plan
            # tiene pasos siguientes que también requieren confirmación,
            # esos sí la piden (la aprobación no se arrastra a una acción
            # distinta de la que se confirmó).
            needs_confirmation_now = agent.requires_confirmation(step.action, **step.parameters) and not (
                skip_confirmation_for_first_step and index == 0
            )
            if needs_confirmation_now:
                # `_execute_plan` solo se llama con pasos SIN confirmar
                # todavía — `confirm()` resume con los pasos restantes de
                # una acción ya aprobada, así que si UNO de esos restantes
                # también requiere confirmación, se pide una nueva (no se
                # arrastra la aprobación anterior a un paso distinto).
                if self._redis_client is None:
                    return PlanExecutionResult(
                        plan_id=plan_id,
                        success=False,
                        steps=results,
                        error=(
                            f"La acción '{step.action}' de '{step.agent_name}' requiere confirmación, "
                            "pero el servicio de confirmaciones (Redis) no está disponible — no se ejecutó nada."
                        ),
                    )
                confirmation_id = str(uuid.uuid4())
                await self._store_pending_confirmation(
                    confirmation_id, plan_id, user_input, session_id, steps[index:], results
                )
                return PlanExecutionResult(
                    plan_id=plan_id,
                    success=False,
                    steps=results,
                    needs_confirmation=True,
                    confirmation_id=confirmation_id,
                    error=(
                        f"La acción '{step.action}' de '{step.agent_name}' requiere confirmación. "
                        f"Decí \"{CONFIRMATION_PHRASE}\" para continuar."
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
                # format="json" restringe la salida a JSON válido a nivel
                # de decodificación (Ollama) en vez de depender de que el
                # modelo "se porte bien" — y max_tokens pone un techo para
                # que un modelo que no emite su token de parada falle
                # rápido y truncado en vez de colgar hasta el timeout
                # completo del cliente HTTP (hallazgo del supervisor,
                # 2026-09-25). Proveedores que no reconozcan estos kwargs
                # los ignoran vía **kwargs del contrato ILLMProvider.
                response = await self.llm_provider.complete(
                    prompt, temperature=0.0, format="json", max_tokens=self._intent_llm_max_tokens
                )
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
        # Reglas agregadas 2026-09-27, medidas contra qwen2.5:3b real (no
        # estimadas — ver PROGRESS.md, "checklist de pruebas del usuario"):
        # dos fallos reales encontrados en producción.
        # (1) "este repositorio"/"la carpeta actual" sin ruta concreta se
        #     copiaba literal como parámetro (ej. repo_path="este
        #     repositorio"), rompiendo la acción — cada agente ya tiene un
        #     default razonable (directorio actual) si el parámetro falta,
        #     nunca se usaba porque el modelo lo pisaba con la frase cruda.
        # (2) al agregar la regla de sintaxis Windows para process.*, el
        #     modelo empezó a preferir process.run_command con comandos
        #     crudos (`git status`, `del archivo`) en vez de las acciones
        #     específicas de git/filesystem que ya existen — bypasea la
        #     lógica de confirmación específica de cada agente. La regla de
        #     "acción específica antes que process.*" corrige esto (medido:
        #     sin ella, "listá la carpeta y hacé git status" pasaba por
        #     process.run_command("git status") en vez de git.status).
        rules = (
            "Reglas importantes:\n"
            '- Si el usuario se refiere a algo implícito sin dar un valor concreto '
            '(ej. "este repositorio", "la carpeta actual", "acá"), OMITÍ ese parámetro '
            '(no lo incluyas en "parameters") y ejecutá la acción igual — cada agente ya usa '
            "un valor por default razonable (el directorio actual) cuando el parámetro falta. "
            'Omitir el parámetro NO significa dejar "steps" vacío: la acción se ejecuta igual, '
            "solo sin ese parámetro.\n"
            "- Usá SIEMPRE la acción específica de un agente (git.*, filesystem.*, database.*) "
            "en vez de process.run_command/run_script cuando esa acción específica exista y "
            'cubra el pedido — ej. para git usá git.status, NUNCA process.run_command con '
            '"git status"; para archivos usá filesystem.delete_file/create_file, NUNCA '
            'process.run_command con "del"/"echo". process.run_command es SOLO para lo que '
            "ningún otro agente cubre.\n"
            "- Si de verdad necesitás process.run_command/run_script, generalo en sintaxis de "
            "Windows (cmd o PowerShell), nunca sintaxis Unix/bash."
        )
        return (
            "Sos el módulo de planificación de Aries OS, corriendo en Windows. "
            "Interpretá el pedido del usuario y devolvé ÚNICAMENTE un JSON "
            f"(sin texto adicional, sin bloques de markdown) con este esquema exacto:\n{schema}\n\n"
            f"Agentes disponibles y sus acciones:\n{catalog}\n"
            f"{context_block}\n"
            f"{rules}\n\n"
            'Si el pedido no se puede cumplir con NINGUNA acción disponible (no por faltar un '
            'parámetro que tiene default, sino porque ninguna acción del catálogo aplica), '
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
        pena recordar como "intercambio terminado"; el llamado a
        `confirm()` que efectivamente ejecute (o rechace) la acción sí se
        guarda. Nunca propaga excepciones."""
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

    # --- Confirmación server-side (auditoría de seguridad 2026-09-23) ------

    async def _store_pending_confirmation(
        self,
        confirmation_id: str,
        plan_id: str,
        user_input: str,
        session_id: str | None,
        remaining_steps: list[PlannedStep],
        completed_results: list[ActionResult],
    ) -> None:
        assert self._redis_client is not None  # narrowing: el caller ya lo chequeó
        payload = {
            "plan_id": plan_id,
            "user_input": user_input,
            "session_id": session_id,
            "remaining_steps": [step.model_dump() for step in remaining_steps],
            "completed_results": [dataclasses.asdict(r) for r in completed_results],
        }
        key = f"{_PENDING_CONFIRMATION_KEY_PREFIX}{confirmation_id}"
        await self._redis_client.set(key, json.dumps(payload), ex=max(1, int(self._pending_confirmation_ttl_seconds)))

    async def _pop_pending_confirmation(self, confirmation_id: str) -> dict[str, Any] | None:
        """Lee y borra en un solo paso (`GETDEL`, Redis >=6.2) — de un solo
        uso: un `confirmation_id` ya consumido (con éxito o no) no sirve
        una segunda vez, evita reintentos/replay contra la misma acción."""
        if self._redis_client is None:
            return None
        key = f"{_PENDING_CONFIRMATION_KEY_PREFIX}{confirmation_id}"
        raw = await self._redis_client.getdel(key)
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(raw)
        return data


def _action_result_from_dict(data: dict[str, Any]) -> ActionResult:
    return ActionResult(
        status=ActionStatus(data["status"]),
        output=data.get("output"),
        error=data.get("error"),
        data=data.get("data"),
        execution_time_ms=data.get("execution_time_ms", 0.0),
    )


def _extract_json(text: str) -> str:
    """Heurística de mejor esfuerzo para extraer JSON de una respuesta de
    LLM que puede venir envuelta en texto/markdown alrededor."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]
