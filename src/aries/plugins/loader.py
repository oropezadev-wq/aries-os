"""plugins/loader.py — carga dinámica del código de un plugin desde disco
(`importlib`) e instanciación de su clase `IPlugin`, **sin** llamar a
`initialize()` — eso es responsabilidad de `PluginRegistry.load()`, que
además necesita el `context` real (event_bus, logger, etc.) antes de poder
inicializar nada.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ..contracts.plugin import IPlugin, PluginMetadata
from .manifest import parse_manifest


class LoaderError(Exception):
    """Error al importar/instanciar el código de un plugin.

    Nunca debe llegar sin capturar más allá de `PluginRegistry` — normaliza
    cualquier falla de import (módulo inexistente, error de sintaxis,
    excepción durante la ejecución del módulo, clase inexistente, clase que
    no implementa `IPlugin`) en un único tipo de excepción con mensaje claro.
    """


def load_plugin_class(plugin_dir: str | Path, metadata: PluginMetadata) -> type[IPlugin]:
    """Importa el módulo declarado en `metadata.entry_point` ('modulo:Clase')
    dentro de `plugin_dir` y devuelve la clase (sin instanciarla)."""
    module_name, _, class_name = metadata.entry_point.partition(":")

    plugin_dir = Path(plugin_dir)
    module_path = plugin_dir / (module_name.replace(".", "/") + ".py")

    if not module_path.exists():
        raise LoaderError(
            f"No existe el módulo del entry_point de '{metadata.name}': {module_path}"
        )

    unique_module_name = f"aries_plugin__{metadata.name}__{module_name}".replace("-", "_")
    spec = importlib.util.spec_from_file_location(unique_module_name, module_path)
    if spec is None or spec.loader is None:
        raise LoaderError(f"No se pudo crear el import spec para {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(unique_module_name, None)
        raise LoaderError(
            f"Error al importar el módulo del plugin '{metadata.name}' ({module_path}): {error}"
        ) from error

    plugin_class = getattr(module, class_name, None)
    if plugin_class is None:
        raise LoaderError(
            f"El módulo {module_path} no define la clase '{class_name}' declarada en entry_point"
        )

    if not isinstance(plugin_class, type) or not issubclass(plugin_class, IPlugin):
        raise LoaderError(f"'{class_name}' en {module_path} no es una subclase de IPlugin")

    return plugin_class


def load_plugin(plugin_dir: str | Path) -> tuple[PluginMetadata, IPlugin]:
    """Lee el manifest de `plugin_dir`, importa la clase de su
    `entry_point` y la instancia — **sin** llamar a `initialize()`.

    Levanta `ManifestError` (de `manifest.py`) o `LoaderError`; ninguna de
    las dos debe llegar sin capturar más allá de `PluginRegistry`.
    """
    plugin_dir = Path(plugin_dir)
    metadata = parse_manifest(plugin_dir)  # puede levantar ManifestError, se deja propagar tal cual
    plugin_class = load_plugin_class(plugin_dir, metadata)

    try:
        instance = plugin_class()
    except Exception as error:
        raise LoaderError(f"Error al instanciar el plugin '{metadata.name}': {error}") from error

    return metadata, instance
