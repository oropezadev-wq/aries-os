from __future__ import annotations

import logging

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import StackInfoRenderer, TimeStamper, add_log_level, format_exc_info
from structlog.stdlib import BoundLogger, LoggerFactory
from typing import cast


_configured = False


def get_logger(name: str, level: str | int = "INFO") -> BoundLogger:
    """Retorna un logger estructurado para Aries OS."""
    global _configured

    if not _configured:
        logging.basicConfig(level=level)
        structlog.configure(
            processors=[
                add_log_level,
                StackInfoRenderer(),
                format_exc_info,
                TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            logger_factory=LoggerFactory(),
            wrapper_class=BoundLogger,
            cache_logger_on_first_use=True,
        )
        _configured = True

    return cast(BoundLogger, structlog.get_logger(name))
