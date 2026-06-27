"""M0·B9 — скоупинг роутов тела/веса/фото: чтение видит только записи владельца.

Залогинен user(id=1). Данные user(id=2) заведены напрямую в БД. Проверяем, что
роуты body/weight/inbody/progress/body_photos не отдают и не трогают чужие записи:
списки пусты, одиночные → 404, ряды прогресса не считают чужое, апсёрт веса по дню
не перетирает чужую строку того же дня. 404 (а не 403) — чтобы не раскрывать факт
существования чужой записи.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.body import BodyMeasurement, InbodyMeasurement, ProgressPhoto
from app.models.goal import GoalStatus, SmartGoal
from app.models.user import User

EMAIL = "owner@example.com"
PASSWORD = "right-password"
OTHER_DATE = dt.date(2026, 6, 21)


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


@pytest.fixture
def other(engine, tmp_path):
    """Чужой user(id=2) с полным набором записей тела: обхваты, InBody, фото.

    Файл фото реально пишется на диск (абсолютный путь), чтобы 404 на /body-photos/{id}
    был следствием именно проверки владельца, а не отсутствия файла."""
    photo_file = tmp_path / "other.jpg"
    photo_file.write_bytes(b"not-really-a-jpeg")
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        body = BodyMeasurement(user_id=2, date=OTHER_DATE, waist_cm=99, chest_cm=120)
        inbody = InbodyMeasurement(user_id=2, date=OTHER_DATE, weight_kg=99.0, body_fat_pct=33.0)
        photo = ProgressPhoto(user_id=2, date=OTHER_DATE, source_image_path=str(photo_file))
        for row in (body, inbody, photo):
            session.add(row)
        session.commit()
        session.refresh(body)
        session.refresh(inbody)
        session.refresh(photo)
        return {"body": body.id, "inbody": inbody.id, "photo": photo.id}


# --- body_measurement -------------------------------------------------------


def test_list_measurements_excludes_other_user(client, other):
    assert client.get("/body-measurements").json() == []


def test_list_measurements_by_date_excludes_other_user(client, other):
    assert client.get("/body-measurements", params={"date": OTHER_DATE.isoformat()}).json() == []


def test_get_other_measurement_returns_404(client, other):
    assert client.get(f"/body-measurements/{other['body']}").status_code == 404


def test_patch_other_measurement_returns_404(client, other):
    resp = client.patch(f"/body-measurements/{other['body']}", json={"waist_cm": 1})
    assert resp.status_code == 404


def test_delete_other_measurement_returns_404(client, other):
    assert client.delete(f"/body-measurements/{other['body']}").status_code == 404


# --- progress (body / inbody) ------------------------------------------------


def test_body_progress_excludes_other_user(client, other):
    body = client.get("/progress/body").json()
    assert body["weight_kg"] == []
    assert all(series == [] for series in body["circumferences"].values())


def test_inbody_progress_excludes_other_user(client, other):
    composition = client.get("/progress/inbody").json()["composition"]
    assert all(series == [] for series in composition.values())


def test_goal_progress_excludes_other_user_weight(client, engine, other):
    # Активная цель есть (заводим напрямую), но вес чужого InBody не должен в неё попасть:
    # у залогиненного юзера своих замеров нет → current/baseline = None.
    with Session(engine) as session:
        session.add(
            SmartGoal(user_id=1, status=GoalStatus.active, target_metrics_json={"weight_kg": 80.0})
        )
        session.commit()
    metrics = client.get("/progress/goal").json()["metrics"]
    weight = next(m for m in metrics if m["metric"] == "weight_kg")
    assert weight["current"] is None
    assert weight["baseline"] is None


def test_goal_progress_ignores_other_users_active_goal(client, engine, other):
    # Активная цель ТОЛЬКО у чужого юзера (id=2). Залогинен id=1 без своей цели → 404,
    # а не чужая цель (раньше /progress/goal брал первую активную цель без скоупа по user_id —
    # межаккаунтная утечка: цель одного против замеров другого).
    with Session(engine) as session:
        session.add(
            SmartGoal(user_id=2, status=GoalStatus.active, target_metrics_json={"weight_kg": 70.0})
        )
        session.commit()
    assert client.get("/progress/goal").status_code == 404


# --- body_photos -------------------------------------------------------------


def test_list_photos_excludes_other_user(client, other):
    assert client.get("/body-photos").json() == []


def test_get_other_photo_returns_404(client, other):
    assert client.get(f"/body-photos/{other['photo']}").status_code == 404


# --- weight upsert: не перетирать чужой день ---------------------------------


def test_weight_upsert_does_not_clobber_other_user(client, engine, other):
    # У чужого юзера уже есть InBody-замер за OTHER_DATE с весом 99. Залогиненный
    # пишет свой вес за тот же день — должна появиться НОВАЯ строка (его), а чужая
    # остаться нетронутой (вес 99).
    resp = client.post("/body/weight", json={"date": OTHER_DATE.isoformat(), "weight_kg": 70.0})
    assert resp.status_code == 201
    assert resp.json()["weight_kg"] == 70.0
    with Session(engine) as session:
        rows = session.exec(
            select(InbodyMeasurement)
            .where(InbodyMeasurement.date == OTHER_DATE)
            .order_by(InbodyMeasurement.id)
        ).all()
        by_user = {r.user_id: r.weight_kg for r in rows}
        assert by_user == {1: 70.0, 2: 99.0}  # чужая (id=2) не тронута


# --- владелец видит своё, но не чужое ---------------------------------------


def test_owner_sees_own_not_other(client, other):
    own = client.post("/body-measurements", json={"date": "2026-06-22", "waist_cm": 80}).json()
    listed = client.get("/body-measurements").json()
    assert [m["id"] for m in listed] == [own["id"]]  # ровно своё, без чужого
    assert client.get(f"/body-measurements/{own['id']}").status_code == 200
