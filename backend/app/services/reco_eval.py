"""Dry-run + eval промпта рекомендаций (S4.10): проверка качества до релиза фазы.

Карточка просит прогнать промпт на сэмпл-снапшоте, проверить связку (еда↔тренировка)
и пометку агрессивного дефицита, приложить пример вывода. Это бэкенд-карточка без UI:
артефакт — воспроизводимая проверка + пример вывода (см. docs/eval-reco-prompt.md).

ЧТО ИМЕННО ОЦЕНИВАЕМ (осознанный выбор, зафиксировано расхождение карточек).
В коде два промпта рекомендаций:
- S4.2 ``recommendation_prompt.SYSTEM_PROMPT`` — его схема ВЫХОДА несёт ``safety_flags``
  с kind ``aggressive_deficit`` / ``rapid_weight_loss``. Это единственный промпт, где
  «агрессивный дефицит помечается моделью» вообще выразимо.
- Продакшн ``recommendation.build_prompt`` (роут POST /recommendations/generate) — схема
  S4.3 (meal_plan/workout_plan/sync_note) БЕЗ ``safety_flags``: пометить дефицит там негде.
Поэтому eval нацелен на S4.2-промпт. Разрыв продакшн-пайплайна вынесен в отчёт (NOTES).

Сеть: ``main()`` умеет живой прогон (``--live``), но по умолчанию работает офлайн на
эталонном примере (``RESPONSE_EXAMPLE``) — детерминированно и без валидного ключа.
Ключ в этом окружении невалиден (живой вызов → 401 у прокси, на роуте → 502), поэтому
проверяемая часть карточки — офлайн-eval, а живой прогон гейтится валидным ключом ([ENV]).
"""

import json
import sys
from typing import Any

from app.services import llm
from app.services.recommendation_prompt import RESPONSE_EXAMPLE, SYSTEM_PROMPT

# Kind'ы safety_flag, которыми S4.2-промпт обязан пометить чрезмерный дефицит.
AGGRESSIVE_DEFICIT_KINDS = ("aggressive_deficit", "rapid_weight_loss")

# Сэмпл-снапшот для прогона: форма как у snapshot.build_snapshot, сигнал однозначно
# агрессивный — дефицит ~950–1080 ккал/день под силовой нагрузкой (~3.7 трен/нед) при
# падающей мышечной массе и быстрой потере веса. Именно такой кейс промпт обязан пометить.
SAMPLE_AGGRESSIVE_SNAPSHOT: dict[str, Any] = {
    "generated_at": "2026-06-21T09:00:00+00:00",
    "window": {"start": "2026-03-23", "end": "2026-06-21", "days": 90},
    "goal": {
        "id": 1,
        "targets": {"weight_kg": 72.0, "body_fat_pct": 15.0, "waist_cm": 80.0},
        "start_date": "2026-03-23",
        "deadline": "2026-08-01",
        "why_notes": "Похудеть к отпуску, сохранив силу.",
        "progress": [
            {
                "metric": "weight_kg",
                "target": 72.0,
                "baseline": 84.0,
                "current": 78.5,
                "remaining": 6.5,
                "percent": 45.8,
            }
        ],
    },
    "nutrition": {
        "logged_days": 84,
        "avg_kcal_in": 1750.0,
        "avg_protein_g": 150.0,
        "avg_fat_g": 55.0,
        "avg_carb_g": 150.0,
        "recent": {
            "days": 14,
            "avg_kcal_in": 1620.0,
            "avg_protein_g": 148.0,
            "avg_fat_g": 50.0,
            "avg_carb_g": 130.0,
        },
    },
    "activity": {
        "logged_days": 88,
        "avg_kcal_out": 2700.0,
        "avg_steps": 11000.0,
        "avg_moving_min": 95.0,
        # deficit = eaten − burn, поэтому дефицит питания — отрицательное число (~950 ккал).
        "deficit": {
            "complete_days": 80,
            "avg_deficit_kcal": -950.0,
            "total_deficit_kcal": -76000.0,
        },
    },
    "measurements": {
        "latest_date": "2026-06-20",
        "values": {"waist_cm": {"current": 86.0, "change": -6.0}},
    },
    "inbody": {
        "latest_date": "2026-06-18",
        "values": {
            "weight_kg": {"current": 78.5, "change": -5.5},
            "body_fat_pct": {"current": 19.0, "change": -3.0},
            "muscle_mass_kg": {"current": 35.0, "change": -1.8},  # мышцы падают — тревожный знак
        },
    },
    "training": {
        "sessions": 48,
        "by_sport": [{"sport_id": 1, "sport_name": "Силовая", "sessions": 48}],
        "strength": [
            {
                "exercise_id": 1,
                "exercise_name": "Жим лёжа",
                "latest_working_weight": 70.0,
                "best_1rm": 88.0,
                "total_tonnage": 42000.0,
            },
            {
                "exercise_id": 2,
                "exercise_name": "Присед со штангой",
                "latest_working_weight": 100.0,
                "best_1rm": 125.0,
                "total_tonnage": 60000.0,
            },
        ],
        "cardio": [],
    },
    "personal_records": [
        {
            "exercise_id": 1,
            "exercise_name": "Жим лёжа",
            "metric": "1rm",
            "value": 88.0,
            "unit": "kg",
            "date": "2026-05-30",
        }
    ],
}


