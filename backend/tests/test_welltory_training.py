"""Разбор скрина Welltory «Анализ тренировки» (ядро 9671): нормализация ответа модели без
вызова vision (parse_training_response — чистая функция). Ключевое: длительность ч/м → минуты,
знак нагрузки сохраняется, пропуски → None, мусорный JSON → VisionParseError (не падение)."""

import pytest

from app.services.welltory_training import VisionParseError, parse_training_response


def test_parse_core_fields():
    raw = (
        '{"время": "1 ч 5 мин", "всего_ккал": "573 ккал", "активные_ккал": "489 ккал",'
        ' "всего_мет": "509 МЕТ", "полезные_мет": "241 МЕТ", "пульс_средний": "123",'
        ' "пульс_макс": "162", "нагрузка": "-8%", "оценка": "3"}'
    )
    v = parse_training_response(raw)
    assert v.duration_min == 65  # 1ч 5м → 65
    assert (v.total_kcal, v.active_kcal) == (573, 489)
    assert (v.total_met, v.useful_met) == (509, 241)
    assert (v.hr_avg, v.hr_max) == (123, 162)
    assert v.load_pct == -8  # знак сохранён (в отличие от kcal/МЕТ)
    assert v.score == 3


def test_negative_load_unicode_minus():
    assert parse_training_response('{"нагрузка": "−12 %"}').load_pct == -12  # − → -


def test_missing_fields_none():
    v = parse_training_response('{"всего_ккал": "573 ккал"}')
    assert v.total_kcal == 573
    assert v.duration_min is None and v.hr_avg is None and v.load_pct is None


def test_json_wrapped_in_markdown():
    assert parse_training_response('```json\n{"всего_ккал": 573}\n```').total_kcal == 573


def test_invalid_json_raises():
    with pytest.raises(VisionParseError):
        parse_training_response("это не json")
