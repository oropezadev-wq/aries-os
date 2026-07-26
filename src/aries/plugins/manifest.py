"""plugins/manifest.py — parseo y validación del manifest de un plugin
contra `PluginMetadata` (`docs/contracts/IPlugin.md`).

Formato elegido: **JSON** (`manifest.json`), no un `manifest.py` con un
dict de Python — a propósito. Leer los metadatos de un plugin (para
decidir si vale la pena cargarlo, chequear versión, etc.) no debe requerir
ejecutar ni una sola línea de código del plugin. Un manifest en Python
ejecutable sería un vector de ejecución de código arbitrario con solo
"mirar" qué plugin es, antes de que nadie decida cargarlo de verdad — JSON
es datos puros, sin ese riesgo.

`entry_point` usa el formato `"modulo:Clase"` (mismo estilo que los
entry points de `setuptools`) — inequívoco sobre dónde termina el módulo y
empieza el nombre de la clase, a diferencia de `"modulo.Clase"` con puntos
para ambas cosas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..contracts.plugin import PluginMetadata

MANIFEST_FILENAME = "manifest.json"

_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+")
_ENTRY_POINT_PATTERN = re.compile(r"^[\w.]+:[\w]+$")
_REQUIRED_STRING_FIELDS = ("name", "version", "author", "description")


class ManifestError(Exception):
    """Manifest de plugin inválido, ilegible o con JSON malformado.

    Nunca debe llegar sin capturar a quien orquesta la carga de plugins
    (`loader.py`/`registry.py`) — es el punto donde se normalizan todos los
    errores posibles de lectura/parseo/validación en un único tipo de
    excepción con mensaje claro, en vez de dejar propagar `OSError`,
    `json.JSONDecodeError`, `KeyError`, etc. tal cual.
    """


def parse_manifest(path: str | Path) -> PluginMetadata:
    """Lee y valida el manifest en `path` (o `path/manifest.json` si
    `path` es un directorio). Levanta `ManifestError` con un mensaje claro
    ante cualquier problema — nunca deja escapar la excepción original."""
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_FILENAME

    if not manifest_path.exists():
        raise ManifestError(f"No existe el manifest: {manifest_path}")
    if not manifest_path.is_file():
        raise ManifestError(f"La ruta del manifest no es un archivo: {manifest_path}")

    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError(f"No se pudo leer el manifest {manifest_path}: {error}") from error

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ManifestError(f"JSON inválido en el manifest {manifest_path}: {error}") from error

    if not isinstance(data, dict):
        raise ManifestError(
            f"El manifest debe ser un objeto JSON, no {type(data).__name__}: {manifest_path}"
        )

    missing = [field for field in _REQUIRED_STRING_FIELDS if field not in data]
    if missing:
        raise ManifestError(f"Faltan campos requeridos {missing} en el manifest {manifest_path}")

    for field_name in _REQUIRED_STRING_FIELDS:
        value = data[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(
                f"El campo '{field_name}' debe ser un string no vacío en {manifest_path}"
            )

    name = data["name"]
    if not _NAME_PATTERN.match(name):
        raise ManifestError(
            f"'name' debe ser minúsculas y sin espacios (solo [a-z0-9_-]): {name!r} en {manifest_path}"
        )

    version = data["version"]
    if not _VERSION_PATTERN.match(version):
        raise ManifestError(
            f"'version' debe ser semántica (ej. '1.0.0'): {version!r} en {manifest_path}"
        )

    requires = data.get("requires", [])
    if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
        raise ManifestError(f"'requires' debe ser una lista de strings en {manifest_path}")

    entry_point = data.get("entry_point", "")
    if not isinstance(entry_point, str) or not entry_point.strip():
        raise ManifestError(f"'entry_point' no puede estar vacío en {manifest_path}")
    if not _ENTRY_POINT_PATTERN.match(entry_point):
        raise ManifestError(
            f"'entry_point' debe tener el formato 'modulo:Clase': {entry_point!r} en {manifest_path}"
        )

    return PluginMetadata(
        name=name,
        version=version,
        author=data["author"],
        description=data["description"],
        requires=list(requires),
        entry_point=entry_point,
    )
