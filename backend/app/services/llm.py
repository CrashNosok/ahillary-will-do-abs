"""Обёртка над Anthropic SDK для текстовых и vision-запросов через ProxyAPI.

api_key и base_url берутся из конфига (см. app.core.config) — в коде их нет.
Модель по умолчанию: text() → MODEL_RECO, vision() → MODEL_VISION.
Ошибки сети/API заворачиваются в LLMError, чтобы вызывающий код не зависел от
внутренних классов SDK.
"""

import base64
from functools import lru_cache

import anthropic

from app.core.config import settings

# ponytail: фиксированный таймаут; вынести в конфиг, если какому-то вызову не хватит.
LLM_TIMEOUT_SECONDS = 60.0
# Скромный потолок ответа — задачи трекера (распознавание, рекомендации) короткие.
_MAX_TOKENS = 1024


class LLMError(RuntimeError):
    """Не удалось получить ответ от LLM (сеть, авторизация, ошибка API)."""


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    """Singleton-клиент Anthropic с base_url/api_key из конфига и таймаутом."""
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def text(prompt: str, model: str | None = None) -> str:
    """Текстовый запрос. По умолчанию модель MODEL_RECO."""
    return _create(model or settings.model_reco, [{"type": "text", "text": prompt}])


def vision(image_bytes: bytes, prompt: str, model: str | None = None) -> str:
    """Vision-запрос: изображение + текстовый вопрос. По умолчанию модель MODEL_VISION."""
    image_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _media_type(image_bytes),
            "data": base64.standard_b64encode(image_bytes).decode("ascii"),
        },
    }
    content = [image_block, {"type": "text", "text": prompt}]
    return _create(model or settings.model_vision, content)


def _create(model: str, content: list[dict]) -> str:
    """Шлёт один user-message и возвращает склеенный текст ответа."""
    try:
        message = _client().messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as exc:
        raise LLMError(f"Запрос к LLM не удался: {exc}") from exc
    return "".join(block.text for block in message.content if block.type == "text")


def _media_type(image_bytes: bytes) -> str:
    """Определяет MIME картинки по сигнатуре. Anthropic принимает png/jpeg/gif/webp."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise LLMError("Не удалось определить тип изображения (поддержка: PNG/JPEG/GIF/WebP).")
