"""Pruebas unitarias para el kernel de Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings
from aries.core.kernel import Kernel


@pytest.mark.asyncio
async def test_kernel_initialization() -> None:
    config = Settings()
    kernel = Kernel(config)

    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_already_initialized() -> None:
    config = Settings()
    kernel = Kernel(config)

    await kernel.initialize()
    await kernel.initialize()

    assert kernel._initialized is True


@pytest.mark.asyncio
async def test_kernel_shutdown() -> None:
    config = Settings()
    kernel = Kernel(config)

    await kernel.initialize()
    await kernel.shutdown()

    assert kernel._initialized is False
