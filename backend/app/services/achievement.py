"""Генератор ачивок (S5.1): дисциплина + уровень → Opus → тированный набор → запись.

Связывает три слоя в один проход (тот же приём, что в S4.4):
- ``build_prompt`` — преамбула безопасности + дисциплина + уровень + строгая схема S5.1;
- ``llm.text`` — вызов MODEL_RECO (Opus) через ProxyAPI;
- ``achievement_schema`` — строгая схема выхода + валидация тиров и безопасности с ретраем.

Результат сохраняется как строки ``Achievement`` (FK sport_id), где ``level`` хранит тир
сложности, ``status="locked"`` — ачивка ещё не выполнена. Сетевую/парс-ошибку пробрасываем
наверх (``llm.LLMError`` / ``InvalidAchievementSetError``) — если валидный набор получить не
удалось, в БД ничего не пишем.

Расхождение с формулировкой карточки (зафиксировано осознанно): карточка говорит «при
создании вида спорта генерить ачивки», но генерация вынесена в отдельное действие
(POST /sports/{id}/achievements/generate), а не встроена в POST /sports. Причины: (1) так уже
сделано в проекте — S4 вынес LLM-генерацию в кнопку (/recommendations/generate), а не в
сайд-эффект; (2) встраивание в CRUD сломало бы создание спорта и его тесты и завязало бы
каждый create на живой LLM; (3) действие переиспользуемо с выбором уровня. См. отчёт S5.1.
"""

import json

from sqlmodel import Session

from app.core.config import settings
from app.models.achievement import Achievement
from app.models.sport import Sport
from app.services import llm
from app.services.achievement_schema import (
    ACHIEVEMENT_SET_EXAMPLE,
    AthleteLevel,
    achievement_set_json_schema,
    generate_valid_achievement_set,
)

# Преамбула: что строим и правила тирования/безопасности. Согласована со схемой S5.1,
# чтобы текст промпта не противоречил валидатору (тиры + защита новичка).
_SAFETY_FRAMING = """\
Ты — тренер-методист для ОДНОГО пользователя личного трекера. Составь набор ачивок \
(достижений-вызовов) под конкретную дисциплину, разбитый по ТИРАМ сложности — от базовых к \
продвинутым.

Принципы (соблюдай всегда):
1. Тируй по сложности: каждой ачивке проставь tier из foundation < intermediate < advanced < \
elite так, чтобы набор охватывал минимум два разных тира и вёл от простого к сложному.
2. Уважай уровень атлета (level). Новичку (beginner) НЕ предлагай опасные трюки: никаких \
элементов с серьёзным риском травмы или обязательной страховкой. Держи набор новичка не выше \
тира intermediate.
3. is_dangerous ставь честно: true — если трюк несёт реальный риск травмы, падения с высоты \
или требует сложной страховки. Для beginner такие ачивки в набор не включай вовсе.
4. Привязывай ачивки к самой дисциплине — конкретные навыки и трюки этого спорта \
(вейкборд: старт из воды → прыжок через кильватер → рейли; BMX: банни-хоп → бар-спин; \
эндуро: баланс на месте → стойка 10 секунд; кайт: контроль купола → первый прыжок).
5. Формулировки конкретные и измеримые; тон поддерживающий, без обещаний нереального."""


def build_prompt(sport: Sport, level: AthleteLevel) -> str:
    """Собрать промпт: преамбула + дисциплина + уровень + строгая JSON-схема выхода и пример.

    Один пользовательский месседж (преамбула играет роль системной инструкции). Схема и
    пример берутся из S5.1, поэтому форма запроса и форма парсинга гарантированно совпадают.
    """
    sport_block = {
        "name": sport.name,
        "type": sport.type.value,
        "description": sport.description,
    }
    return (
        f"{_SAFETY_FRAMING}\n\n"
        "ДИСЦИПЛИНА (JSON):\n"
        f"{json.dumps(sport_block, ensure_ascii=False, indent=2)}\n\n"
        f"УРОВЕНЬ АТЛЕТА: {level.value}\n\n"
        "ВЫХОД (СТРОГО): верни РОВНО один JSON-объект по схеме ниже и НИЧЕГО больше — "
        "без markdown, без ``` и без текста до или после. Поле level в ответе обязано быть "
        f"равно '{level.value}'. Весь текст значений — на русском.\n"
        "JSON-схема ответа:\n"
        f"{json.dumps(achievement_set_json_schema(), ensure_ascii=False)}\n\n"
        "Пример валидного ответа:\n"
        f"{json.dumps(ACHIEVEMENT_SET_EXAMPLE, ensure_ascii=False, indent=2)}"
    )


def generate_achievements(
    session: Session,
    sport: Sport,
    level: AthleteLevel,
    *,
    model: str | None = None,
    attempts: int = 3,
) -> list[Achievement]:
    """Сгенерировать и сохранить ачивки: дисциплина+уровень → Opus → парс → запись.

    Промпт отдаётся в Opus (MODEL_RECO по умолчанию), ответ валидируется по схеме S5.1 с
    ретраем отбраковки (тиры + безопасность под уровень). Каждая ачивка сохраняется строкой
    ``Achievement`` (tier → поле ``level``). Если валидный набор не получить — ничего не пишем.
    """
    model_name = model or settings.model_reco
    prompt = build_prompt(sport, level)

    def produce() -> str:
        return llm.text(prompt, model=model_name)

    result = generate_valid_achievement_set(produce, expected_level=level, attempts=attempts)

    created = [
        Achievement(
            sport_id=sport.id,
            title=spec.title,
            description=spec.description,
            level=spec.tier.value,  # тир сложности хранится в поле level модели
            status="locked",
        )
        for spec in result.achievements
    ]
    session.add_all(created)
    session.commit()
    for achievement in created:
        session.refresh(achievement)
    return created
