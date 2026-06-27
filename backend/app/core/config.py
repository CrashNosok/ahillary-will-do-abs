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

    # --- LLM через OpenRouter (OpenAI-совместимый; модель выбирается через env) ---
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_vision: str = "anthropic/claude-sonnet-4.6"  # распознавание скринов (vision)
    model_reco: str = "anthropic/claude-opus-4.8"  # рекомендации/план (текст)

    # --- Сессии (подпись cookie) ---
    secret_key: str

    # --- Единственный сид-аккаунт (регистрации нет) ---
    seed_user_email: str
    seed_user_password: str

    # --- Локальные данные (SQLite, видео/скрины) ---
    data_dir: Path = Path("data")

    # --- Корпус исследований для доказательного отчёта (research/studies.json в корне репо) ---
    research_dir: Path = _BACKEND_DIR.parent / "research"


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
