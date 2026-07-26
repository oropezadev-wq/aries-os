"""plugins/installer.py — verificación de las dependencias declaradas en
`PluginMetadata.requires` ("otros plugins o paquetes pip", según
`docs/contracts/IPlugin.md`). **No instala nada** — ver `install_requirements()`.
"""

from __future__ import annotations

import importlib.util

from ..contracts.plugin import PluginMetadata


def check_requirements(
    metadata: PluginMetadata, loaded_plugin_names: set[str] | None = None
) -> dict[str, bool]:
    """Verifica cada entrada de `metadata.requires` sin instalar nada.

    Cada entrada de `requires` puede ser el nombre de otro plugin (se
    compara contra `loaded_plugin_names`) o un paquete pip importable (se
    comprueba con `importlib.util.find_spec`, que localiza el módulo sin
    ejecutarlo/importarlo de verdad). No hay forma de saber de antemano
    cuál es cuál a partir del string solo, así que se comprueban ambas
    posibilidades para cada entrada.

    Returns:
        dict {requisito: disponible (bool)}
    """
    loaded = loaded_plugin_names or set()
    status: dict[str, bool] = {}
    for requirement in metadata.requires:
        if requirement in loaded:
            status[requirement] = True
            continue
        try:
            status[requirement] = importlib.util.find_spec(requirement) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            # find_spec puede levantar si el nombre es inválido como
            # identificador de módulo (ej. viene de un plugin name con
            # guiones) — se trata como "no disponible como paquete",
            # no como error.
            status[requirement] = False
    return status


def missing_requirements(
    metadata: PluginMetadata, loaded_plugin_names: set[str] | None = None
) -> list[str]:
    """Atajo sobre `check_requirements()`: solo los requisitos que faltan."""
    status = check_requirements(metadata, loaded_plugin_names)
    return [name for name, available in status.items() if not available]


def install_requirements(metadata: PluginMetadata) -> None:
    """NO IMPLEMENTADO A PROPÓSITO — decisión de seguridad, no pereza.

    Instalar paquetes pip arbitrarios declarados por un plugin de terceros
    (`metadata.requires`) sin supervisión humana es, en los hechos,
    ejecución de código arbitrario con los privilegios del proceso que
    corre Aries OS (setup.py / build hooks / wheels maliciosos corriendo
    como el usuario actual, potencialmente durante una sesión nocturna sin
    nadie mirando). La instrucción para esta tarea fue explícita: este
    método queda deshabilitado bajo cualquier circunstancia, no se activa,
    no se rodea, no se implementa "una versión simple total esta noche".

    `check_requirements()`/`missing_requirements()` arriba cubren todo lo
    que sí está en alcance de esta tarea: detectar y reportar qué falta,
    sin instalar nada.

    Si en el futuro se decide implementar esto de verdad, como mínimo
    debería requerir: confirmación explícita del usuario por cada paquete a
    instalar, verificación de origen (índice de PyPI oficial vs. uno
    arbitrario), y probablemente aislamiento por plugin (venv o contenedor
    dedicado) — ninguna de esas decisiones de diseño se tomó acá; quedan
    fuera de alcance a propósito.
    """
    raise NotImplementedError(
        "install_requirements() está deshabilitado a propósito por razones de "
        "seguridad: instalar paquetes declarados por un plugin sin supervisión "
        "humana es ejecución de código arbitrario. No se activa en esta sesión."
    )
