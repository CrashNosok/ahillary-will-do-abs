"""Общий помощник времени для моделей: UTC-aware now для default_factory полей *_at."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
