"""Implementación básica del kernel de Aries OS."""

from __future__ import annotations

import asyncio

from structlog.stdlib import BoundLogger

from ..config.settings import Settings
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
    ) -> None:
        self.settings = settings
        self.memory = memory
        self.llm_provider = llm_provider
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._initialized = False
        self._running = False

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
        self.logger.debug("Kernel inicializado correctamente")

    async def run(self) -> None:
        """Ejecuta el bucle principal del kernel."""
        if not self._initialized:
            raise KernelError("El kernel debe inicializarse antes de ejecutarse.")

        if self._running:
            self.logger.warning("El kernel ya se está ejecutando")
            return

        self._running = True
        self.logger.info("Kernel en ejecución")

        try:
            await asyncio.sleep(0.1)
            self.logger.info("Kernel completó su ciclo de ejecución")
        finally:
            self._running = False

    async def shutdown(self) -> None:
        """Cierra los recursos del kernel de forma segura."""
        if not self._initialized:
            self.logger.warning("El kernel no estaba inicializado al apagar")
            return

        self.logger.info("Apagando kernel")
        await asyncio.sleep(0.05)
        self._initialized = False
        self.logger.info("Kernel apagado correctamente")
