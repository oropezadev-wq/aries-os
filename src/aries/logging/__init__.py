"""Configuración de logging estructurado para Aries OS."""

import logging
import sys
from typing import Optional

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configura structlog y el log estándar de Python."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        stream=sys.stdout,
        format="%(message)s",
        level=log_level,
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if level.upper() == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()


def get_logger(name: str, level: Optional[str] = None) -> structlog.BoundLogger:
    """Obtiene un logger estructurado con el nombre de componente indicado."""
    if level:
        configure_logging(level)
    return structlog.get_logger(name)
