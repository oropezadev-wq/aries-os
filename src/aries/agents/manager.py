"""AgentManager: registra los `IAgent` concretos del proyecto y rutea
solicitudes de ejecución (agente + acción + parámetros) hacia el agente
correcto.

Alcance deliberado: **registro explícito, no descubrimiento automático.**
No escanea `agents/` en disco ni carga plugins dinámicamente — eso es
responsabilidad de `plugins/` (0% implementado hoy, fuera de alcance de
esta tarea). `AgentManager` simplemente conoce, al construirse, los 4
`IAgent` concretos que ya existen (`FileSystemAgent`, `ProcessAgent`,
`GitAgent`, `DatabaseAgent`) y permite registrar otros manualmente vía
`register()` — útil para tests con agentes fake, y para cuando exista un
mecanismo de carga de plugins que registre agentes adicionales.

`dispatch()` nunca propaga excepciones ni las produce por su cuenta: valida
agente/acción y retorna `ActionResult(status=FAILED, error=...)` si algo no
existe, exactamente igual que cualquier `IAgent.execute()` — mismo criterio
en todo el proyecto (ver `docs/contracts/IAgent.md`). El `ActionResult` que
devuelve un agente real se retorna tal cual, sin transformarlo ni envolverlo.
"""

from __future__ import annotations

from typing import Any

from structlog.stdlib import BoundLogger

from ..contracts.agent import ActionResult, ActionStatus, IAgent
from ..logging import get_logger
from .database import DatabaseAgent
from .filesystem import FileSystemAgent
from .git import GitAgent
from .process import ProcessAgent


class AgentManager:
    """Registro y ruteo de ejecuciones hacia los `IAgent` del sistema."""

    def __init__(self, agents: list[IAgent] | None = None) -> None:
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._agents: dict[str, IAgent] = {}
        for agent in agents if agents is not None else self._default_agents():
            self.register(agent)

    @staticmethod
    def _default_agents() -> list[IAgent]:
        """Los 4 `IAgent` concretos existentes hoy en el proyecto."""
        return [FileSystemAgent(), ProcessAgent(), GitAgent(), DatabaseAgent()]

    def register(self, agent: IAgent) -> None:
        """Registra (o reemplaza) un agente bajo su `get_agent_name()`."""
        name = agent.get_agent_name()
        if name in self._agents:
            self.logger.warning("Reemplazando agente ya registrado", agent_name=name)
        self._agents[name] = agent
        self.logger.info("Agente registrado", agent_name=name)

    def unregister(self, agent_name: str) -> bool:
        """Remueve un agente registrado bajo `agent_name`.

        Cambio mínimo agregado para que `PluginRegistry.unload()` pueda
        deshacer el `register()` que hizo al cargar un plugin (vía
        `PluginAgentAdapter`, ver `plugins/agent_adapter.py`) — los 4
        `IAgent` nativos nunca se desregistran hoy (nada los carga/descarga
        en runtime), pero un plugin sí puede descargarse en cualquier
        momento (`docs/contracts/IPlugin.md`, principio de independencia),
        y dejarlo registrado tras `unload()` sería despachar acciones hacia
        una instancia ya apagada.

        Returns:
            `True` si había un agente con ese nombre y se removió, `False`
            si no había nada registrado.
        """
        if agent_name not in self._agents:
            return False
        del self._agents[agent_name]
        self.logger.info("Agente removido", agent_name=agent_name)
        return True

    def get_agent(self, agent_name: str) -> IAgent | None:
        """Devuelve el agente registrado bajo `agent_name`, o `None`."""
        return self._agents.get(agent_name)

    def list_agents(self) -> dict[str, list[str]]:
        """Agentes registrados y sus capacidades, para que el Planner (u
        otro consumidor) sepa qué agente invocar para qué acción."""
        return {name: agent.get_capabilities() for name, agent in self._agents.items()}

    async def dispatch(self, agent_name: str, action: str, **kwargs: Any) -> ActionResult:
        """Valida agente + acción y ejecuta, devolviendo el `ActionResult`
        del agente sin transformarlo. Nunca lanza excepciones."""
        agent = self._agents.get(agent_name)
        if agent is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=(
                    f"Agente desconocido: '{agent_name}'. "
                    f"Agentes registrados: {sorted(self._agents)}"
                ),
            )

        capabilities = agent.get_capabilities()
        if action not in capabilities:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=(
                    f"El agente '{agent_name}' no soporta la acción '{action}'. "
                    f"Acciones disponibles: {capabilities}"
                ),
            )

        return await agent.execute(action, **kwargs)
