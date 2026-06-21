"""Vision-разбор скрина активности Welltory (S1.9).

Закрывает критерии карточки:
- ответ модели разбирается в типизированную ActivityVision (поля осмысленны);
- пропущенные/нечитаемые поля → None, не падение;
- невалидный (не-JSON) ответ модели поднимает контролируемую VisionParseError,
  а не роняет процесс.

Сеть не дёргаем — llm.vision мокаем. Реальный вызов по IMG_9605.PNG проверяется
вручную по smoke-guide (требует настоящий ANTHROPIC_API_KEY).
"""

import json

import pytest

from app.core.config import settings
from app.services import welltory

# Показания плиток IMG_9605.PNG (docs/sample-formats.md): то, что модель должна
# вернуть строками, ровно как на экране.
SCREEN_JSON = {
    "всего_ккал": "1218 ккал",
    "активные_ккал": "683 ккал",
    "шаги": "4459",
    "в_движении": "2ч 53м",
    "без_движения": "21ч 57м",
    "разминка": "7ч",
    "активные_мет": "782 МЕТ",
    "интенсивные_мет": "0 МЕТ",
}


def test_parse_full_screen_normalises_every_field():
    av = welltory.parse_activity_response(json.dumps(SCREEN_JSON, ensure_ascii=False))

    assert av.total_kcal == 1218
    assert av.active_kcal == 683
    assert av.steps == 4459
    assert av.moving_min == 173  # 2ч 53м
    assert av.idle_min == 1317  # 21ч 57м
    assert av.warmup_min == 420  # 7ч
    assert av.active_met == 782
    assert av.intense_met == 0
    assert av.raw == SCREEN_JSON


def test_parse_strips_markdown_fence_and_prose():
    wrapped = "Вот данные:\n```json\n" + json.dumps(SCREEN_JSON, ensure_ascii=False) + "\n```"
    av = welltory.parse_activity_response(wrapped)

    assert av.total_kcal == 1218
    assert av.steps == 4459


def test_missing_fields_become_none():
    av = welltory.parse_activity_response('{"шаги": "4459", "всего_ккал": "1218 ккал"}')

    assert av.steps == 4459
    assert av.total_kcal == 1218
    # остальные плитки в ответе отсутствовали
    assert av.active_kcal is None
    assert av.moving_min is None
    assert av.idle_min is None
    assert av.warmup_min is None
    assert av.active_met is None
    assert av.intense_met is None


def test_explicit_null_and_unreadable_values_become_none():
    av = welltory.parse_activity_response(
        '{"шаги": null, "всего_ккал": "—", "в_движении": "не видно", "активные_мет": "782 МЕТ"}'
    )

    assert av.steps is None  # null → None
    assert av.total_kcal is None  # «—» без цифр → None
    assert av.moving_min is None  # текст без ч/м → None
    assert av.active_met == 782  # читаемое поле всё равно разобрано


@pytest.mark.parametrize(
    "raw",
    ["не json вовсе", "", "```\nничего полезного\n```", "[1, 2, 3]", "42", "null"],
)
def test_invalid_response_raises_controlled_error(raw):
    # «невалидный ответ модели не роняет сервер»: контролируемая ошибка, не KeyError/прочее.
    with pytest.raises(welltory.VisionParseError):
        welltory.parse_activity_response(raw)


@pytest.mark.parametrize(
    "value,minutes",
    [
        ("2ч 53м", 173),
        ("7ч", 420),
        ("0 мин", 0),
        ("21ч 57м", 1317),
        ("1ч 5м", 65),
        (None, None),
        ("без единиц", None),
    ],
)
def test_duration_parsing(value, minutes):
    assert welltory._parse_duration_min(value) == minutes


@pytest.mark.parametrize(
    "value,number",
    [
        ("1218 ккал", 1218),
        ("4459", 4459),
        ("782 МЕТ", 782),
        ("0 МЕТ", 0),
        ("1 218 ккал", 1218),
        (4459, 4459),
        (None, None),
        ("—", None),
        (True, None),
    ],
)
def test_int_parsing(value, number):
    assert welltory._parse_int(value) == number


def test_parse_activity_screen_calls_vision_with_prompt(monkeypatch):
    captured: dict = {}

    def fake_vision(image_bytes, prompt, model=None):
        captured["image"] = image_bytes
        captured["prompt"] = prompt
        captured["model"] = model
        return json.dumps(SCREEN_JSON, ensure_ascii=False)

    monkeypatch.setattr(welltory.llm, "vision", fake_vision)

    av = welltory.parse_activity_screen(b"\x89PNG\r\n\x1a\nfake")

    assert av.total_kcal == 1218
    assert captured["image"] == b"\x89PNG\r\n\x1a\nfake"
    assert captured["prompt"] == welltory.ACTIVITY_PROMPT
    # модель vision по умолчанию (llm.vision сам подставит settings.model_vision)
    assert captured["model"] is None
    # промпт перечисляет все восемь ключей карточки
    for key in SCREEN_JSON:
        assert key in welltory.ACTIVITY_PROMPT


def test_vision_model_is_configurable(monkeypatch):
    captured: dict = {}

    def fake_vision(image_bytes, prompt, model=None):
        captured["model"] = model
        return json.dumps(SCREEN_JSON, ensure_ascii=False)

    monkeypatch.setattr(welltory.llm, "vision", fake_vision)
    welltory.parse_activity_screen(b"x", model="claude-haiku-4-5")

    # явная модель пробрасывается в llm.vision как есть
    assert captured["model"] == "claude-haiku-4-5"
    assert settings.model_vision  # конфиг доступен (модель по умолчанию задана)
