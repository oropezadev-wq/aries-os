"""Tipos y alias comunes para Aries OS."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, TypedDict

EventData = Dict[str, Any]
EventHandler = Callable[[Any], None]
AsyncEventHandler = Callable[[Any], Awaitable[None]]
JSON = Dict[str, Any]
