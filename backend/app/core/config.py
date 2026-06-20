"""Конфигурация приложения.

ponytail: пока только список CORS-origin фронта захардкожен здесь;
переезд на pydantic-settings (чтение из .env) — карточка S0.3.
"""

# Локальный фронт (Vite). Фронт ходит на бэкенд с этого origin.
CORS_ORIGINS: list[str] = ["http://localhost:5173"]
