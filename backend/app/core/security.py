"""Хэширование паролей через bcrypt. Единственный источник правды для auth.

hash_password — для сида и (позже) смены пароля; verify_password — для логина (S0.7).
Используем библиотеку bcrypt напрямую: passlib не поддерживает bcrypt 4.1+ (мёртв с 2020).
"""

import bcrypt

# bcrypt считает только первые 72 байта пароля и в 5.0 РОНЯЕТ длиннее — режем сами.
_MAX_BCRYPT_BYTES = 72


def hash_password(password: str) -> str:
    """bcrypt-хэш пароля (строка `$2b$...`)."""
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Сверяет пароль с хэшем (constant-time внутри bcrypt)."""
    return bcrypt.checkpw(_encode(password), password_hash.encode("ascii"))


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
