"""Личные цели по упражнениям: GET / upsert (PUT) / DELETE.

Закрывает: upsert по паре (user, exercise) обновляет, а не плодит; список и удаление
скоупятся по владельцу (чужая цель не видна и не удаляется → 404); цель на несуществующее
упражнение → 404; роуты под сессией (401 без неё).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует все таблицы
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.exercise_target import ExerciseTarget
from app.models.sport import Exercise, Sport
from app.models.user import User

EMAIL = "targets@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        s.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        sport = Sport(name="Зал", category="strength")
        s.add(sport)
        s.commit()
        s.refresh(sport)
        s.add(Exercise(sport_id=sport.id, name="Жим лёжа", kind="strength", unit="кг"))
        s.commit()
    return eng


@pytest.fixture
def client(engine):
    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield c
    app.dependency_overrides.clear()


def _exercise_id(engine) -> int:
    with Session(engine) as s:
        return s.exec(select(Exercise.id)).first()


def _put(client, eid: int, value: float):
    body = {"exercise_id": eid, "target_value": value, "unit": "кг"}
    return client.put("/exercise-targets", json=body)


def test_upsert_creates_then_updates(client, engine):
    eid = _exercise_id(engine)
    r1 = _put(client, eid, 100.0)
    assert r1.status_code == 200
    assert r1.json()["target_value"] == 100.0
    r2 = _put(client, eid, 110.0)
    assert r2.status_code == 200
    assert r2.json()["target_value"] == 110.0
    with Session(engine) as s:  # одна строка, а не дубль
        assert len(s.exec(select(ExerciseTarget)).all()) == 1


def test_unknown_exercise_returns_404(client):
    resp = client.put("/exercise-targets", json={"exercise_id": 999, "target_value": 50.0})
    assert resp.status_code == 404


def test_list_and_delete_scoped_to_owner(client, engine):
    eid = _exercise_id(engine)
    client.put("/exercise-targets", json={"exercise_id": eid, "target_value": 100.0})
    # чужая цель (user_id=2) не видна и не удаляется владельцем сессии (user_id=1)
    with Session(engine) as s:
        s.add(ExerciseTarget(user_id=2, exercise_id=eid, target_value=200.0))
        s.commit()
    listed = client.get("/exercise-targets").json()
    assert [t["target_value"] for t in listed] == [100.0]  # только своя
    assert client.delete(f"/exercise-targets/{eid}").status_code == 204  # снял свою
    assert client.delete(f"/exercise-targets/{eid}").status_code == 404  # своей больше нет


def test_exercise_target_in_snapshot(client, engine):
    """Цель по упражнению попадает в снапшот (#1) — чтобы ИИ учёл её в плане."""
    from app.services.snapshot import build_snapshot

    eid = _exercise_id(engine)
    _put(client, eid, 100.0)
    with Session(engine) as s:
        snap = build_snapshot(s, user_id=1)
    targets = snap["exercise_targets"]
    assert any(t["exercise_id"] == eid and t["target_value"] == 100.0 for t in targets)


def test_requires_auth():
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    assert unauth.get("/exercise-targets").status_code == 401
    put = unauth.put("/exercise-targets", json={"exercise_id": 1, "target_value": 1.0})
    assert put.status_code == 401
