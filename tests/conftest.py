"""Configuración de pruebas para Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings
from aries.core.kernel import Kernel


@pytest.fixture(name="app_config")
def fixture_app_config() -> Settings:
    """Retorna la configuración base para los tests."""
    return Settings()


@pytest.fixture(name="kernel")
async def fixture_kernel(app_config: Settings) -> Kernel:
    """Inicializa un kernel para uso en pruebas asincrónicas."""
    kernel = Kernel(app_config)
    await kernel.initialize()
    yield kernel
    await kernel.shutdown()
