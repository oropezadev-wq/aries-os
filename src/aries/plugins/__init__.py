"""Sistema de plugins de Aries OS."""

from .context import build_plugin_context
from .events import PluginLoadedEvent, PluginUnloadedEvent
from .installer import check_requirements, install_requirements, missing_requirements
from .loader import LoaderError, load_plugin, load_plugin_class
from .manifest import ManifestError, parse_manifest
from .registry import CONTRACT_EVENTS, LoadedPlugin, PluginRegistry

__all__ = [
    "CONTRACT_EVENTS",
    "LoadedPlugin",
    "LoaderError",
    "ManifestError",
    "PluginLoadedEvent",
    "PluginRegistry",
    "PluginUnloadedEvent",
    "build_plugin_context",
    "check_requirements",
    "install_requirements",
    "load_plugin",
    "load_plugin_class",
    "missing_requirements",
    "parse_manifest",
]
