"""Генерация рекомендации (S4.4): снапшот → вызов Opus → парс по схеме → запись.

Связывает три готовых слоя в один проход:
- S4.1 `snapshot.build_snapshot` — собирает срез данных пользователя (вход модели);
- S4.3 `recommendation_schema` — строгая схема выхода + валидация с ретраем;
- `llm.text` — вызов MODEL_RECO (Opus) через ProxyAPI.

Результат сохраняется как `Recommendation` (input_snapshot_json, output_json, raw_text,
model, goal_id) — сырой текст модели хранится для отладки рядом с распарсенным планом.

Расхождение между карточками (зафиксировано осознанно): системный промпт S4.2
(`recommendation_prompt.SYSTEM_PROMPT`) описывает ИНУЮ форму выхода
(summary/assessment/recommendations/...), чем схема S4.3, по которой здесь идёт парсинг.
Карточка S4.4 требует «распарсить ПО СХЕМЕ», а парсер с валидацией/ретраем есть только у
S4.3, поэтому промпт согласован именно с её формой (meal_plan/workout_plan). Принципы
безопасности из S4.2 переиспользованы как преамбула; см. отчёт S4.4.
"""

import json
import time
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.models.recommendation import Recommendation
from app.services import llm
from app.services.recommendation_schema import (
    PLAN_EXAMPLE,
    RecommendationPlan,
    generate_valid_plan,
    plan_json_schema,
)
from app.services.snapshot import DEFAULT_WINDOW_DAYS, build_snapshot

# Преамбула: принципы безопасности (канонический источник — SYSTEM_PROMPT из S4.2).
# Держим коротко и согласованно со схемой S4.3, чтобы промпт не противоречил парсеру.
_SAFETY_FRAMING = """\
Ты — помощник по составу тела и тренировкам для ОДНОГО пользователя личного трекера. \
Составь связный, безопасный и выполнимый план питания и тренировок по срезу его данных. \
Ты не врач и не ставишь диагнозов.

Принципы (соблюдай всегда):
1. Устойчивость важнее скорости: темп, который человек удержит неделями, без экстрима.
2. Калорийный дефицит не делай агрессивным; нагрузке нужно топливо — тренировочный день \
не беднее дня отдыха по калориям.
3. Прогрессию нагрузки поднимай малыми шагами, без резких скачков.
4. Согласуй питание с тренировками (в день тяжёлой силовой не режь углеводы).
5. Тон поддерживающий, без токсичности и обещаний нереальных результатов.
6. Опирайся только на данные снапшота; не выдумывай числа. Любая секция может быть null \
(данных нет) — тогда давай осторожный план и не сочиняй отсутствующие показатели."""


def build_prompt(snapshot: dict[str, Any]) -> str:
    """Собрать промпт: преамбула + снапшот + строгая JSON-схема выхода и пример.

    Один пользовательский месседж (преамбула играет роль системной инструкции) — этого
    достаточно для задачи и не требует расширять `llm.text`. Схема и пример берутся из
    S4.3, поэтому форма запроса и форма парсинга гарантированно совпадают.
    """
    return (
        f"{_SAFETY_FRAMING}\n\n"
        "ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (JSON-снапшот за окно):\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\n"
        "ВЫХОД (СТРОГО): верни РОВНО один JSON-объект по схеме ниже и НИЧЕГО больше — "
        "без markdown, без ``` и без текста до или после. Весь текст значений — на русском.\n"
        "JSON-схема ответа:\n"
        f"{json.dumps(plan_json_schema(), ensure_ascii=False)}\n\n"
        "Пример валидного ответа:\n"
        f"{json.dumps(PLAN_EXAMPLE, ensure_ascii=False, indent=2)}"
    )


def generate_recommendation(
    session: Session,
    *,
    user_id: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
    model: str | None = None,
    attempts: int = 3,
) -> Recommendation:
    """Сгенерировать и сохранить рекомендацию: снапшот → Opus → парс → запись.

    Снапшот собирается из БД (вход модели), отдаётся в Opus (MODEL_RECO по умолчанию),
    ответ парсится по схеме S4.3 с ретраем отбраковки (`generate_valid_plan`). Сохраняется
    распарсенный план (`output_json`) вместе с сырым текстом успешной попытки (`raw_text`).
    Сетевую/парс-ошибку пробрасываем наверх (`llm.LLMError` / `InvalidPlanError`) — ничего
    не пишем в БД, если валидный план получить не удалось.
    """
    snapshot = build_snapshot(session, window_days=window_days)
    model_name = model or settings.model_reco
    prompt = build_prompt(snapshot)

    # Захватываем сырой текст КАЖДОЙ попытки: после успеха здесь лежит raw, которому
    # соответствует распарсенный план (успешная попытка отрабатывает последней).
    captured: dict[str, str] = {}

    def produce() -> str:
        raw = llm.text(prompt, model=model_name)
        captured["raw"] = raw
        return raw

    # S4.9: засекаем именно генерацию (вызовы модели + ретраи парса) — снапшот собирается
    # локально и копейки не стоит. monotonic — на случай перевода системных часов.
    started = time.monotonic()
    plan: RecommendationPlan = generate_valid_plan(produce, attempts=attempts)
    generation_ms = round((time.monotonic() - started) * 1000)

    goal = snapshot.get("goal")
    recommendation = Recommendation(
        user_id=user_id,
        model=model_name,
        input_snapshot_json=snapshot,
        output_json=plan.model_dump(mode="json"),
        raw_text=captured["raw"],
        goal_id=goal["id"] if goal else None,
        generation_ms=generation_ms,
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)
    return recommendation
