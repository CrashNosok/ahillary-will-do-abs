"""ИИ-рекомендация по конкретному виду спорта (#1): срез данных вида → LLM → markdown-совет.

Контекст вида: цели по упражнениям (с текущим лучшим из PR) + план навыков (достижения по
статусам: учу/доступно/освоено) + сводка последних тренировок в этом виде. Модель даёт
конкретные, безопасные шаги. Результат upsert-ится в sport_advice (последний совет на
user+sport). Сеть/ошибку модели пробрасываем как llm.LLMError — роут отдаёт 502.
"""

import datetime as dt
import json
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.models._time import utcnow
from app.models.achievement import Achievement
from app.models.exercise_target import ExerciseTarget
from app.models.sport import Exercise, Sport
from app.models.sport_advice import SportAdvice
from app.models.workout import PersonalRecord, WorkoutSession
from app.services import llm

WINDOW_DAYS = 90
_STATUS_RU = {"in_progress": "учу", "locked": "доступно", "unlocked": "освоено"}

_FRAMING = (
    "Ты — тренер-помощник по виду спорта для ОДНОГО пользователя личного трекера. По срезу его "
    "данных дай конкретные, безопасные и выполнимые рекомендации, как двигаться к целям по "
    "упражнениям и осваивать навыки из плана. Не выдумывай числа — опирайся только на данные. "
    "Прогрессию поднимай малыми шагами, технику ставь раньше веса/сложности. Тон "
    "поддерживающий.\n\n"
    "Структурируй ответ в markdown с заголовками:\n"
    "## Цели по упражнениям — как закрывать разрыв до цели.\n"
    "## Навыки — что и как тренировать (по приоритету: сначала «учу», затем доступные).\n"
    "## Ближайшие шаги (2–4 недели) — короткий конкретный список.\n"
    "Без вступления и заключения вне этих секций."
)


def _build_context(session: Session, sport: Sport, *, user_id: int) -> dict[str, Any]:
    """Компактный контекст вида для промпта (цели упражнений + навыки + недавние тренировки)."""
    exercises = session.exec(select(Exercise).where(Exercise.sport_id == sport.id)).all()
    ex_by_id = {e.id: e for e in exercises}
    # Цели только по упражнениям этого вида — фильтр в SQL (не тянем все цели пользователя).
    targets = (
        {
            t.exercise_id: t
            for t in session.exec(
                select(ExerciseTarget).where(
                    ExerciseTarget.user_id == user_id,
                    ExerciseTarget.exercise_id.in_(list(ex_by_id)),
                )
            ).all()
        }
        if ex_by_id
        else {}
    )
    # Текущий лучший результат по упражнению (макс среди PR) — для оценки разрыва до цели.
    best: dict[int, float] = {}
    if targets:
        for rec in session.exec(
            select(PersonalRecord).where(
                PersonalRecord.user_id == user_id,
                PersonalRecord.exercise_id.in_(list(targets)),
            )
        ).all():
            best[rec.exercise_id] = max(best.get(rec.exercise_id, rec.value), rec.value)

    exercise_targets = [
        {
            "exercise": ex_by_id[eid].name,
            "target": t.target_value,
            "unit": t.unit or ex_by_id[eid].unit,
            "current_best": best.get(eid),
        }
        for eid, t in targets.items()
    ]

    skills: dict[str, list[str]] = {"учу": [], "доступно": [], "освоено": []}
    for a in session.exec(
        select(Achievement).where(
            Achievement.user_id == user_id, Achievement.sport_id == sport.id
        )
    ).all():
        skills[_STATUS_RU.get(a.status, "доступно")].append(a.title)

    today = dt.date.today()
    start = today - dt.timedelta(days=WINDOW_DAYS - 1)
    recent_sessions = session.exec(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.sport_id == sport.id,
            WorkoutSession.date >= start,
            WorkoutSession.date <= today,
        )
    ).all()

    return {
        "sport": sport.name,
        "category": sport.category,
        "exercise_targets": exercise_targets,
        "skill_plan": skills,
        "recent_sessions_90d": len(recent_sessions),
    }


def generate_sport_advice(
    session: Session, sport: Sport, *, user_id: int, model: str | None = None
) -> SportAdvice:
    """Сгенерировать и сохранить (upsert) ИИ-совет по виду. llm.LLMError пробрасывается."""
    context = _build_context(session, sport, user_id=user_id)
    model_name = model or settings.model_reco
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    prompt = f"{_FRAMING}\n\nДАННЫЕ ВИДА (JSON):\n{context_json}"
    text = llm.text(prompt, model=model_name)

    existing = session.exec(
        select(SportAdvice).where(
            SportAdvice.user_id == user_id, SportAdvice.sport_id == sport.id
        )
    ).first()
    advice = existing or SportAdvice(user_id=user_id, sport_id=sport.id, text="", model=model_name)
    advice.text = text
    advice.model = model_name
    advice.created_at = utcnow()
    session.add(advice)
    session.commit()
    session.refresh(advice)
    return advice


def latest_sport_advice(session: Session, sport_id: int, *, user_id: int) -> SportAdvice | None:
    """Последний сохранённый совет по виду для пользователя (или None)."""
    return session.exec(
        select(SportAdvice).where(
            SportAdvice.user_id == user_id, SportAdvice.sport_id == sport_id
        )
    ).first()
