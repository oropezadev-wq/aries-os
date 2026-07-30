"""plugins/agent_adapter.py — adapta un `IPlugin` ya cargado para que
`AgentManager` pueda tratarlo exactamente como un `IAgent` nativo más, sin
que `AgentManager`/`dispatch()`/el Planner necesiten saber que están
hablando con un plugin en vez de con uno de los 4 agentes nativos (ver
`docs/contracts/IPlugin.md`, sección `execute()`).

Existe porque `IPlugin` e `IAgent` son contratos distintos con superficies
parcialmente distintas: ambos ya comparten `execute()`/`get_capabilities()`
(desde que `IPlugin.md` incorporó `execute()`), pero `IPlugin` no define
`get_agent_name()`/`requires_confirmation()`/`is_available()` — este
adapter completa esos tres delegando a lo que `IPlugin` sí ofrece, o con un
default conservador donde el contrato de plugins simplemente no define el
concepto todavía (ver el docstring de cada método).
"""

from __future__ import annotations

from typing import Any

from ..contracts.agent import ActionResult, IAgent
from ..contracts.plugin import IPlugin


class PluginAgentAdapter(IAgent):
    """Envuelve un `IPlugin` ya cargado para registrarlo en `AgentManager`."""

    def __init__(self, plugin: IPlugin) -> None:
        self._plugin = plugin

    async def execute(self, action: str, **kwargs: Any) -> ActionResult:
        return await self._plugin.execute(action, **kwargs)

    def get_capabilities(self) -> list[str]:
        return self._plugin.get_capabilities()

    def requires_confirmation(self, action: str, **kwargs: Any) -> bool:
        """`docs/contracts/IPlugin.md` no define un mecanismo de
        confirmación por acción (a diferencia de `IAgent`) — por ahora,
        ninguna acción de un plugin pide confirmación. Límite conocido del
        contrato actual, documentado en PROGRESS.md, no un olvido."""
        return False

    async def is_available(self) -> bool:
        """Un plugin ya cargado por `PluginRegistry` se considera
        disponible — a diferencia de `ProcessAgent`/`GitAgent`, que
        verifican el entorno en cada llamada, `IPlugin` no tiene un
        concepto de disponibilidad más allá de "está cargado"."""
        return True

    def get_agent_name(self) -> str:
        return self._plugin.get_metadata().name
