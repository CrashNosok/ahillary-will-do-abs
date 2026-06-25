"""Модели ядра + ингеста (S1.1): create_all поднимает все таблицы, гибкие поля — JSON."""

from datetime import date

from sqlalchemy import JSON, inspect
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — импорт регистрирует таблицы в SQLModel.metadata
from app.models import ActivityDay, HrZones, InbodyMeasurement

# Имена таблиц из карточки (snake_case заданы через __tablename__, иначе было бы "foodentry").
_EXPECTED_TABLES = {
    "user",
    "smart_goal",
    "food_entry",
    "activity_day",
    "hr_zones",
    "deficit_day",
    "body_measurement",
    "inbody_measurement",
}


def _memory_engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


def test_create_all_builds_every_core_table():
    tables = set(inspect(_memory_engine()).get_table_names())
    assert _EXPECTED_TABLES <= tables  # критерий: таблицы создаются через create_all


def test_flexible_fields_are_json_columns():
    # критерий: гибкие raw/metrics-поля — JSON-колонки
    assert isinstance(ActivityDay.__table__.c.raw_json.type, JSON)
    assert isinstance(HrZones.__table__.c.zones_json.type, JSON)
    assert isinstance(InbodyMeasurement.__table__.c.metrics_json.type, JSON)


def test_user_profile_fields_have_defaults():
    # критерий M0·B2: доп. поля профиля с дефолтами (display_name пусто, is_active=True)
    from app.models.user import User

    user = User(email="x@example.com", password_hash="h")
    assert user.display_name is None
    assert user.is_active is True


def test_json_column_roundtrips_dict():
    engine = _memory_engine()
    payload = {"всего_ккал": 1218, "tiles": {"steps": 4459}}
    with Session(engine) as session:
        session.add(ActivityDay(user_id=1, date=date(2026, 6, 20), raw_json=payload))
        session.commit()
    with Session(engine) as session:
        row = session.exec(select(ActivityDay)).one()
    assert row.raw_json == payload  # dict сериализуется/читается через JSON-колонку


# --- S1.2: тренировки + LLM + ачивки ---

_S12_TABLES = {
    "sport",
    "exercise",
    "workout_session",
    "strength_set",
    "cardio_log",
    "skill_log",
    "personal_record",
    "recommendation",
    "achievement",
    "achievement_proof",
}

# (таблица, кортеж колонок) -> таблица, на которую FK обязан ссылаться. Ключ — кортеж
# (а не одна колонка), потому что после M0·B7 у workout_session появился композитный FK
# (user_id, activity_date) → activity_day, и та же колонка user_id участвует ещё и в FK на
# user — по одной колонке такие FK не различить. Кортежи отсортированы для устойчивости.
_EXPECTED_FKS = {
    ("exercise", ("sport_id",)): "sport",
    ("workout_session", ("sport_id",)): "sport",
    # связь с Welltory-днём, перепривязана композитным FK в M0·B7 (раньше — одиночный на date)
    ("workout_session", ("activity_date", "user_id")): "activity_day",
    ("workout_session", ("user_id",)): "user",  # владелец сессии (M0·B3)
    ("strength_set", ("session_id",)): "workout_session",
    ("strength_set", ("exercise_id",)): "exercise",
    ("cardio_log", ("session_id",)): "workout_session",
    ("cardio_log", ("exercise_id",)): "exercise",
    ("skill_log", ("session_id",)): "workout_session",
    ("skill_log", ("exercise_id",)): "exercise",
    ("personal_record", ("exercise_id",)): "exercise",
    ("personal_record", ("user_id",)): "user",  # владелец рекорда (M0·B3)
    ("achievement", ("sport_id",)): "sport",
    ("achievement", ("user_id",)): "user",  # владелец ачивки (M0·B6)
    ("achievement_proof", ("achievement_id",)): "achievement",
    ("recommendation", ("goal_id",)): "smart_goal",
    ("recommendation", ("user_id",)): "user",  # владелец рекомендации (M0·B5)
}


def test_create_all_builds_every_s12_table():
    tables = set(inspect(_memory_engine()).get_table_names())
    assert _S12_TABLES <= tables  # критерий: все таблицы создаются


def test_foreign_keys_reference_expected_tables():
    # критерий: FK на sport/exercise/session (и др.) согласованы
    insp = inspect(_memory_engine())
    actual = {
        (table, tuple(sorted(fk["constrained_columns"]))): fk["referred_table"]
        for table in _S12_TABLES
        for fk in insp.get_foreign_keys(table)
    }
    assert actual == _EXPECTED_FKS


# --- M0·B4: владелец данных в body-кластере ---
# Каждая таблица кластера получает user_id FK -> user (изоляция данных по пользователю).
_B4_USER_FK_TABLES = ("body_measurement", "inbody_measurement", "progress_photo", "hr_zones")


def test_body_cluster_tables_have_user_id_fk():
    # критерий M0·B4: у каждой таблицы body-кластера user_id ссылается на user
    insp = inspect(_memory_engine())
    for table in _B4_USER_FK_TABLES:
        fks = {
            col: fk["referred_table"]
            for fk in insp.get_foreign_keys(table)
            for col in fk["constrained_columns"]
        }
        assert fks.get("user_id") == "user", table


# --- M0·B5: владелец данных в nutrition-кластере ---
# food_entry, smart_goal, recommendation, deficit_day получают user_id FK -> user.
_B5_USER_FK_TABLES = ("food_entry", "smart_goal", "recommendation", "deficit_day")


def test_nutrition_cluster_tables_have_user_id_fk():
    # критерий M0·B5: у каждой таблицы кластера питания/целей user_id ссылается на user
    insp = inspect(_memory_engine())
    for table in _B5_USER_FK_TABLES:
        fks = {
            col: fk["referred_table"]
            for fk in insp.get_foreign_keys(table)
            for col in fk["constrained_columns"]
        }
        assert fks.get("user_id") == "user", table


# --- M0·B7: день активности изолирован по пользователю (составной PK) ---


def test_activity_day_has_composite_pk_and_user_fk():
    # критерий M0·B7: PK activity_day = (user_id, date), user_id ссылается на user
    insp = inspect(_memory_engine())
    pk = set(insp.get_pk_constraint("activity_day")["constrained_columns"])
    assert pk == {"user_id", "date"}
    fks = {
        col: fk["referred_table"]
        for fk in insp.get_foreign_keys("activity_day")
        for col in fk["constrained_columns"]
    }
    assert fks.get("user_id") == "user"


def test_workout_session_activity_link_is_composite_fk():
    # критерий M0·B7: FK workout_session.activity_date перепривязан на составной PK дня
    insp = inspect(_memory_engine())
    composite = [
        fk
        for fk in insp.get_foreign_keys("workout_session")
        if fk["referred_table"] == "activity_day"
    ]
    assert len(composite) == 1
    fk = composite[0]
    assert set(fk["constrained_columns"]) == {"user_id", "activity_date"}
    assert set(fk["referred_columns"]) == {"user_id", "date"}


# --- M2·B16: флаг «превзошёл себя» на сессии тренировки ---


def test_workout_session_surpassed_self_defaults_false():
    # критерий M2·B16: новая колонка surpassed_self — bool с дефолтом False
    from app.models.workout import WorkoutSession

    ws = WorkoutSession(user_id=1, date=date(2026, 6, 25))
    assert ws.surpassed_self is False
