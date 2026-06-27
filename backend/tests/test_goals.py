"""CRUD SMART-цели (S1.3): создать/прочитать/обновить/архивировать + одна активная.

Закрывает критерии карточки: полный CRUD над smart_goal и инвариант «активной целью
считается ровно одна (status=active)», который всегда определяется через GET /goals/active.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "goals@example.com"
PASSWORD = "right-password"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def test_create_goal_returns_active_with_fields(client):
    resp = client.post(
        "/goals",
        json={
            "target_metrics_json": {"weight_kg": 78.5, "body_fat_pct": 15.0, "waist_cm": 82},
            "start_date": "2026-06-21",
            "deadline": "2026-12-31",
            "baseline_json": {"weight_kg": 90},
            "why_notes": "Хочу видеть кубики",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["status"] == "active"  # новая цель активна по умолчанию
    assert body["target_metrics_json"] == {"weight_kg": 78.5, "body_fat_pct": 15.0, "waist_cm": 82}
    assert body["baseline_json"] == {"weight_kg": 90}


def test_read_goal_by_id(client):
    created = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    resp = client.get(f"/goals/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["target_metrics_json"]["weight_kg"] == 80


def test_get_unknown_goal_returns_404(client):
    assert client.get("/goals/999").status_code == 404


def test_create_and_patch_reject_unknown_metric_key(client):
    # цель только по ключам реестра — неизвестный ключ отклоняется на create и на patch (422)
    assert client.post("/goals", json={"target_metrics_json": {"nope": 1}}).status_code == 422
    created = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    patched = client.patch(
        f"/goals/{created['id']}", json={"target_metrics_json": {"nope": 1}}
    )
    assert patched.status_code == 422


def test_create_ignores_status_from_body(client):
    # status в теле больше не принимается — цель всегда создаётся активной.
    body = client.post(
        "/goals", json={"target_metrics_json": {"weight_kg": 80}, "status": "archived"}
    ).json()
    assert body["status"] == "active"


def test_create_rejects_unknown_baseline_key(client):
    # baseline_json валидируется по реестру так же, как target_metrics_json (422).
    assert client.post("/goals", json={"baseline_json": {"nope": 1}}).status_code == 422
    ok = client.post("/goals", json={"baseline_json": {"weight_kg": 90}})
    assert ok.status_code == 201  # ключ реестра проходит


def test_update_goal_changes_fields(client):
    created = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    resp = client.patch(
        f"/goals/{created['id']}",
        json={"why_notes": "обновлено", "deadline": "2027-01-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["why_notes"] == "обновлено"
    assert body["deadline"] == "2027-01-01"
    assert body["target_metrics_json"] == {"weight_kg": 80}  # не затёрто частичным апдейтом


def test_list_returns_all_goals(client):
    client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}, "status": "archived"})
    client.post("/goals", json={"target_metrics_json": {"weight_kg": 78}})
    resp = client.get("/goals")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_only_one_active_goal_at_a_time(client):
    first = client.post("/goals", json={"target_metrics_json": {"weight_kg": 90}}).json()
    second = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    # новая активная цель архивирует предыдущую
    assert client.get(f"/goals/{first['id']}").json()["status"] == "archived"
    assert client.get(f"/goals/{second['id']}").json()["status"] == "active"
    active = client.get("/goals/active")
    assert active.status_code == 200
    assert active.json()["id"] == second["id"]


def test_archive_goal_clears_active(client):
    created = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    resp = client.post(f"/goals/{created['id']}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    # активной цели больше нет
    assert client.get("/goals/active").status_code == 404


def test_reactivating_goal_archives_other(client):
    first = client.post("/goals", json={"target_metrics_json": {"weight_kg": 90}}).json()
    second = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}}).json()
    # вернуть первую в active через PATCH — вторая должна архивироваться
    client.patch(f"/goals/{first['id']}", json={"status": "active"})
    assert client.get("/goals/active").json()["id"] == first["id"]
    assert client.get(f"/goals/{second['id']}").json()["status"] == "archived"


def test_active_goal_404_when_none(client):
    assert client.get("/goals/active").status_code == 404


def test_goals_require_auth():
    # без логина guard отдаёт 401
    app.dependency_overrides.clear()
    resp = TestClient(app).get("/goals")
    assert resp.status_code == 401
