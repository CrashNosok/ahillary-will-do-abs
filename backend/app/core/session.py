"""Подпись cookie-сессии: HMAC-SHA256 на SECRET_KEY.

В cookie кладём только id пользователя, подписанный SECRET_KEY: подделать нельзя
(нет ключа), но и шифрования нет — id виден. Для личного локального трекера достаточно.
Проверка подписи — constant-time (hmac.compare_digest). Регистрации/мультиюзера нет,
поэтому payload минимальный — без itsdangerous/JWT хватает стдлиба.
"""

import hmac
from hashlib import sha256

from app.core.config import settings

SESSION_COOKIE = "session"


def sign(value: str) -> str:
    """`value.<hex-HMAC>` — value, подписанный SECRET_KEY."""
    return f"{value}.{_digest(value)}"


def unsign(signed: str) -> str | None:
    """Возвращает исходный value при валидной подписи, иначе None."""
    value, sep, sig = signed.rpartition(".")
    if not sep or not hmac.compare_digest(sig, _digest(value)):
        return None
    return value


def _digest(value: str) -> str:
    return hmac.new(settings.secret_key.encode(), value.encode(), sha256).hexdigest()
