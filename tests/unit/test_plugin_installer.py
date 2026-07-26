"""Pruebas unitarias para plugins/installer.py."""

from __future__ import annotations

import pytest

from aries.contracts.plugin import PluginMetadata
from aries.plugins.installer import (
    check_requirements,
    install_requirements,
    missing_requirements,
)


def _metadata(requires: list[str]) -> PluginMetadata:
    return PluginMetadata(
        name="test-plugin",
        version="1.0.0",
        author="x",
        description="x",
        requires=requires,
        entry_point="plugin:X",
    )


class TestCheckRequirements:
    def test_no_requirements_returns_empty_dict(self) -> None:
        assert check_requirements(_metadata([])) == {}

    def test_importable_stdlib_package_is_available(self) -> None:
        status = check_requirements(_metadata(["json", "os"]))

        assert status == {"json": True, "os": True}

    def test_nonexistent_package_is_unavailable(self) -> None:
        status = check_requirements(_metadata(["paquete_que_no_existe_xyz123"]))

        assert status == {"paquete_que_no_existe_xyz123": False}

    def test_loaded_plugin_name_counts_as_available(self) -> None:
        status = check_requirements(
            _metadata(["otro-plugin"]), loaded_plugin_names={"otro-plugin"}
        )

        assert status == {"otro-plugin": True}

    def test_plugin_name_not_loaded_and_not_importable_is_unavailable(self) -> None:
        status = check_requirements(
            _metadata(["otro-plugin"]), loaded_plugin_names={"un-tercer-plugin"}
        )

        assert status == {"otro-plugin": False}

    def test_mixed_requirements(self) -> None:
        status = check_requirements(
            _metadata(["json", "plugin-cargado", "no_existe_nada_xyz"]),
            loaded_plugin_names={"plugin-cargado"},
        )

        assert status == {"json": True, "plugin-cargado": True, "no_existe_nada_xyz": False}


class TestMissingRequirements:
    def test_returns_only_unavailable_entries(self) -> None:
        missing = missing_requirements(_metadata(["json", "no_existe_xyz"]))

        assert missing == ["no_existe_xyz"]

    def test_empty_when_all_available(self) -> None:
        assert missing_requirements(_metadata(["json"])) == []


class TestInstallRequirementsIsDisabled:
    def test_install_requirements_always_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            install_requirements(_metadata(["cualquier-cosa"]))

    def test_install_requirements_raises_even_with_no_requirements(self) -> None:
        # No debe haber ningún atajo que lo "active" ni siquiera con
        # requires vacío — está deshabilitado sin excepciones.
        with pytest.raises(NotImplementedError):
            install_requirements(_metadata([]))
