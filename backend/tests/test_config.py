"""Типизированный конфиг (pydantic-settings): чтение из env, дефолты, валидация."""

import pytest

from app.core.config import Settings, build_settings

# Минимально достаточный набор обязательных переменных (без дефолтов).
REQUIRED_ENV = {
    "ANTHROPIC_API_KEY": "sk-test-key",
    "SECRET_KEY": "test-secret",
    "SEED_USER_EMAIL": "test@example.com",
    "SEED_USER_PASSWORD": "test-password",
}


def _set_required(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_loads_required_fields_from_env(monkeypatch):
    _set_required(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key == "sk-test-key"
    assert settings.secret_key == "test-secret"
    assert settings.seed_user_email == "test@example.com"
    assert settings.seed_user_password == "test-password"


def test_defaults_for_models_and_base_url(monkeypatch):
    _set_required(monkeypatch)
    for key in ("ANTHROPIC_BASE_URL", "MODEL_VISION", "MODEL_RECO"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.anthropic_base_url == "https://api.proxyapi.ru/anthropic"
    assert settings.model_vision == "claude-sonnet-4-6"
    assert settings.model_reco == "claude-opus-4-8"


def test_base_url_is_configurable_from_env(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.test/anthropic")
    settings = Settings(_env_file=None)
    assert settings.anthropic_base_url == "https://proxy.example.test/anthropic"


def test_missing_required_field_raises_clear_error(monkeypatch):
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        build_settings(_env_file=None)
    message = str(exc_info.value)
    # Сообщение должно называть отсутствующие переменные и указывать на .env.
    assert "ANTHROPIC_API_KEY" in message
    assert ".env" in message
