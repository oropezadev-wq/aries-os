"""Brain: genera la respuesta en lenguaje natural que se le muestra al
usuario, a partir del resultado de un plan ya ejecutado por el Planner.

Alcance deliberadamente mínimo (`docs/specs/Planner.spec.md`, decisión 9):
esto SOLO arma un prompt con el resultado del plan y llama a
`ILLMProvider.complete()`. Sin lógica de tono/personalidad, sin memoria de
conversación propia, sin nada más — separar más responsabilidades acá
antes de que exista una segunda razón real para hacerlo sería abstracción
prematura. `Planner` importa `generate_response()` y no tiene su propia
lógica de fraseo.
"""

from __future__ import annotations

from structlog.stdlib import BoundLogger

from ..contracts.llm import ILLMProvider
from ..logging import get_logger

_logger: BoundLogger = get_logger("aries.brain")


async def generate_response(
    llm_provider: ILLMProvider,
    user_input: str,
    plan_success: bool,
    step_summaries: list[str],
) -> str:
    """Genera una respuesta en lenguaje natural para el usuario a partir del
    resultado de un plan ya ejecutado.

    Nunca propaga excepciones: si el LLM falla o devuelve algo vacío, se
    devuelve un mensaje de fallback genérico en vez de dejar que la
    excepción llegue al caller — mismo criterio de "nunca propagar" que el
    resto del proyecto (`docs/contracts/IAgent.md`).
    """
    prompt = _build_prompt(user_input, plan_success, step_summaries)

    try:
        response = await llm_provider.complete(prompt, temperature=0.7)
    except Exception as error:
        _logger.warning("Brain: el LLM falló al generar la respuesta", error=str(error))
        return _fallback_response(plan_success)

    content = response.content.strip()
    return content or _fallback_response(plan_success)


def _build_prompt(user_input: str, plan_success: bool, step_summaries: list[str]) -> str:
    resultado = "se completó con éxito" if plan_success else "falló"
    pasos = "\n".join(f"- {summary}" for summary in step_summaries) or "(sin pasos ejecutados)"
    return (
        "Sos el asistente de Aries OS. El usuario pidió lo siguiente:\n"
        f'"{user_input}"\n\n'
        f"El plan para cumplirlo {resultado}. Resultado de cada paso:\n"
        f"{pasos}\n\n"
        "Respondé en español, en un párrafo corto y natural, contándole al "
        "usuario qué pasó. No repitas la lista de pasos textualmente ni "
        "menciones detalles técnicos internos."
    )


def _fallback_response(plan_success: bool) -> str:
    if plan_success:
        return "Listo, se completó la acción solicitada."
    return "No se pudo completar la acción solicitada."