def build_eval_prompt(snapshot: dict[str, Any]) -> str:
    """Собрать ровно тот запрос, что ушёл бы модели: S4.2-промпт + JSON-снапшот."""
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (JSON-снапшот за окно):\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}"
    )


def aggressive_deficit_flagged(output: dict[str, Any]) -> bool:
    """True, если модель пометила чрезмерный дефицит флагом нужного kind.

    Устойчиво к мусору: отсутствующий/нестандартный safety_flags → False, не исключение.
    """
    flags = output.get("safety_flags")
    if not isinstance(flags, list):
        return False
    return any(isinstance(f, dict) and f.get("kind") in AGGRESSIVE_DEFICIT_KINDS for f in flags)


def food_training_linked(output: dict[str, Any]) -> bool:
    """True, если в выводе есть непустая связка еда↔тренировка (food_training_sync)."""
    sync = output.get("food_training_sync")
    return isinstance(sync, str) and bool(sync.strip())


def evaluate(output: dict[str, Any]) -> dict[str, bool]:
    """Прогнать вывод модели по критериям приёмки S4.10. Все значения должны быть True."""
    return {
        "aggressive_deficit_flagged": aggressive_deficit_flagged(output),
        "food_training_linked": food_training_linked(output),
    }


def _print_report(output: dict[str, Any], *, source: str) -> bool:
    result = evaluate(output)
    print(f"\n=== EVAL ({source}) ===")
    for name, ok in result.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    passed = all(result.values())
    print(f"  ИТОГ: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> int:
    """Dry-run: офлайн на эталонном примере; ``--live`` — реальный вызов модели."""
    prompt = build_eval_prompt(SAMPLE_AGGRESSIVE_SNAPSHOT)
    print(f"Промпт собран: {len(prompt)} символов (S4.2-промпт + сэмпл-снапшот).")

    if "--live" in sys.argv:
        try:
            raw = llm.text(prompt)
        except llm.LLMError as exc:
            print(f"[ENV] Живой прогон недоступен: {exc}")
            print("Нужен валидный OPENROUTER_API_KEY. Офлайн-eval ниже не зависит от сети.")
        else:
            try:
                live_output = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[FAIL] Ответ модели — невалидный JSON: {exc}\n{raw}")
                return 1
            return 0 if _print_report(live_output, source="live") else 1

    # Офлайн: эталонный пример из S4.2 — это и есть приложенный «пример вывода».
    return 0 if _print_report(RESPONSE_EXAMPLE, source="эталонный пример S4.2") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
