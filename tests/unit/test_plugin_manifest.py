"""Pruebas unitarias para plugins/manifest.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aries.plugins.manifest import ManifestError, parse_manifest

VALID_MANIFEST: dict = {
    "name": "mi-plugin",
    "version": "1.0.0",
    "author": "Alguien",
    "description": "Un plugin de prueba",
    "requires": ["otro-plugin"],
    "entry_point": "plugin:MiPlugin",
}


def _write_manifest(path: Path, data: dict) -> Path:
    manifest_path = path / "manifest.json"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return manifest_path


class TestValidManifest:
    def test_parses_valid_manifest_from_directory(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, VALID_MANIFEST)

        metadata = parse_manifest(tmp_path)

        assert metadata.name == "mi-plugin"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Alguien"
        assert metadata.requires == ["otro-plugin"]
        assert metadata.entry_point == "plugin:MiPlugin"

    def test_parses_valid_manifest_from_direct_file_path(self, tmp_path: Path) -> None:
        manifest_path = _write_manifest(tmp_path, VALID_MANIFEST)

        metadata = parse_manifest(manifest_path)

        assert metadata.name == "mi-plugin"

    def test_requires_defaults_to_empty_list(self, tmp_path: Path) -> None:
        data = dict(VALID_MANIFEST)
        del data["requires"]
        _write_manifest(tmp_path, data)

        metadata = parse_manifest(tmp_path)

        assert metadata.requires == []


class TestInvalidManifest:
    def test_missing_file_raises_manifest_error(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError):
            parse_manifest(tmp_path / "no_existe")

    def test_malformed_json_raises_manifest_error(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("{ esto no es json", encoding="utf-8")

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    def test_json_array_instead_of_object_raises_manifest_error(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    @pytest.mark.parametrize("missing_field", ["name", "version", "author", "description"])
    def test_missing_required_field_raises_manifest_error(
        self, tmp_path: Path, missing_field: str
    ) -> None:
        data = dict(VALID_MANIFEST)
        del data[missing_field]
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    @pytest.mark.parametrize("bad_name", ["MiPlugin", "mi plugin", "mi/plugin", ""])
    def test_invalid_name_raises_manifest_error(self, tmp_path: Path, bad_name: str) -> None:
        data = dict(VALID_MANIFEST, name=bad_name)
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    @pytest.mark.parametrize("bad_version", ["1.0", "v1.0.0", "latest", "1"])
    def test_invalid_version_raises_manifest_error(self, tmp_path: Path, bad_version: str) -> None:
        data = dict(VALID_MANIFEST, version=bad_version)
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    @pytest.mark.parametrize("bad_entry_point", ["plugin.MiPlugin", "plugin", ":MiPlugin", "plugin:"])
    def test_invalid_entry_point_raises_manifest_error(
        self, tmp_path: Path, bad_entry_point: str
    ) -> None:
        data = dict(VALID_MANIFEST, entry_point=bad_entry_point)
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    def test_requires_not_a_list_raises_manifest_error(self, tmp_path: Path) -> None:
        data = dict(VALID_MANIFEST, requires="otro-plugin")
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)

    def test_requires_with_non_string_items_raises_manifest_error(self, tmp_path: Path) -> None:
        data = dict(VALID_MANIFEST, requires=[1, 2])
        _write_manifest(tmp_path, data)

        with pytest.raises(ManifestError):
            parse_manifest(tmp_path)
