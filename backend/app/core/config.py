"""Типизированный конфиг приложения.

Секреты и параметры читаются ТОЛЬКО из окружения / backend/.env через
pydantic-settings — в коде их нет. Обязательные поля валидируются при старте:
отсутствие любого из них роняет приложение с понятным сообщением (см. build_settings).
"""

from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — корень бэкенда (config.py лежит в backend/app/core/).
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Локальный фронт (Vite). Не секрет, не из env — статичный список origin для CORS.
CORS_ORIGINS: list[str] = ["http://localhost:5173"]


class Settings(BaseSettings):
    """Единый источник конфигурации. Имена env — регистронезависимые (UPPER_SNAKE)."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Anthropic / LLM (через ProxyAPI-совместимый base_url) ---
    anthropic_api_key: str
    anthropic_base_url: str = "https://api.proxyapi.ru/anthropic"
    model_vision: str = "claude-sonnet-4-6"
    model_reco: str = "claude-opus-4-8"

    # --- Сессии (подпись cookie) ---
    secret_key: str

    # --- Единственный сид-аккаунт (регистрации нет) ---
    seed_user_email: str
    seed_user_password: str

    # --- Локальные данные (SQLite, видео/скрины) ---
    data_dir: Path = Path("data")


def build_settings(**overrides) -> Settings:
    """Создаёт Settings, превращая ошибку валидации в понятное сообщение.

    overrides пробрасываются в Settings (например, _env_file=None в тестах).
    """
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        missing = [
            ".".join(str(part) for part in err["loc"])
            for err in exc.errors()
            if err["type"] == "missing"
        ]
        if missing:
            raise RuntimeError(
                "Не заданы обязательные переменные окружения: "
                + ", ".join(name.upper() for name in missing)
                + ". Заполни backend/.env по образцу backend/.env.example."
            ) from exc
        raise


# Валидация при старте: импорт конфига (а значит и приложения) упадёт,
# если в окружении/.env нет обязательных полей.
settings = build_settings()
