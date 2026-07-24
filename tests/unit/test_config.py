"""Pruebas unitarias para la configuración de Aries OS."""

from __future__ import annotations

import pytest

from aries.config.settings import Settings


def test_settings_load_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "aries-os"
    assert settings.environment == "development"
    assert settings.api_port == 8000
    assert settings.log_level == "DEBUG"


def test_settings_override_from_env(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings()

    assert settings.environment == "testing"
    assert settings.log_level == "WARNING"
    assert settings.api_port == 9000
