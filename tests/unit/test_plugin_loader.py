"""Pruebas unitarias para plugins/loader.py.

Usa el plugin real de `tests/fixtures/example_plugin/` (sin mocks) más
plugins generados al vuelo en `tmp_path` para los casos de error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aries.contracts.plugin import IPlugin
from aries.plugins.loader import LoaderError, load_plugin, load_plugin_class
from aries.plugins.manifest import parse_manifest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "example_plugin"


def _write_plugin(tmp_path: Path, manifest: dict, module_code: str, module_name: str = "plugin") -> Path:
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / f"{module_name}.py").write_text(module_code, encoding="utf-8")
    return tmp_path


class TestLoadRealExamplePlugin:
    def test_load_plugin_returns_metadata_and_uninitialized_instance(self) -> None:
        metadata, instance = load_plugin(FIXTURE_DIR)

        assert metadata.name == "example-plugin"
        assert isinstance(instance, IPlugin)
        assert instance.initialized is False  # load_plugin() no llama initialize()

    def test_load_plugin_class_returns_the_class_not_an_instance(self) -> None:
        metadata = parse_manifest(FIXTURE_DIR)

        plugin_class = load_plugin_class(FIXTURE_DIR, metadata)

        assert isinstance(plugin_class, type)
        assert issubclass(plugin_class, IPlugin)


class TestLoaderErrors:
    def test_entry_point_module_does_not_exist(self, tmp_path: Path) -> None:
        _write_plugin(
            tmp_path,
            {
                "name": "roto",
                "version": "1.0.0",
                "author": "x",
                "description": "x",
                "requires": [],
                "entry_point": "no_existe:Clase",
            },
            "print('no debería importarse')\n",
        )

        with pytest.raises(LoaderError):
            load_plugin(tmp_path)

    def test_entry_point_class_does_not_exist_in_module(self, tmp_path: Path) -> None:
        _write_plugin(
            tmp_path,
            {
                "name": "sin-clase",
                "version": "1.0.0",
                "author": "x",
                "description": "x",
                "requires": [],
                "entry_point": "plugin:NoExiste",
            },
            "class OtraClase:\n    pass\n",
        )

        with pytest.raises(LoaderError):
            load_plugin(tmp_path)

    def test_entry_point_class_does_not_implement_iplugin(self, tmp_path: Path) -> None:
        _write_plugin(
            tmp_path,
            {
                "name": "no-iplugin",
                "version": "1.0.0",
                "author": "x",
                "description": "x",
                "requires": [],
                "entry_point": "plugin:NoEsPlugin",
            },
            "class NoEsPlugin:\n    pass\n",
        )

        with pytest.raises(LoaderError):
            load_plugin(tmp_path)

    def test_module_with_import_error_raises_loader_error(self, tmp_path: Path) -> None:
        _write_plugin(
            tmp_path,
            {
                "name": "import-roto",
                "version": "1.0.0",
                "author": "x",
                "description": "x",
                "requires": [],
                "entry_point": "plugin:Clase",
            },
            "import modulo_que_no_existe_xyz123\n\nclass Clase:\n    pass\n",
        )

        with pytest.raises(LoaderError):
            load_plugin(tmp_path)

    def test_module_that_raises_on_instantiation_raises_loader_error(self, tmp_path: Path) -> None:
        code = (
            "from aries.contracts.plugin import IPlugin\n\n"
            "class Clase(IPlugin):\n"
            "    def __init__(self):\n"
            "        raise RuntimeError('no se puede instanciar')\n"
            "    def get_metadata(self): ...\n"
            "    async def initialize(self, context): return True\n"
            "    async def shutdown(self): return True\n"
            "    def register_hooks(self): return {}\n"
            "    def get_capabilities(self): return []\n"
            "    def is_compatible(self, kernel_version): return True\n"
        )
        _write_plugin(
            tmp_path,
            {
                "name": "falla-init",
                "version": "1.0.0",
                "author": "x",
                "description": "x",
                "requires": [],
                "entry_point": "plugin:Clase",
            },
            code,
        )

        with pytest.raises(LoaderError):
            load_plugin(tmp_path)

    def test_manifest_error_propagates_unwrapped_for_caller_to_distinguish(
        self, tmp_path: Path
    ) -> None:
        from aries.plugins.manifest import ManifestError

        with pytest.raises(ManifestError):
            load_plugin(tmp_path)  # no hay manifest.json en absoluto
