"""Eval промпта рекомендаций (S4.10): офлайн-проверка критериев приёмки.

Сети нет — прогон детерминированный. Проверяем, что:
- эталонный пример S4.2 (приложенный «пример вывода») проходит ОБА критерия:
  помечает агрессивный дефицит и несёт связку еда↔тренировка;
- eval имеет «зубы» — вывод без флага дефицита проваливает проверку;
- собранный запрос реально несёт агрессивный сигнал сэмпл-снапшота и инструкцию
  пометить дефицит (иначе прогон бессмыслен).
"""

import json

from app.services import reco_eval
from app.services.recommendation_prompt import RESPONSE_EXAMPLE


def test_canonical_example_passes_both_criteria():
    """Критерии приёмки: приложенный пример вывода помечает дефицит и даёт связку."""
    result = reco_eval.evaluate(RESPONSE_EXAMPLE)
    assert result == {"aggressive_deficit_flagged": True, "food_training_linked": True}


def test_rapid_weight_loss_kind_also_counts():
    """Промпт разрешает оба kind для чрезмерного дефицита — eval засчитывает оба."""
    output = {
        "safety_flags": [{"kind": "rapid_weight_loss", "message": "Слишком быстро."}],
        "food_training_sync": "Углеводы вокруг силовой.",
    }
    assert reco_eval.aggressive_deficit_flagged(output) is True


def test_output_without_flag_fails():
    """Без флага дефицита (или с нерелевантным kind) критерий FAIL — у eval есть зубы."""
    no_flag = {"safety_flags": [], "food_training_sync": "Связка есть."}
    other_kind = {
        "safety_flags": [{"kind": "data_gap", "message": "Мало данных."}],
        "food_training_sync": "Связка есть.",
    }
    assert reco_eval.aggressive_deficit_flagged(no_flag) is False
    assert reco_eval.aggressive_deficit_flagged(other_kind) is False
    assert reco_eval.evaluate(no_flag)["aggressive_deficit_flagged"] is False


def test_missing_food_training_sync_fails():
    """Пустая/отсутствующая связка еда↔тренировка → FAIL по второму критерию."""
    assert reco_eval.food_training_linked({"food_training_sync": "   "}) is False
    assert reco_eval.food_training_linked({}) is False


def test_eval_is_robust_to_garbage():
    """Мусорный вывод модели не роняет eval — обе проверки просто False."""
    assert reco_eval.evaluate({}) == {
        "aggressive_deficit_flagged": False,
        "food_training_linked": False,
    }
    assert reco_eval.aggressive_deficit_flagged({"safety_flags": "не список"}) is False


def test_prompt_carries_aggressive_signal_and_instruction():
    """Собранный запрос несёт сэмпл-снапшот (агрессивный дефицит) и приказ его пометить."""
    prompt = reco_eval.build_eval_prompt(reco_eval.SAMPLE_AGGRESSIVE_SNAPSHOT)
    # Сигнал снапшота: отрицательный (дефицитный) средний баланс калорий ушёл в промпт.
    assert '"avg_deficit_kcal": -950.0' in prompt
    # Инструкция промпта: помечать агрессивный дефицит флагом safety_flags.
    assert "aggressive_deficit" in prompt
    assert "safety_flags" in prompt


def test_sample_snapshot_has_recommendation_shape():
    """Сэмпл-снапшот по форме совпадает с выходом snapshot.build_snapshot (это вход модели)."""
    snap = reco_eval.SAMPLE_AGGRESSIVE_SNAPSHOT
    assert {"goal", "nutrition", "activity", "training", "window"} <= set(snap)
    # Сериализуется в JSON без потерь (кладётся в промпт как есть).
    assert (
        json.loads(json.dumps(snap, ensure_ascii=False))["activity"]["deficit"]["avg_deficit_kcal"]
        == -950.0
    )
