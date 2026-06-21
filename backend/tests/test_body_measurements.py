"""CRUD замеров тела (S2.2): ручной ввод обхватов в см, дата ISO.

Закрывает критерии карточки:
- запись сохраняется и читается по дате;
- список замеров отдаётся в хронологии (по возрастанию даты).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "body@example.com"
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


def test_create_returns_saved_fields(client):
    resp = client.post(
        "/body-measurements",
        json={"date": "2026-06-21", "waist_cm": 82.5, "chest_cm": 104, "notes": "утро"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["date"] == "2026-06-21"
    assert body["waist_cm"] == 82.5
    assert body["chest_cm"] == 104
    assert body["notes"] == "утро"


def test_read_by_id(client):
    created = client.post("/body-measurements", json={"date": "2026-06-21", "waist_cm": 80}).json()
    resp = client.get(f"/body-measurements/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["waist_cm"] == 80


def test_read_by_date(client):
    client.post("/body-measurements", json={"date": "2026-06-07", "waist_cm": 84})
    client.post("/body-measurements", json={"date": "2026-06-21", "waist_cm": 82})
    resp = client.get("/body-measurements", params={"date": "2026-06-21"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["date"] == "2026-06-21"
    assert body[0]["waist_cm"] == 82


def test_list_is_chronological(client):
    # вносим вразнобой — список должен вернуться по возрастанию даты
    for date in ("2026-06-21", "2026-05-24", "2026-06-07"):
        client.post("/body-measurements", json={"date": date})
    dates = [m["date"] for m in client.get("/body-measurements").json()]
    assert dates == ["2026-05-24", "2026-06-07", "2026-06-21"]


def test_get_unknown_returns_404(client):
    assert client.get("/body-measurements/999").status_code == 404


def test_update_changes_fields(client):
    created = client.post("/body-measurements", json={"date": "2026-06-21", "waist_cm": 82}).json()
    resp = client.patch(
        f"/body-measurements/{created['id']}",
        json={"waist_cm": 80, "notes": "после сушки"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["waist_cm"] == 80
    assert body["notes"] == "после сушки"
    assert body["date"] == "2026-06-21"  # не затёрто частичным апдейтом


def test_update_unknown_returns_404(client):
    assert client.patch("/body-measurements/999", json={"waist_cm": 80}).status_code == 404


def test_delete_removes_record(client):
    created = client.post("/body-measurements", json={"date": "2026-06-21"}).json()
    assert client.delete(f"/body-measurements/{created['id']}").status_code == 204
    assert client.get(f"/body-measurements/{created['id']}").status_code == 404


def test_create_requires_date(client):
    assert client.post("/body-measurements", json={"waist_cm": 80}).status_code == 422


def test_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/body-measurements").status_code == 401
