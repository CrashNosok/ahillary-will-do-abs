"""PR-движок (S3.10): оценка 1ПМ, тоннаж, объём и детект персональных рекордов.

Закрывает критерии карточки:
- на известной серии подходов 1ПМ и PR верны (чистые функции + API);
- PR фиксируется только при реальном улучшении (вес/1ПМ для силовой, темп/дистанция кардио).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User
from app.models.workout import StrengthSet
from app.services.workout_metrics import (
    epley_1rm,
    strength_candidates,
    tonnage,
    volume_by_exercise,
)

EMAIL = "prs@example.com"
PASSWORD = "right-password"


# --- чистые функции: 1ПМ / тоннаж / объём (без БД) ---


def test_epley_on_known_values():
    # Epley: w*(1+reps/30). Известные значения, округление до 2 знаков.
    assert epley_1rm(100, 1) == round(100 * (1 + 1 / 30), 2) == 103.33
    assert epley_1rm(60, 10) == 80.0  # 60 * 4/3
    assert epley_1rm(70, 6) == 84.0  # 70 * 1.2
    assert epley_1rm(65, 8) == 82.33  # 65 * (1+8/30)


def test_epley_needs_positive_weight_and_reps():
    assert epley_1rm(None, 5) is None
    assert epley_1rm(80, None) is None
    assert epley_1rm(0, 5) is None
    assert epley_1rm(80, 0) is None


def _series() -> list[StrengthSet]:
    # известная серия по одному упражнению (id=1): (вес, повторы)
    return [
        StrengthSet(session_id=1, exercise_id=1, weight_kg=60, reps=10),  # 1ПМ 80.0
        StrengthSet(session_id=1, exercise_id=1, weight_kg=65, reps=8),  # 1ПМ 82.33
        StrengthSet(session_id=1, exercise_id=1, weight_kg=70, reps=6),  # 1ПМ 84.0
    ]


def test_tonnage_on_known_series():
    # 60*10 + 65*8 + 70*6 = 600 + 520 + 420 = 1540
    assert tonnage(_series()) == 1540.0


def test_tonnage_skips_incomplete_sets():
    sets = [
        StrengthSet(session_id=1, exercise_id=1, weight_kg=50, reps=5),  # 250
        StrengthSet(session_id=1, exercise_id=1, weight_kg=None, reps=5),  # пропуск
        StrengthSet(session_id=1, exercise_id=1, weight_kg=50, reps=None),  # пропуск
    ]
    assert tonnage(sets) == 250.0


def test_volume_by_exercise_groups_per_exercise():
    sets = [
        StrengthSet(session_id=1, exercise_id=1, weight_kg=60, reps=10),  # 600
        StrengthSet(session_id=1, exercise_id=1, weight_kg=40, reps=5),  # 200
        StrengthSet(session_id=1, exercise_id=2, weight_kg=80, reps=5),  # 400
    ]
    assert volume_by_exercise(sets) == {1: 800.0, 2: 400.0}


def test_strength_candidates_pick_max_weight_and_best_1rm():
    cands = {(c.metric, c.value) for c in strength_candidates(_series())}
    assert ("max_weight", 70.0) in cands  # самый тяжёлый подход
    assert ("best_1rm", 84.0) in cands  # лучшая оценка 1ПМ серии


# --- API: фиксация PR при создании сессий ---


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
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


def _make_exercise(client, name="Жим лёжа") -> int:
    payload = {"name": name + " спорт", "category": "strength"}
    sport_id = client.post("/sports", json=payload).json()["id"]
    return client.post("/exercises", json={"sport_id": sport_id, "name": name}).json()["id"]


def _post_strength(client, ex, sets, date="2026-06-21"):
    return client.post("/workouts", json={"date": date, "sets": sets})


def test_first_strength_session_sets_max_weight_and_1rm_prs(client):
    # критерий: на известной серии 1ПМ и PR верны. Первый результат — всегда рекорд.
    ex = _make_exercise(client)
    body = _post_strength(
        client,
        ex,
        [
            {"exercise_id": ex, "weight_kg": 60, "reps": 10},
            {"exercise_id": ex, "weight_kg": 65, "reps": 8},
            {"exercise_id": ex, "weight_kg": 70, "reps": 6},
        ],
    ).json()
    prs = {p["metric"]: p for p in body["personal_records"]}
    assert prs["max_weight"]["value"] == 70.0
    assert prs["max_weight"]["unit"] == "кг"
    assert prs["best_1rm"]["value"] == 84.0  # лучший 1ПМ серии (Epley)


def test_pr_only_on_real_improvement_strength(client):
    # критерий: PR фиксируется только при реальном улучшении.
    ex = _make_exercise(client)
    _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 70, "reps": 6}])  # 1ПМ 84

    # более лёгкая сессия — не бьёт ни вес, ни 1ПМ → ни одного нового PR
    weaker = _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 60, "reps": 5}]).json()
    assert weaker["personal_records"] == []

    # ровно тот же результат — не строгое улучшение → не PR
    same = _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 70, "reps": 6}]).json()
    assert same["personal_records"] == []

    # тяжелее — бьёт и вес, и 1ПМ → два новых PR
    stronger = _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 80, "reps": 6}]).json()
    metrics = {p["metric"]: p["value"] for p in stronger["personal_records"]}
    assert metrics["max_weight"] == 80.0
    assert metrics["best_1rm"] == 96.0  # 80*1.2

    # все рекорды читаются обратно через /workouts/prs
    all_prs = client.get("/workouts/prs").json()
    assert {(p["metric"], p["value"]) for p in all_prs} == {
        ("max_weight", 70.0),
        ("best_1rm", 84.0),
        ("max_weight", 80.0),
        ("best_1rm", 96.0),
    }


def test_better_1rm_at_lower_weight_is_a_pr(client):
    # 1ПМ-рекорд независим от веса: 60x12 (1ПМ 84) бьёт 70x6 (1ПМ 84)? нет — равен.
    # А 60x13 → 1ПМ 86 бьёт по 1ПМ, но не по весу (60<70).
    ex = _make_exercise(client)
    _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 70, "reps": 6}])  # 1ПМ 84, вес 70
    body = _post_strength(client, ex, [{"exercise_id": ex, "weight_kg": 60, "reps": 13}]).json()
    metrics = {p["metric"] for p in body["personal_records"]}
    assert "best_1rm" in metrics  # 60*(1+13/30)=86.0 > 84 → новый 1ПМ
    assert "max_weight" not in metrics  # 60 < 70 → вес не побит


# --- API: кардио PR (темп / дистанция) ---


def _make_cardio_exercise(client) -> int:
    sport_id = client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()["id"]
    return client.post("/exercises", json={"sport_id": sport_id, "name": "5 км"}).json()["id"]


def _post_cardio(client, ex, distance, duration, date="2026-06-21"):
    return client.post(
        "/workouts/cardio",
        json={"date": date, "exercise_id": ex, "distance_km": distance, "duration_sec": duration},
    )


def test_cardio_first_run_sets_pace_and_distance_prs(client):
    ex = _make_cardio_exercise(client)
    body = _post_cardio(client, ex, 5, 1500).json()  # темп 300 сек/км
    prs = {p["metric"]: p for p in body["personal_records"]}
    assert prs["best_pace"]["value"] == 300.0
    assert prs["best_pace"]["unit"] == "сек/км"
    assert prs["max_distance"]["value"] == 5.0


def test_cardio_pr_only_on_improvement(client):
    ex = _make_cardio_exercise(client)
    _post_cardio(client, ex, 5, 1500)  # темп 300, дистанция 5

    # быстрее на той же дистанции → новый рекорд темпа, дистанция не побита
    faster = _post_cardio(client, ex, 5, 1400).json()  # темп 280 < 300
    metrics = {p["metric"]: p["value"] for p in faster["personal_records"]}
    assert metrics == {"best_pace": 280.0}

    # дальше, но медленнее → новый рекорд дистанции, темп не побит
    longer = _post_cardio(client, ex, 8, 2400).json()  # темп 300 (не < 280), дистанция 8 > 5
    metrics = {p["metric"]: p["value"] for p in longer["personal_records"]}
    assert metrics == {"max_distance": 8.0}


def test_cardio_without_exercise_records_no_pr(client):
    # рекорды привязаны к упражнению; без exercise_id фиксировать нечего
    body = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 1500},
    ).json()
    assert body["personal_records"] == []
    assert client.get("/workouts/prs").json() == []


# --- API: метрики сессии (1ПМ/тоннаж/объём по упражнению и группе) ---


def test_workout_metrics_aggregates_tonnage_and_1rm(client):
    ex = _make_exercise(client, name="Присед")
    created = _post_strength(
        client,
        ex,
        [
            {"exercise_id": ex, "weight_kg": 60, "reps": 10},
            {"exercise_id": ex, "weight_kg": 70, "reps": 6},
        ],
    ).json()
    m = client.get(f"/workouts/{created['id']}/metrics").json()
    assert m["total_tonnage"] == 1020.0  # 600 + 420
    by_ex = {e["exercise_id"]: e for e in m["by_exercise"]}
    assert by_ex[ex]["tonnage"] == 1020.0
    assert by_ex[ex]["max_weight"] == 70.0
    assert by_ex[ex]["best_1rm"] == 84.0
    # объём по группе (виду спорта) — один вид → весь тоннаж там
    assert m["by_group"][0]["tonnage"] == 1020.0


def test_workout_metrics_unknown_session_404(client):
    assert client.get("/workouts/999/metrics").status_code == 404


def test_workout_metrics_groups_by_sport(client):
    # два упражнения в разных видах спорта → объём делится по группам
    ex1 = _make_exercise(client, name="Жим")
    ex2 = _make_exercise(client, name="Тяга")
    created = _post_strength(
        client,
        ex1,
        [
            {"exercise_id": ex1, "weight_kg": 50, "reps": 10},  # 500
            {"exercise_id": ex2, "weight_kg": 100, "reps": 5},  # 500
        ],
    ).json()
    m = client.get(f"/workouts/{created['id']}/metrics").json()
    assert m["total_tonnage"] == 1000.0
    group_tonnage = sorted(g["tonnage"] for g in m["by_group"])
    assert group_tonnage == [500.0, 500.0]  # по 500 в каждой группе
    assert len(m["by_group"]) == 2
