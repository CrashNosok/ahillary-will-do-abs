"""CRUD спонсоров (M6·B29): создать/список/читать/обновить/удалить + уникальность name.

Закрывает критерии карточки: полный CRUD над самостоятельной таблицей
sponsor(name, description, url, logo_path); name уникален (повтор → 409),
неизвестный id → 404, доступ только под сессией (401 без логина).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "sponsors@example.com"
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


def test_create_sponsor_returns_201_with_fields(client):
    resp = client.post(
        "/sponsors",
        json={
            "name": "Nike",
            "description": "Спортивная экипировка",
            "url": "https://nike.com",
            "logo_path": "sponsors/nike.png",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["name"] == "Nike"
    assert body["description"] == "Спортивная экипировка"
    assert body["url"] == "https://nike.com"
    assert body["logo_path"] == "sponsors/nike.png"


def test_create_sponsor_optional_fields_default_none(client):
    body = client.post("/sponsors", json={"name": "Локальный зал"}).json()
    assert body["description"] is None
    assert body["url"] is None
    assert body["logo_path"] is None


def test_create_sponsor_requires_name(client):
    assert client.post("/sponsors", json={"description": "Без имени"}).status_code == 422


def test_list_sponsors_returns_all_sorted_by_name(client):
    client.post("/sponsors", json={"name": "Reebok"})
    client.post("/sponsors", json={"name": "Adidas"})
    resp = client.get("/sponsors")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["Adidas", "Reebok"]  # отсортировано по имени


def test_read_sponsor_by_id(client):
    created = client.post("/sponsors", json={"name": "Puma"}).json()
    resp = client.get(f"/sponsors/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Puma"


def test_read_unknown_sponsor_returns_404(client):
    assert client.get("/sponsors/999").status_code == 404


def test_update_sponsor_changes_fields(client):
    created = client.post("/sponsors", json={"name": "Asics"}).json()
    resp = client.patch(
        f"/sponsors/{created['id']}",
        json={"description": "Беговые кроссовки", "url": "https://asics.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Беговые кроссовки"
    assert body["url"] == "https://asics.com"
    assert body["name"] == "Asics"  # не затёрто частичным апдейтом


def test_update_unknown_sponsor_returns_404(client):
    assert client.patch("/sponsors/999", json={"name": "x"}).status_code == 404


def test_delete_sponsor(client):
    created = client.post("/sponsors", json={"name": "Under Armour"}).json()
    resp = client.delete(f"/sponsors/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/sponsors/{created['id']}").status_code == 404  # удалён


def test_delete_unknown_sponsor_returns_404(client):
    assert client.delete("/sponsors/999").status_code == 404


def test_duplicate_name_returns_409(client):
    client.post("/sponsors", json={"name": "Nike"})
    resp = client.post("/sponsors", json={"name": "Nike"})
    assert resp.status_code == 409  # name уникален


def test_update_to_duplicate_name_returns_409(client):
    client.post("/sponsors", json={"name": "Nike"})
    other = client.post("/sponsors", json={"name": "Adidas"}).json()
    resp = client.patch(f"/sponsors/{other['id']}", json={"name": "Nike"})
    assert resp.status_code == 409  # переименование в занятое имя → конфликт


def test_sponsors_require_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sponsors").status_code == 401
