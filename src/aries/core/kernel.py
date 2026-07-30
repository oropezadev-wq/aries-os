"""Implementación básica del kernel de Aries OS."""

from __future__ import annotations

import asyncio
from pathlib import Path

from structlog.stdlib import BoundLogger

from ..agents.manager import AgentManager
from ..config.settings import Settings
from ..contracts.event_bus import IEventBus
from ..contracts.llm import ILLMProvider
from ..contracts.memory import IMemory
from ..exceptions import KernelError
from ..logging import get_logger


class Kernel:
    """Kernel central que administra el ciclo de vida del sistema."""

    def __init__(
        self,
        settings: Settings,
        memory: IMemory,
        llm_provider: ILLMProvider,
        event_bus: IEventBus,
        agent_manager: AgentManager,
    ) -> None:
        # Import diferido: si `PluginRegistry` se importara al nivel de
        # módulo de este archivo, se cerraría un ciclo real de import
        # (plugins.registry -> core.events -> paquete core -> core.kernel,
        # este mismo archivo, todavía a medio importar) — mismo criterio ya
        # usado en este archivo para `KernelInitializedEvent`/
        # `KernelShutdownEvent`. Importar dentro de `__init__` es seguro
        # porque para cuando alguien construye un `Kernel`, este módulo ya
        # terminó de importarse por completo.
        from ..plugins.registry import PluginRegistry

        self.settings = settings
        self.memory = memory
        self.llm_provider = llm_provider
        self.event_bus = event_bus
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._initialized = False
        self._running = False
        self._stop_event: asyncio.Event | None = None
        # `AgentManager` recibido por parámetro, ya NO construido acá — debe
        # ser el mismo objeto que usa el Planner en `api.py` (`_agent_manager`,
        # compartido vía el startup event de la app, mismo patrón que ya
        # usa `_memory`). Así, un plugin cargado por `Kernel.initialize()`
        # queda dispatchable de verdad vía `POST /message`, no solo dentro
        # de una copia aislada del Kernel. Antes de esta unificación, el
        # Kernel construía su propio `AgentManager()` independiente —ver
        # PROGRESS.md para el detalle de por qué eso no alcanzaba.
        self.agent_manager = agent_manager
        self.plugin_registry: PluginRegistry = PluginRegistry(
            event_bus, settings, agent_manager=self.agent_manager
        )

    async def initialize(self) -> None:
        """Configura los recursos iniciales del kernel."""
        if self._initialized:
            self.logger.warning("Kernel ya inicializado", state="initialized")
            return

        self.logger.info(
            "Inicializando kernel",
            environment=self.settings.environment,
            database_url=self.settings.database_url,
            redis_url=self.settings.redis_url,
        )

        disponible = await self.llm_provider.is_available()
        if not disponible:
            self.logger.warning("Proveedor LLM no disponible al iniciar")

        await asyncio.sleep(0.05)
        self._initialized = True
        from .events import KernelInitializedEvent

        await self.event_bus.publish(KernelInitializedEvent())
        await self.memory.store("Kernel inicializado", "context", importance=1)
        await self._load_plugins()
        self.logger.debug("Kernel inicializado correctamente")

    async def _load_plugins(self) -> None:
        """Descubre y carga los plugins válidos en `settings.plugins_dir`.

        Regla de aislamiento (a propósito distinta de la del Planner, donde
        un paso fallido aborta el resto del plan): acá los plugins son
        subsistemas independientes entre sí, así que si UNO falla al cargar
        (manifest inválido, `initialize()` que devuelve `False` o lanza,
        excepción de import) se registra el error y se sigue con los
        demás — un plugin roto nunca debe tumbar el Kernel ni bloquear la
        carga de los otros. `PluginRegistry.load()` ya nunca propaga
        excepciones por su cuenta (ver `plugins/registry.py`); acá solo se
        decide qué directorios intentar y se loguea el resultado de cada
        uno.

        Si `plugins_dir` no existe, no se carga ningún plugin — no es un
        error, es el estado esperado cuando todavía no hay plugins
        instalados.
        """
        plugins_dir = Path(self.settings.plugins_dir)
        if not plugins_dir.is_dir():
            self.logger.debug(
                "Directorio de plugins no existe, no se cargan plugins",
                plugins_dir=str(plugins_dir),
            )
            return

        try:
            candidate_dirs = sorted(
                (child for child in plugins_dir.iterdir() if child.is_dir()),
                key=lambda path: path.name,
            )
        except OSError as error:
            self.logger.warning(
                "No se pudo listar el directorio de plugins, no se cargan plugins",
                plugins_dir=str(plugins_dir),
                error=str(error),
            )
            return

        for plugin_dir in candidate_dirs:
            ok, error = await self.plugin_registry.load(plugin_dir)
            if ok:
                self.logger.info("Plugin cargado durante Kernel.initialize()", plugin_dir=str(plugin_dir))
            else:
                self.logger.warning(
                    "Un plugin no pudo cargar al iniciar el Kernel — se continúa con los demás",
                    plugin_dir=str(plugin_dir),
                    error=error,
                )

    async def _unload_plugins(self) -> None:
        """Descarga todos los plugins cargados, en orden inverso al de
        carga, vía `PluginRegistry.unload()`. Nunca propaga excepciones —
        mismo criterio que `_load_plugins()`."""
        for name in reversed(list(self.plugin_registry.list_plugins())):
            ok, error = await self.plugin_registry.unload(name)
            if not ok:
                self.logger.warning(
                    "Un plugin no se descargó limpiamente durante el shutdown del Kernel",
                    plugin=name,
                    error=error,
                )

    async def run(self) -> None:
        """Ejecuta el bucle principal del kernel.

        Bucle de fondo (housekeeping + eventos), deliberadamente desacoplado
        del servidor HTTP: `api.py` se sirve por separado (vía uvicorn) y
        comparte instancias con el Kernel solo cuando ambos corren en el
        mismo proceso — el Kernel nunca levanta el servidor él mismo (ver
        decisión de arquitectura registrada en PROGRESS.md).

        Corre hasta que `shutdown()` señale la salida, invocando
        `memory.clear_expired()` en el intervalo configurado en
        `settings.kernel_housekeeping_interval_seconds`.
        """
        if not self._initialized:
            raise KernelError("El kernel debe inicializarse antes de ejecutarse.")

        if self._running:
            self.logger.warning("El kernel ya se está ejecutando")
            return

        self._running = True
        self._stop_event = asyncio.Event()
        interval = self.settings.kernel_housekeeping_interval_seconds
        self.logger.info("Kernel en ejecución", housekeeping_interval_seconds=interval)

        from .events import KernelStartingEvent

        await self.event_bus.publish(KernelStartingEvent())

        try:
            while not self._stop_event.is_set():
                eliminados = await self.memory.clear_expired()
                if eliminados:
                    self.logger.debug(
                        "Housekeeping: memoria expirada limpiada", eliminados=eliminados
                    )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            self.logger.info("Kernel completó su ciclo de ejecución")
        finally:
            self._running = False

    async def shutdown(self) -> None:
        """Cierra los recursos del kernel de forma segura.

        Señala a `run()` (si está en ejecución) que debe salir de su bucle
        de housekeeping antes de publicar el evento de apagado, para que un
        shutdown ordenado (Ctrl+C / señal, ver `__main__.py`) no deje el
        bucle de fondo corriendo después de que el kernel se marca como no
        inicializado. También descarga todos los plugins cargados, en
        orden inverso al de carga, antes de publicar `KernelShutdownEvent`.
        """
        if not self._initialized:
            self.logger.warning("El kernel no estaba inicializado al apagar")
            return

        self.logger.info("Apagando kernel")

        if self._stop_event is not None:
            self._stop_event.set()

        await self._unload_plugins()

        from .events import KernelShutdownEvent

        await self.event_bus.publish(KernelShutdownEvent())
        await asyncio.sleep(0.05)
        self._initialized = False
        self.logger.info("Kernel apagado correctamente")
