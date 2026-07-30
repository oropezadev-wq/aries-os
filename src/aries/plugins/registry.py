"""plugins/registry.py — PluginRegistry: trackea plugins cargados/activos,
su metadata y sus hooks conectados al Event Bus **real** (no un mock ni un
bus separado — la misma instancia de `IEventBus` que usa el resto del
sistema, inyectada por constructor, mismo patrón que `Kernel`).

`load()`/`unload()` nunca propagan excepciones — devuelven
`(éxito: bool, error: str | None)`, mismo criterio que todo `IAgent.execute()`
en este proyecto: cualquier falla (manifest inválido, módulo que no
importa, `initialize()` que lanza o devuelve `False`, requisito faltante)
se captura y se reporta como resultado, nunca como traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from structlog.stdlib import BoundLogger

from ..agents.manager import AgentManager
from ..contracts.event_bus import Handler, IEventBus
from ..contracts.plugin import IPlugin, PluginMetadata
from ..core.events import KernelInitializedEvent, KernelShutdownEvent, KernelStartingEvent
from ..events.event import BaseEvent
from ..logging import get_logger
from ..planner.events import (
    ActionCompletedEvent,
    ActionFailedEvent,
    ActionStartedEvent,
    ErrorOccurredEvent,
    IntentDetectedEvent,
    MemoryStoredEvent,
    PlanCreatedEvent,
    PlanExecutedEvent,
)
from .agent_adapter import PluginAgentAdapter
from .context import build_plugin_context
from .events import PluginLoadedEvent, PluginUnloadedEvent
from .installer import missing_requirements
from .loader import LoaderError, load_plugin
from .manifest import ManifestError

# Mapa contrato (docs/contracts/IPlugin.md, "Eventos disponibles") -> clase
# real de BaseEvent. `None` = evento documentado en el contrato que
# TODAVÍA NO EXISTE como clase concreta. Actualizado para reflejar el
# catálogo real tras las tareas de Planner y Kernel (`core/events.py`,
# `planner/events.py`) — quedan solo 2 de los 15 sin implementar:
# `MEMORY_DELETED` y `MEMORY_SEARCHED` (bloqueados porque `IMemory.delete()`
# y `IMemory.search()` no publican eventos todavía, ver PROGRESS.md).
# Un plugin puede seguir declarando un hook para uno de estos dos nombres:
# PluginRegistry no lo rechaza, pero jamás va a dispararse hasta que el
# evento real exista — queda registrado en `LoadedPlugin.unavailable_hooks`
# y se loguea una advertencia, en vez de fallar silenciosamente o mentir
# que está "conectado".
CONTRACT_EVENTS: dict[str, type[BaseEvent] | None] = {
    "KERNEL_STARTING": KernelStartingEvent,
    "KERNEL_READY": KernelInitializedEvent,  # equivalencia semántica, ver PROGRESS.md
    "KERNEL_SHUTDOWN": KernelShutdownEvent,
    "INTENT_DETECTED": IntentDetectedEvent,
    "PLAN_CREATED": PlanCreatedEvent,
    "PLAN_EXECUTED": PlanExecutedEvent,
    "ACTION_STARTED": ActionStartedEvent,
    "ACTION_COMPLETED": ActionCompletedEvent,
    "ACTION_FAILED": ActionFailedEvent,
    "MEMORY_STORED": MemoryStoredEvent,
    "MEMORY_DELETED": None,
    "MEMORY_SEARCHED": None,
    "ERROR_OCCURRED": ErrorOccurredEvent,
    "PLUGIN_LOADED": PluginLoadedEvent,
    "PLUGIN_UNLOADED": PluginUnloadedEvent,
}


@dataclass
class LoadedPlugin:
    """Estado de un plugin activo, trackeado por `PluginRegistry`."""

    metadata: PluginMetadata
    instance: IPlugin
    plugin_dir: Path
    connected_hooks: dict[str, Handler] = field(default_factory=dict)
    unavailable_hooks: list[str] = field(default_factory=list)


class PluginRegistry:
    """Registro central de plugins: carga, inicializa, conecta hooks al
    Event Bus real, descarga."""

    def __init__(
        self,
        event_bus: IEventBus,
        settings: Any = None,
        agent_manager: AgentManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._settings = settings
        self._agent_manager = agent_manager
        self._plugins: dict[str, LoadedPlugin] = {}
        self.logger: BoundLogger = get_logger(self.__class__.__name__)

    def list_plugins(self) -> dict[str, PluginMetadata]:
        """Nombre de plugin -> su metadata, para introspección externa."""
        return {name: entry.metadata for name, entry in self._plugins.items()}

    def get_plugin(self, name: str) -> IPlugin | None:
        entry = self._plugins.get(name)
        return entry.instance if entry else None

    def get_loaded_entry(self, name: str) -> LoadedPlugin | None:
        """Acceso al estado interno completo (hooks conectados/no
        disponibles) — pensado para tests e introspección, no para uso
        normal de negocio."""
        return self._plugins.get(name)

    async def load(self, plugin_dir: str | Path) -> tuple[bool, str | None]:
        """Carga, valida e inicializa el plugin en `plugin_dir`.

        Pasos: parsear manifest -> importar/instanciar -> verificar
        `requires` -> `initialize(context)` -> `register_hooks()` ->
        conectar al Event Bus real -> publicar `PluginLoadedEvent`.

        Nunca propaga excepciones. Retorna `(True, None)` en éxito, o
        `(False, mensaje_de_error)` en cualquier punto de falla.
        """
        plugin_dir = Path(plugin_dir)

        try:
            return await self._load_impl(plugin_dir)
        except Exception as error:  # red de seguridad final — ver docstring de clase
            message = f"Error inesperado al cargar el plugin desde {plugin_dir}: {error}"
            self.logger.error(message)
            return False, message

    async def _load_impl(self, plugin_dir: Path) -> tuple[bool, str | None]:
        try:
            metadata, instance = load_plugin(plugin_dir)
        except (ManifestError, LoaderError) as error:
            message = str(error)
            self.logger.warning("No se pudo cargar el plugin", plugin_dir=str(plugin_dir), error=message)
            return False, message

        if metadata.name in self._plugins:
            message = f"Ya hay un plugin registrado con el nombre '{metadata.name}'"
            self.logger.warning(message)
            return False, message

        missing = missing_requirements(metadata, loaded_plugin_names=set(self._plugins))
        if missing:
            message = f"Faltan requisitos para '{metadata.name}': {missing}"
            self.logger.warning(message)
            return False, message

        context = build_plugin_context(self._event_bus, metadata.name, self._settings)

        try:
            initialized = await instance.initialize(context)
        except Exception as error:
            message = f"initialize() de '{metadata.name}' lanzó una excepción: {error}"
            self.logger.error(message)
            return False, message

        if not initialized:
            message = f"initialize() de '{metadata.name}' retornó False"
            self.logger.warning(message)
            return False, message

        try:
            hooks = instance.register_hooks()
        except Exception as error:
            # El plugin ya se inicializó (pudo abrir recursos) pero no
            # pudimos conectar sus hooks — lo apagamos para no dejarlo a
            # medio activar.
            await self._safe_shutdown(instance, metadata.name)
            message = f"register_hooks() de '{metadata.name}' lanzó una excepción: {error}"
            self.logger.error(message)
            return False, message

        entry = LoadedPlugin(metadata=metadata, instance=instance, plugin_dir=plugin_dir)

        for event_name, handler in hooks.items():
            event_class = CONTRACT_EVENTS.get(event_name)
            if event_class is None:
                entry.unavailable_hooks.append(event_name)
                self.logger.warning(
                    "Hook declarado para un evento que todavía no existe como BaseEvent real",
                    plugin=metadata.name,
                    event_name=event_name,
                )
                continue
            await self._event_bus.subscribe(event_class, handler)
            entry.connected_hooks[event_name] = handler

        self._plugins[metadata.name] = entry

        if self._agent_manager is not None:
            # Mismo camino que los 4 IAgent nativos: el plugin queda
            # dispatchable vía AgentManager.dispatch() sin que AgentManager
            # sepa que está hablando con un plugin (ver
            # plugins/agent_adapter.py y docs/contracts/IPlugin.md).
            self._agent_manager.register(PluginAgentAdapter(instance))

        self.logger.info(
            "Plugin cargado",
            plugin=metadata.name,
            version=metadata.version,
            hooks_conectados=list(entry.connected_hooks),
            hooks_no_disponibles=entry.unavailable_hooks,
            registrado_en_agent_manager=self._agent_manager is not None,
        )

        await self._event_bus.publish(
            PluginLoadedEvent(plugin_name=metadata.name, version=metadata.version)
        )
        return True, None

    async def unload(self, name: str) -> tuple[bool, str | None]:
        """Desconecta los hooks del plugin, llama a `shutdown()` y lo
        remueve del registro. Nunca propaga excepciones."""
        try:
            return await self._unload_impl(name)
        except Exception as error:  # red de seguridad final, ver load()
            message = f"Error inesperado al descargar el plugin '{name}': {error}"
            self.logger.error(message)
            return False, message

    async def _unload_impl(self, name: str) -> tuple[bool, str | None]:
        entry = self._plugins.get(name)
        if entry is None:
            message = f"No hay ningún plugin cargado con el nombre '{name}'"
            self.logger.warning(message)
            return False, message

        for event_name, handler in entry.connected_hooks.items():
            event_class = CONTRACT_EVENTS[event_name]
            assert event_class is not None  # invariante: solo se conectan hooks con clase real
            await self._event_bus.unsubscribe(event_class, handler)

        if self._agent_manager is not None:
            self._agent_manager.unregister(name)

        shutdown_ok = await self._safe_shutdown(entry.instance, name)

        del self._plugins[name]
        self.logger.info("Plugin descargado", plugin=name, shutdown_ok=shutdown_ok)

        await self._event_bus.publish(PluginUnloadedEvent(plugin_name=name))

        if not shutdown_ok:
            return False, f"'{name}' se descargó, pero shutdown() falló o retornó False"
        return True, None

    async def _safe_shutdown(self, instance: IPlugin, name: str) -> bool:
        try:
            return bool(await instance.shutdown())
        except Exception as error:
            self.logger.error("shutdown() lanzó una excepción", plugin=name, error=str(error))
            return False
