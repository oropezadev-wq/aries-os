"""Paquete de contratos para Aries OS."""

from .agent import ActionResult, ActionStatus, IAgent
from .event_bus import IEventBus
from .llm import ILLMProvider, LLMResponse
from .memory import IMemory, MemoryItem
from .plugin import IPlugin, PluginHooks, PluginMetadata
from .tool import ITool, ToolMetadata, ToolResult

__all__ = [
    "ActionResult",
    "ActionStatus",
    "IAgent",
    "IEventBus",
    "ILLMProvider",
    "LLMResponse",
    "IMemory",
    "MemoryItem",
    "IPlugin",
    "PluginHooks",
    "PluginMetadata",
    "ITool",
    "ToolMetadata",
    "ToolResult",
]
