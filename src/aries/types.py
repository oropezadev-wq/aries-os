"""Tipos y alias comunes para Aries OS."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, TypedDict

EventData = Dict[str, Any]
EventHandler = Callable[[EventData], None]
AsyncEventHandler = Callable[[EventData], Awaitable[None]]
JSON = Dict[str, Any]
