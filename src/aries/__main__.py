"""Punto de entrada principal para ejecutar Aries OS."""

import asyncio
from typing import NoReturn

from .config.settings import Settings
from .core import Kernel
from .llm.ollama_provider import OllamaProvider
from .memory.in_memory import InMemoryStore
from .exceptions import AriesException
from .logging import get_logger

LOGGER = get_logger("aries.__main__")


async def main() -> None:
    """Inicializa y ejecuta el kernel principal del sistema."""
    settings = Settings()
    memory = InMemoryStore()

    async with OllamaProvider(settings) as llm_provider:
        kernel = Kernel(settings, memory, llm_provider)

        try:
            await kernel.initialize()
            await kernel.run()
        except AriesException as error:
            LOGGER.error("Error en Aries OS", error=str(error))
            raise
        except Exception as error:
            LOGGER.exception("Excepción inesperada en Aries OS", error=str(error))
            raise
        finally:
            await kernel.shutdown()


def run() -> None:
    """Ejecuta la aplicación asincrónica usando asyncio."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
