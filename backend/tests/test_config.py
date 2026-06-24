"""Типизированный конфиг (pydantic-settings): чтение из env, дефолты, валидация."""

import pytest

from app.core.config import Settings, build_settings

# Минимально достаточный набор обязательных переменных (без дефолтов).
REQUIRED_ENV = {
    "OPENROUTER_API_KEY": "sk-or-test-key",
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
    assert settings.openrouter_api_key == "sk-or-test-key"
    assert settings.secret_key == "test-secret"
    assert settings.seed_user_email == "test@example.com"
    assert settings.seed_user_password == "test-password"


def test_defaults_for_models_and_base_url(monkeypatch):
    _set_required(monkeypatch)
    for key in ("OPENROUTER_BASE_URL", "MODEL_VISION", "MODEL_RECO"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert settings.model_vision == "anthropic/claude-sonnet-4.6"
    assert settings.model_reco == "anthropic/claude-opus-4.8"


def test_base_url_is_configurable_from_env(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://gateway.example.test/api/v1")
    settings = Settings(_env_file=None)
    assert settings.openrouter_base_url == "https://gateway.example.test/api/v1"


def test_model_is_configurable_from_env(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("MODEL_VISION", "openai/gpt-4o")
    settings = Settings(_env_file=None)
    assert settings.model_vision == "openai/gpt-4o"


def test_missing_required_field_raises_clear_error(monkeypatch):
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        build_settings(_env_file=None)
    message = str(exc_info.value)
    # Сообщение должно называть отсутствующие переменные и указывать на .env.
    assert "OPENROUTER_API_KEY" in message
    assert ".env" in message
