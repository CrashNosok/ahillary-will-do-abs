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
from app.services import llm, research
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

# Инструкции по доказательной части отчёта (nutrition_analysis / evidence_narrative / citations).
_REPORT_INSTRUCTIONS = """\
ЗАДАЧА ОТЧЁТА (поля nutrition_analysis, evidence_narrative, citations):
- Определи активную цель пользователя из снапшота (goal: набор массы / снижение жира / \
поддержание) и адаптируй рекомендации под неё (профицит для массы, дефицит для сушки, \
баланс для поддержания).
- nutrition_analysis: разбери КАЧЕСТВО рациона по средним из снапшота (avg_carb_g, \
avg_fiber_g, avg_sugar_g, avg_complex_carb_g, avg_saturated_fat_g, avg_protein_g): сложные \
vs простые углеводы, клетчатка, сахар, насыщенные жиры, распределение белка. Дай целевые \
числа и пары «оценка→цель».
- evidence_narrative: развёрнутый markdown-отчёт с секциями под ## (энергобаланс под цель, \
белок, объём/частота тренировок, прогрессия, качество углеводов и клетчатка, \
восстановление/сон, добавки). КАЖДОЕ ключевое утверждение подкрепляй инлайн-ссылкой [id] \
на работу из БАЗЫ ИССЛЕДОВАНИЙ выше.
- citations: для КАЖДОГО использованного [id] — объект с этим id (точно как в базе), title, \
authors, year, url_or_doi, claim (что именно подкрепляет). Цитируй ТОЛЬКО id из базы.
- Опирайся на снапшот и на исследования; не выдумывай числа и источники."""


def build_prompt(snapshot: dict[str, Any], evidence_pack: str) -> str:
    """Собрать промпт: преамбула + снапшот + база исследований + инструкции + схема и пример.

    Один пользовательский месседж (преамбула играет роль системной инструкции). База
    исследований и инструкция «цитируй только эти id» дают модели доказательную опору и
    блокируют выдуманные ссылки (их добивает валидатор схемы по valid_ids).
    """
    return (
        f"{_SAFETY_FRAMING}\n\n"
        "ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (JSON-снапшот за окно):\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\n"
        "БАЗА ИССЛЕДОВАНИЙ (цитируй ТОЛЬКО эти работы по их id в квадратных скобках; "
        "НЕ выдумывай источники и НЕ ссылайся на id вне списка):\n"
        f"{evidence_pack}\n\n"
        f"{_REPORT_INSTRUCTIONS}\n\n"
        "ВЫХОД (СТРОГО): верни РОВНО один JSON-объект по схеме ниже и НИЧЕГО больше — без "
        "markdown-обёртки, без ``` и без текста до или после. Текст значений — на русском "
        "(id и DOI как есть); поле evidence_narrative — markdown внутри JSON-строки.\n"
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
    snapshot = build_snapshot(session, user_id=user_id, window_days=window_days)
    model_name = model or settings.model_reco

    # Корпус исследований → evidence-pack в промпт + множество валидных id для проверки цитат.
    corpus = research.load_corpus()
    evidence_pack = research.build_evidence_pack(research.select_studies(corpus, snapshot))
    valid_ids = research.valid_citation_ids(corpus)
    prompt = build_prompt(snapshot, evidence_pack)

    # Захватываем сырой текст КАЖДОЙ попытки: после успеха здесь лежит raw, которому
    # соответствует распарсенный план (успешная попытка отрабатывает последней).
    captured: dict[str, str] = {}

    def produce() -> str:
        # Большой отчёт: поднятый потолок токенов и таймаут (Opus генерит дольше).
        raw = llm.text(
            prompt,
            model=model_name,
            max_tokens=llm.REPORT_MAX_TOKENS,
            timeout=llm.REPORT_TIMEOUT_SECONDS,
        )
        captured["raw"] = raw
        return raw

    # S4.9: засекаем именно генерацию (вызовы модели + ретраи парса) — снапшот собирается
    # локально и копейки не стоит. monotonic — на случай перевода системных часов.
    started = time.monotonic()
    # valid_ids or None: пустой корпус (fail-open) отключает проверку id, а не валит всё в 502.
    plan: RecommendationPlan = generate_valid_plan(
        produce, attempts=attempts, valid_ids=valid_ids or None
    )
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
