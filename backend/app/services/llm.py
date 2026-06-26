"""Обёртка над OpenRouter (OpenAI-совместимый API) для текстовых и vision-запросов.

api_key и base_url берутся из конфига (см. app.core.config) — в коде их нет. Модель
выбирается через env: text() → MODEL_RECO, vision() → MODEL_VISION (любая модель
OpenRouter, напр. `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`). Запрос идёт по
OpenAI-формату /chat/completions. Ошибки сети/API заворачиваются в LLMError, чтобы
вызывающий код не зависел от транспорта.
"""

import base64

import httpx

from app.core.config import settings

# ponytail: фиксированный таймаут; вынести в конфиг, если какому-то вызову не хватит.
LLM_TIMEOUT_SECONDS = 60.0
# Потолок ответа. Распознавание скринов — короткий JSON (сотни токенов), но отчёт/рекомендация
# (структурный план) длиннее: при 1024 модель обрывала JSON на полуслове → невалидный ответ.
# Это лишь ВЕРХНЯЯ граница: модель отдаёт, сколько нужно, поэтому vision не дорожает от запаса.
_MAX_TOKENS = 4096


class LLMError(RuntimeError):
    """Не удалось получить ответ от LLM (сеть, авторизация, ошибка API)."""


def text(prompt: str, model: str | None = None) -> str:
    """Текстовый запрос. По умолчанию модель MODEL_RECO."""
    return _create(model or settings.model_reco, [{"type": "text", "text": prompt}])


def vision(image_bytes: bytes, prompt: str, model: str | None = None) -> str:
    """Vision-запрос: изображение + текстовый вопрос. По умолчанию модель MODEL_VISION."""
    encoded = base64.standard_b64encode(image_bytes).decode("ascii")
    data_url = f"data:{_media_type(image_bytes)};base64,{encoded}"
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return _create(model or settings.model_vision, content)


def _create(model: str, content: list[dict]) -> str:
    """Шлёт один user-message в OpenRouter /chat/completions и возвращает текст ответа."""
    try:
        resp = httpx.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model,
                "max_tokens": _MAX_TOKENS,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"Запрос к LLM не удался: {exc}") from exc
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Неожиданный ответ LLM: {data!r}") from exc


def _media_type(image_bytes: bytes) -> str:
    """Определяет MIME картинки по сигнатуре (png/jpeg/gif/webp) для data-URL."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise LLMError("Не удалось определить тип изображения (поддержка: PNG/JPEG/GIF/WebP).")
