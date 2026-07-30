"""Paquete de contratos para Aries OS."""

from .agent import ActionResult, ActionStatus, IAgent
from .event_bus import IEventBus
from .llm import ILLMProvider, LLMResponse
from .memory import IMemory, MemoryItem
from .plugin import IPlugin, PluginHooks, PluginMetadata
from .stt import ISTTProvider, STTResult
from .tool import ITool, ToolMetadata, ToolResult
from .tts import ITTSProvider, TTSResult
from .wake_word import IWakeWordProvider, WakeWordDetection

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
    "ISTTProvider",
    "STTResult",
    "ITool",
    "ToolMetadata",
    "ToolResult",
    "ITTSProvider",
    "TTSResult",
    "IWakeWordProvider",
    "WakeWordDetection",
]
