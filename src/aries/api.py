"""API mínima para Aries OS usando FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from .config.settings import Settings
from .logging import get_logger

settings = Settings()
logger = get_logger("aries.api", settings.log_level)
app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def startup_event() -> None:
    """Evento de inicio de la aplicación."""
    logger.info("API Aries arrancando", environment=settings.environment)


@app.get("/health", summary="Estado de la aplicación")
async def health_check() -> dict[str, str]:
    """Comprueba que la API está disponible."""
    return {"status": "ok", "environment": settings.environment}
