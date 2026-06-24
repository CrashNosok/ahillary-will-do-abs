"""LLM-клиент (OpenRouter, OpenAI-совместимый): выбор модели, vision, обработка ошибок.

Сеть не дёргаем — httpx.post мокаем. Реальный вызов проверяется вручную
(требует настоящий OPENROUTER_API_KEY).
"""

import base64

import httpx
import pytest

from app.core.config import settings
from app.services import llm

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-body"
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"


def _capture_post(reply: str, captured: dict):
    """Фейковый httpx.post: запоминает url/kwargs и возвращает OpenAI-ответ с `reply`."""

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": reply}}]},
            request=httpx.Request("POST", url),
        )

    return fake_post


def test_text_returns_response_with_reco_model(monkeypatch):
    cap: dict = {}
    monkeypatch.setattr(llm.httpx, "post", _capture_post("pong", cap))

    assert llm.text("ping") == "pong"
    body = cap["json"]
    assert body["model"] == settings.model_reco
    assert body["messages"][0]["content"] == [{"type": "text", "text": "ping"}]
    assert cap["url"] == f"{settings.openrouter_base_url}/chat/completions"
    assert cap["headers"]["Authorization"] == f"Bearer {settings.openrouter_api_key}"
    assert cap["timeout"] == llm.LLM_TIMEOUT_SECONDS


def test_text_uses_explicit_model(monkeypatch):
    cap: dict = {}
    monkeypatch.setattr(llm.httpx, "post", _capture_post("ok", cap))

    llm.text("ping", model="openai/gpt-4o")

    assert cap["json"]["model"] == "openai/gpt-4o"


def test_vision_uses_vision_model_and_encodes_image(monkeypatch):
    cap: dict = {}
    monkeypatch.setattr(llm.httpx, "post", _capture_post("вижу гантель", cap))

    assert llm.vision(PNG_BYTES, "что на фото?") == "вижу гантель"
    content = cap["json"]["messages"][0]["content"]
    assert cap["json"]["model"] == settings.model_vision
    assert content[0] == {"type": "text", "text": "что на фото?"}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.standard_b64decode(url.split(",", 1)[1]) == PNG_BYTES


def test_connection_error_becomes_llm_error(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("no network", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", boom)
    with pytest.raises(llm.LLMError):
        llm.text("ping")


def test_http_status_error_becomes_llm_error(monkeypatch):
    def unauthorized(url, **kwargs):
        return httpx.Response(401, json={"error": "no"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", unauthorized)
    with pytest.raises(llm.LLMError):
        llm.text("ping")


def test_media_type_detects_jpeg():
    assert llm._media_type(JPEG_BYTES) == "image/jpeg"


def test_unknown_media_type_raises():
    with pytest.raises(llm.LLMError):
        llm._media_type(b"not-an-image-at-all")
