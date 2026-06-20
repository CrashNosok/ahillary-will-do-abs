"""LLM-клиент: конфигурируемый base_url, выбор модели, vision и обработка ошибок.

Сеть не дёргаем — Anthropic-клиент мокаем. Реальный вызов через ProxyAPI
проверяется вручную по smoke-guide (требует настоящий ANTHROPIC_API_KEY).
"""

import base64
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx
import pytest

from app.core.config import settings
from app.services import llm

# Префиксы реальных форматов — снифферу достаточно сигнатуры в начале файла.
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-body"
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"


def _fake_message(text: str) -> SimpleNamespace:
    """Имитация anthropic.types.Message: .content — список текстовых блоков."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _fake_client(reply: str = "ok") -> mock.Mock:
    client = mock.Mock()
    client.messages.create.return_value = _fake_message(reply)
    return client


def test_text_returns_response_with_reco_model(monkeypatch):
    client = _fake_client("pong")
    monkeypatch.setattr(llm, "_client", lambda: client)

    result = llm.text("ping")

    assert result == "pong"
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == settings.model_reco
    assert kwargs["messages"][0]["content"] == [{"type": "text", "text": "ping"}]


def test_text_uses_explicit_model(monkeypatch):
    client = _fake_client()
    monkeypatch.setattr(llm, "_client", lambda: client)

    llm.text("ping", model="claude-haiku-4-5")

    assert client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"


def test_vision_uses_vision_model_and_encodes_image(monkeypatch):
    client = _fake_client("вижу гантель")
    monkeypatch.setattr(llm, "_client", lambda: client)

    result = llm.vision(PNG_BYTES, "что на фото?")

    assert result == "вижу гантель"
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == settings.model_vision
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(content[0]["source"]["data"]) == PNG_BYTES
    assert content[1] == {"type": "text", "text": "что на фото?"}


def test_client_built_from_settings(monkeypatch):
    captured: dict = {}

    def fake_anthropic(**kwargs):
        captured.update(kwargs)
        return mock.Mock()

    monkeypatch.setattr(llm.anthropic, "Anthropic", fake_anthropic)
    llm._client.cache_clear()
    try:
        llm._client()
    finally:
        llm._client.cache_clear()

    assert captured["api_key"] == settings.anthropic_api_key
    assert captured["base_url"] == settings.anthropic_base_url
    assert captured["timeout"] == llm.LLM_TIMEOUT_SECONDS


def test_api_error_becomes_llm_error(monkeypatch):
    client = mock.Mock()
    request = httpx.Request("POST", "https://api.proxyapi.ru/anthropic/v1/messages")
    client.messages.create.side_effect = anthropic.APIConnectionError(request=request)
    monkeypatch.setattr(llm, "_client", lambda: client)

    with pytest.raises(llm.LLMError):
        llm.text("ping")


def test_media_type_detects_jpeg():
    assert llm._media_type(JPEG_BYTES) == "image/jpeg"


def test_unknown_media_type_raises():
    with pytest.raises(llm.LLMError):
        llm._media_type(b"not-an-image-at-all")
