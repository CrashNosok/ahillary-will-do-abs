"""Хэширование паролей (bcrypt через passlib): хэш не равен паролю, verify сходится."""

from app.core.security import hash_password, verify_password


def test_hash_is_not_plaintext_and_uses_bcrypt():
    hashed = hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"  # критерий: пароль захэширован, не лежит в открытом виде
    assert hashed.startswith("$2")  # префикс bcrypt-хэша ($2b$/$2a$)


def test_verify_matches_correct_password():
    hashed = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("s3cret-pw")
    assert verify_password("wrong-pw", hashed) is False
