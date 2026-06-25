"""Челленджи (M6·B36): POST /challenges/{id}/sponsors — привязка спонсора с суммой.

Залогинен user(id=1). Проверяем: привязку спонсора к челленджу (201 с amount/currency
из тела, challenge_id из пути), сохранность суммы как Decimal (копейки на месте), 404 на
несуществующий челлендж и несуществующего спонсора, 409 на повторную привязку того же
спонсора (unique challenge_id+sponsor_id), 422 на отсутствующую валюту и неположительную
сумму, и 401 без сессии.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.sponsor import Sponsor
from app.models.sport import Sport
from app.models.user import User

EMAIL = "sponsor-linker@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def _make_sport(engine, name: str, category: str = "strength") -> int:
    with Session(engine) as session:
        sport = Sport(name=name, category=category)
        session.add(sport)
        session.commit()
        session.refresh(sport)
        return sport.id


def _make_sponsor(engine, name: str) -> int:
    with Session(engine) as session:
        sponsor = Sponsor(name=name)
        session.add(sponsor)
        session.commit()
        session.refresh(sponsor)
        return sponsor.id


def _make_challenge(client, engine, title: str = "30 дней планки") -> int:
    sid = _make_sport(engine, f"Спорт-{title}")
    return client.post(
        "/challenges", json={"sport_id": sid, "title": title, "description": "d"}
    ).json()["id"]


def test_add_sponsor_returns_201_with_link(client, engine):
    cid = _make_challenge(client, engine)
    spid = _make_sponsor(engine, "Acme")
    resp = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": spid, "amount": "150.50", "currency": "USD"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["challenge_id"] == cid  # из пути
    assert body["sponsor_id"] == spid
    assert Decimal(str(body["amount"])) == Decimal("150.50")  # копейки на месте
    assert body["currency"] == "USD"


def test_add_sponsor_unknown_challenge_returns_404(client, engine):
    spid = _make_sponsor(engine, "Globex")
    resp = client.post(
        "/challenges/999/sponsors",
        json={"sponsor_id": spid, "amount": "10", "currency": "USD"},
    )
    assert resp.status_code == 404


def test_add_sponsor_unknown_sponsor_returns_404(client, engine):
    cid = _make_challenge(client, engine)
    resp = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": 999, "amount": "10", "currency": "USD"},
    )
    assert resp.status_code == 404


def test_add_same_sponsor_twice_returns_409(client, engine):
    cid = _make_challenge(client, engine)
    spid = _make_sponsor(engine, "Initech")
    first = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": spid, "amount": "10", "currency": "USD"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": spid, "amount": "20", "currency": "EUR"},
    )
    assert second.status_code == 409  # unique (challenge_id, sponsor_id)


def test_add_sponsor_requires_currency(client, engine):
    cid = _make_challenge(client, engine)
    spid = _make_sponsor(engine, "Umbrella")
    resp = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": spid, "amount": "10"},  # без currency
    )
    assert resp.status_code == 422


def test_add_sponsor_rejects_non_positive_amount(client, engine):
    cid = _make_challenge(client, engine)
    spid = _make_sponsor(engine, "Soylent")
    resp = client.post(
        f"/challenges/{cid}/sponsors",
        json={"sponsor_id": spid, "amount": "0", "currency": "USD"},
    )
    assert resp.status_code == 422


def test_add_sponsor_requires_auth():
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    resp = unauth.post(
        "/challenges/1/sponsors",
        json={"sponsor_id": 1, "amount": "10", "currency": "USD"},
    )
    assert resp.status_code == 401
