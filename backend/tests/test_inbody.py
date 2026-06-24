"""Vision-разбор скрина InBody с гибкой схемой (S2.10).

Закрывает критерии карточки:
- на тестовом InBody-скрине ключевые поля извлечены (вес, %жира, мыш.масса,
  висцеральный жир, вода) — типизированные float;
- неизвестные/прочие поля сохраняются в metrics_json как вернула модель;
- пропущенные/нечитаемые поля → None, не падение;
- невалидный (не-JSON) ответ модели поднимает контролируемую InbodyParseError.

Сеть не дёргаем — llm.vision мокаем. Реальный вызов по настоящему скрину InBody
проверяется вручную по smoke-guide (требует OPENROUTER_API_KEY и картинку).
"""

import json

import pytest

from app.core.config import settings
from app.services import inbody

# Показания репрезентативного InBody-скрина: пять ключевых ключей (как просит
# промпт) + произвольные «прочие» показатели — то, что модель вернёт строками.
SCREEN_JSON = {
    "вес": "75.3 kg",
    "процент_жира": "18.2 %",
    "мышечная_масса": "32.1 kg",
    "висцеральный_жир": "8",
    "вода": "45.6 L",
    "BMI": "23.4",
    "Белок": "10.8 kg",
    "Базовый обмен": "1623 kcal",
    "Метаболический возраст": "27",
}

# Ключи пяти ключевых полей — всё остальное должно уехать в metrics_json.
_KNOWN = {"вес", "процент_жира", "мышечная_масса", "висцеральный_жир", "вода"}


def test_parse_full_screen_extracts_key_fields():
    iv = inbody.parse_inbody_response(json.dumps(SCREEN_JSON, ensure_ascii=False))

    # ключевые поля извлечены как float, единицы отрезаны
    assert iv.weight_kg == 75.3
    assert iv.body_fat_pct == 18.2
    assert iv.muscle_mass_kg == 32.1
    assert iv.visceral_fat == 8.0
    assert iv.water == 45.6
    assert iv.raw == SCREEN_JSON


def test_unknown_fields_saved_to_metrics_json():
    iv = inbody.parse_inbody_response(json.dumps(SCREEN_JSON, ensure_ascii=False))

    # прочие показатели сохранены как вернула модель, без потерь
    assert iv.metrics_json == {
        "BMI": "23.4",
        "Белок": "10.8 kg",
        "Базовый обмен": "1623 kcal",
        "Метаболический возраст": "27",
    }
    # ни один из пяти ключевых ключей не попал в metrics_json
    assert not (_KNOWN & set(iv.metrics_json))


def test_no_extra_fields_means_empty_metrics_json():
    iv = inbody.parse_inbody_response('{"вес": "80 kg", "процент_жира": "20 %"}')

    assert iv.weight_kg == 80.0
    assert iv.body_fat_pct == 20.0
    assert iv.metrics_json == {}


def test_parse_strips_markdown_fence_and_prose():
    wrapped = "Распознал:\n```json\n" + json.dumps(SCREEN_JSON, ensure_ascii=False) + "\n```"
    iv = inbody.parse_inbody_response(wrapped)

    assert iv.weight_kg == 75.3
    assert iv.metrics_json["BMI"] == "23.4"


def test_missing_key_fields_become_none():
    iv = inbody.parse_inbody_response('{"вес": "75.3 kg", "Печень": "норма"}')

    assert iv.weight_kg == 75.3
    # остальные ключевые поля в ответе отсутствовали
    assert iv.body_fat_pct is None
    assert iv.muscle_mass_kg is None
    assert iv.visceral_fat is None
    assert iv.water is None
    # незнакомое поле всё равно сохранено
    assert iv.metrics_json == {"Печень": "норма"}


def test_explicit_null_and_unreadable_values_become_none():
    iv = inbody.parse_inbody_response(
        '{"вес": null, "процент_жира": "—", "мышечная_масса": "не видно", "вода": "45,6 л"}'
    )

    assert iv.weight_kg is None  # null → None
    assert iv.body_fat_pct is None  # «—» без цифр → None
    assert iv.muscle_mass_kg is None  # текст без чисел → None
    assert iv.water == 45.6  # запятая-разделитель разобрана


@pytest.mark.parametrize(
    "raw",
    ["не json вовсе", "", "```\nничего полезного\n```", "[1, 2, 3]", "42", "null"],
)
def test_invalid_response_raises_controlled_error(raw):
    # «невалидный ответ модели не роняет сервер»: контролируемая ошибка.
    with pytest.raises(inbody.InbodyParseError):
        inbody.parse_inbody_response(raw)


@pytest.mark.parametrize(
    "value,number",
    [
        ("75.3 kg", 75.3),
        ("18,2 %", 18.2),
        ("8", 8.0),
        ("45.6 L", 45.6),
        ("1,5 кг", 1.5),
        (75.3, 75.3),
        (8, 8.0),
        (None, None),
        ("—", None),
        ("норма", None),
        (True, None),
    ],
)
def test_float_parsing(value, number):
    assert inbody._parse_float(value) == number


def test_parse_inbody_screen_calls_vision_with_prompt(monkeypatch):
    captured: dict = {}

    def fake_vision(image_bytes, prompt, model=None):
        captured["image"] = image_bytes
        captured["prompt"] = prompt
        captured["model"] = model
        return json.dumps(SCREEN_JSON, ensure_ascii=False)

    monkeypatch.setattr(inbody.llm, "vision", fake_vision)

    iv = inbody.parse_inbody_screen(b"\x89PNG\r\n\x1a\nfake")

    assert iv.weight_kg == 75.3
    assert captured["image"] == b"\x89PNG\r\n\x1a\nfake"
    assert captured["prompt"] == inbody.INBODY_PROMPT
    assert captured["model"] is None  # модель vision по умолчанию
    # промпт перечисляет все пять ключевых ключей
    for key in _KNOWN:
        assert key in inbody.INBODY_PROMPT


def test_vision_model_is_configurable(monkeypatch):
    captured: dict = {}

    def fake_vision(image_bytes, prompt, model=None):
        captured["model"] = model
        return json.dumps(SCREEN_JSON, ensure_ascii=False)

    monkeypatch.setattr(inbody.llm, "vision", fake_vision)
    inbody.parse_inbody_screen(b"x", model="claude-haiku-4-5")

    assert captured["model"] == "claude-haiku-4-5"
    assert settings.model_vision  # модель по умолчанию задана в конфиге
