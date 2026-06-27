"""Стартовый сид: единственный пользователь + базовый каталог дисциплин.

Создаётся один раз (юзер — если таблица `user` пуста, спорт — если такого имени ещё
нет): повторный старт дублей не плодит.
"""

import datetime as dt

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import hash_password
from app.models.achievement import Achievement
from app.models.challenge import Challenge
from app.models.sport import (
    Exercise,
    Sport,
    SportCategory,
    SportEvent,
    SportLevel,
    SportMentor,
    SportRecommendation,
)
from app.models.user import User

# Базовый каталог дисциплин (M7·B37): встроенные виды спорта приложения.
# Идемпотентность держится на уникальном Sport.name — повтор пропускает уже заведённые.
BASE_SPORTS: tuple[tuple[str, SportCategory, str], ...] = (
    ("Зал", SportCategory.strength, "Силовые тренировки в тренажёрном зале — железо и тренажёры."),
    ("Кайт", SportCategory.action, "Кайтсёрфинг — катание по воде на доске с воздушным змеем."),
    ("Эндуро", SportCategory.action, "Внедорожные мотогонки по пересечённой местности."),
    ("Вейкборд", SportCategory.action, "Катание по воде на доске за катером или лебёдкой."),
    ("Падел", SportCategory.racket, "Падел — ракеточный спорт на корте со стенами, играют парами."),
    # +7 новых дисциплин (разные категории, для полноты каталога):
    ("Бокс", SportCategory.combat, "Ударное единоборство руками в перчатках."),
    ("Футбол", SportCategory.team, "Командная игра с мячом ногами на поле."),
    ("Баскетбол", SportCategory.team, "Командная игра: забросить мяч в кольцо соперника."),
    ("Теннис", SportCategory.racket, "Ракеточный спорт на корте через сетку, 1×1 или 2×2."),
    ("Плавание", SportCategory.endurance, "Циклическая выносливость в воде разными стилями."),
    ("Йога", SportCategory.artistic, "Гибкость, баланс и дыхание через асаны."),
    ("Сноуборд", SportCategory.action, "Катание по снегу на доске — трассы и парк."),
    ("Кардио", SportCategory.endurance, "Кардио на пульсе: бег, велосипед, гребля, скакалка."),
)

# Лестницы уровней базовых дисциплин (M7·B38): по сидированной дисциплине — упорядоченный
# набор ступеней (code, label). rank — позиция в лестнице (1 — низшая), берётся из порядка.
# Падел использует реальную любительскую градацию D/D+/C/C+/…; остальные — осмысленная
# прогрессия от новичка к мастеру. Ключи обязаны совпадать с именами из BASE_SPORTS.
BASE_SPORT_LEVELS: dict[str, tuple[tuple[str, str], ...]] = {
    "Падел": (
        ("D", "D"),
        ("D+", "D+"),
        ("C", "C"),
        ("C+", "C+"),
        ("B", "B"),
        ("B+", "B+"),
        ("A", "A"),
    ),
    "Зал": (
        ("novice", "Новичок"),
        ("amateur", "Любитель"),
        ("confident", "Уверенный"),
        ("advanced", "Продвинутый"),
        ("athlete", "Атлет"),
    ),
    "Кайт": (
        ("discovery", "Дискавери"),
        ("beginner", "Новичок"),
        ("intermediate", "Уверенный"),
        ("independent", "Самостоятельный райдер"),
        ("advanced", "Продвинутый"),
    ),
    "Эндуро": (
        ("novice", "Новичок"),
        ("hobby", "Хобби"),
        ("expert", "Эксперт"),
        ("pro", "Профи"),
    ),
    "Вейкборд": (
        ("beginner", "Новичок"),
        ("intermediate", "Уверенный"),
        ("advanced", "Продвинутый"),
        ("pro", "Профи"),
    ),
    "Бокс": (
        ("novice", "Новичок"),
        ("amateur", "Любитель"),
        ("fighter", "Боец"),
        ("master", "Мастер"),
    ),
    "Футбол": (
        ("amateur", "Любитель"),
        ("league", "Лига"),
        ("semipro", "Полупро"),
        ("pro", "Профи"),
    ),
    "Баскетбол": (
        ("street", "Дворовый"),
        ("amateur", "Любитель"),
        ("league", "Лига"),
        ("pro", "Профи"),
    ),
    "Теннис": (
        ("beginner", "Начинающий"),
        ("improver", "Развивающийся"),
        ("intermediate", "Средний"),
        ("advanced", "Продвинутый"),
        ("open", "Открытый"),
    ),
    "Плавание": (
        ("novice", "Новичок"),
        ("technique", "Техника"),
        ("endurance", "Выносливость"),
        ("master", "Мастер"),
    ),
    "Йога": (
        ("start", "Начало"),
        ("practice", "Практик"),
        ("advanced", "Продвинутый"),
        ("teacher", "Учитель"),
    ),
    "Сноуборд": (
        ("green", "Зелёная"),
        ("blue", "Синяя"),
        ("red", "Красная"),
        ("black", "Чёрная"),
    ),
    "Кардио": (
        ("start", "Старт"),
        ("base", "База"),
        ("tempo", "Темп"),
        ("endurance", "Выносливость"),
        ("athlete", "Атлет"),
    ),
}

# Богатый контент каждой дисциплины (2026-06-27): развёрнутое описание, упражнения, событие,
# наставник, рекомендация и встроенный челлендж. Цель — чтобы у КАЖДОГО вида был полный набор
# (карточки/детальная страница не пустуют). Идемпотентность: упражнения/события/наставники/
# рекомендации — по (sport_id, имя/заголовок), челлендж — по (sport_id, title). Ключи обязаны
# совпадать с именами из BASE_SPORTS.
SportContent = dict[str, object]
SPORT_CONTENT: dict[str, SportContent] = {
    "Зал": {
        "long": "Работа с отягощениями для силы, массы и рельефа: базовые движения со штангой, "
        "гантелями и на тренажёрах, прогрессия нагрузки от тренировки к тренировке.",
        "exercises": (
            ("Жим лёжа", "strength", "кг"),
            ("Приседания со штангой", "strength", "кг"),
            ("Становая тяга", "strength", "кг"),
            ("Жим стоя", "strength", "кг"),
            ("Подтягивания", "strength", "повторы"),
        ),
        "event": ("Открытый турнир по жиму лёжа", 30, "Москва"),
        "mentor": ("Сергей Тарасов", "Мастер спорта по пауэрлифтингу, тренер с 12-летним стажем."),
        "rec": (
            "С чего начать",
            "Освойте технику базовых движений с пустым грифом, прежде чем добавлять вес.",
        ),
        "challenge": ("Жим 100 кг", "Доведи рабочий жим лёжа до 100 кг и сними чистый подход."),
    },
    "Кайт": {
        "long": "Кайтсёрфинг: управляешь воздушным змеем и скользишь по воде на доске. "
        "Зависит от ветра — от первых стартов с воды до прыжков и трюков.",
        "exercises": (
            ("Рестарт кайта с воды", "skill", "попытки"),
            ("Вотерстарт", "skill", "попытки"),
            ("Ход против ветра", "skill", "метры"),
            ("Поворот (тэк)", "skill", "попытки"),
            ("Прыжок", "skill", "попытки"),
        ),
        "event": ("Кайт-кэмп на Должанке", 45, "Должанская коса"),
        "mentor": ("Анна Морозова", "IKO-инструктор, 8 сезонов обучения на воде и снегу."),
        "rec": (
            "Безопасность прежде всего",
            "Учи систему сброса (чикенлуп) и правила траффика до первого самостоятельного старта.",
        ),
        "challenge": ("Первый прыжок", "Сделай контролируемый прыжок и приземлись на ходу."),
    },
    "Эндуро": {
        "long": "Внедорожные мотогонки по пересечённой местности: грязь, корни, броды и подъёмы. "
        "Техника баланса, работа газом и выносливость важнее голой скорости.",
        "exercises": (
            ("Баланс на месте", "skill", "сек"),
            ("Проезд по бревну", "skill", "попытки"),
            ("Подъём в гору стоя", "skill", "попытки"),
            ("Развороты восьмёркой", "skill", "попытки"),
            ("Преодоление брода", "skill", "попытки"),
        ),
        "event": ("Хард-эндуро трофи", 60, "Карелия"),
        "mentor": ("Дмитрий Волков", "КМС по мотокроссу, гид по эндуро-маршрутам."),
        "rec": (
            "Стоя устойчивее",
            "Большую часть бездорожья проезжай стоя на подножках — так байк управляется ногами.",
        ),
        "challenge": ("Чистый круг", "Проедь технический круг трассы без касания ногой земли."),
    },
    "Вейкборд": {
        "long": "Катание по воде на доске за катером или электролебёдкой. От уверенной стойки на "
        "воде до выпрыгиваний с волны, вращений и грэбов в парке.",
        "exercises": (
            ("Вставание на воде", "skill", "попытки"),
            ("Прыжок через волну", "skill", "попытки"),
            ("Грэб", "skill", "попытки"),
            ("Поворот 180°", "skill", "попытки"),
            ("Сёрфейс 360", "skill", "попытки"),
        ),
        "event": ("Wake Park Jam", 21, "Москва"),
        "mentor": ("Игорь Сафонов", "Чемпион региона по вейкборду, инструктор парка."),
        "rec": (
            "Колени мягкие",
            "Держи колени согнутыми и вес по центру доски — так гасишь удары о волну.",
        ),
        "challenge": ("Прыжок 180°", "Выпрыгни с волны и приземлись после поворота на 180°."),
    },
    "Падел": {
        "long": "Ракеточный спорт на корте со стеклянными стенами, играют парами. Мяч можно "
        "отыгрывать от стен — тактика, кисть и работа в паре важнее силы удара.",
        "exercises": (
            ("Подача снизу", "skill", "попытки"),
            ("Отскок от задней стены", "skill", "попытки"),
            ("Volley у сетки", "skill", "попытки"),
            ("Удар бандеха", "skill", "попытки"),
            ("Смэш", "skill", "попытки"),
        ),
        "event": ("Любительский турнир Padel Open", 28, "Сочи"),
        "mentor": ("Мария Гонсалес", "Тренер по падел-теннису, опыт игры в Испании."),
        "rec": (
            "Играй по стенам",
            "Не спеши бить — дай мячу отскочить от стекла, это открывает удобный угол.",
        ),
        "challenge": ("Серия из 20", "Удержи розыгрыш у стены: 20 ударов подряд без ошибки."),
    },
    "Бокс": {
        "long": "Ударное единоборство руками в перчатках: работа на дистанции, защита, "
        "комбинации и передвижения. Кардио, координация и характер.",
        "exercises": (
            ("Прямой (джеб)", "skill", "повторы"),
            ("Хук", "skill", "повторы"),
            ("Работа на скакалке", "cardio", "мин"),
            ("Работа на мешке", "skill", "раунды"),
            ("Работа на лапах", "skill", "раунды"),
        ),
        "event": ("Открытый ринг (спарринги)", 25, "Москва"),
        "mentor": ("Руслан Идрисов", "КМС по боксу, тренирует любителей и новичков."),
        "rec": (
            "Защита — это база",
            "Руки у подбородка, подбородок вниз: сначала научись не пропускать, потом бить.",
        ),
        "challenge": ("3 раунда", "Отработай 3 полных раунда на мешке без падения темпа."),
    },
    "Футбол": {
        "long": "Командная игра с мячом на поле: пас, контроль, удар и взаимодействие. "
        "От дворовой коробки до любительской лиги — техника плюс командная химия.",
        "exercises": (
            ("Жонглирование", "skill", "касания"),
            ("Пас в стенку", "skill", "повторы"),
            ("Удар по воротам", "skill", "попытки"),
            ("Дриблинг по конусам", "skill", "сек"),
            ("Приём мяча", "skill", "повторы"),
        ),
        "event": ("Любительский турнир 5×5", 35, "Москва"),
        "mentor": ("Алексей Громов", "Тренер ДЮСШ, специализация — техника и дриблинг."),
        "rec": (
            "Работай с двумя ногами",
            "Тренируй слабую ногу — предсказуемого игрока легко закрыть.",
        ),
        "challenge": ("100 касаний", "Прожонглируй мяч 100 касаний без падения на землю."),
    },
    "Баскетбол": {
        "long": "Командная игра: забросить мяч в кольцо соперника. Ведение, бросок, передачи и "
        "защита. От уличной площадки 3×3 до зала с полным составом.",
        "exercises": (
            ("Бросок со штрафной", "skill", "попадания"),
            ("Бросок с трёх", "skill", "попадания"),
            ("Ведение двумя руками", "skill", "мин"),
            ("Двойной шаг", "skill", "попытки"),
            ("Передача от груди", "skill", "повторы"),
        ),
        "event": ("Стритбол 3×3", 40, "Москва"),
        "mentor": ("Ольга Беляева", "Играла в студенческой лиге, тренер по броску."),
        "rec": (
            "Бросок — это рутина",
            "Отрабатывай одинаковую механику броска ежедневно: стабильность важнее силы.",
        ),
        "challenge": ("50 штрафных", "Забей 50 штрафных за тренировку и запиши процент попаданий."),
    },
    "Теннис": {
        "long": "Ракеточный спорт на корте через сетку, 1×1 или 2×2. Подача, форхенд, бэкхенд и "
        "перемещения. Сочетание техники, тактики и выносливости.",
        "exercises": (
            ("Подача", "skill", "попытки"),
            ("Форхенд по линии", "skill", "повторы"),
            ("Бэкхенд кросс", "skill", "повторы"),
            ("Удар с лёта (волей)", "skill", "повторы"),
            ("Смэш", "skill", "попытки"),
        ),
        "event": ("Теннисный турнир выходного дня", 33, "Москва"),
        "mentor": ("Виктор Лазарев", "Тренер с лицензией ITF, ставит технику с нуля."),
        "rec": (
            "Работа ног решает",
            "Мелкими шагами выставляйся под мяч заранее — половина ошибок от плохой позиции.",
        ),
        "challenge": ("Серия из 10", "Сыграй рандомный розыгрыш: 10 ударов через сетку подряд."),
    },
    "Плавание": {
        "long": "Циклическая выносливость в воде разными стилями: кроль, брасс, спина, баттерфляй. "
        "Техника дыхания и гребка важнее, чем грубая сила.",
        "exercises": (
            ("Кроль на технику", "cardio", "метры"),
            ("Брасс", "cardio", "метры"),
            ("Спина", "cardio", "метры"),
            ("Работа ног с доской", "cardio", "метры"),
            ("Дыхание на 3 счёта", "skill", "бассейны"),
        ),
        "event": ("Заплыв на открытой воде", 50, "Завидово"),
        "mentor": ("Екатерина Соколова", "Мастер спорта по плаванию, тренер по технике."),
        "rec": (
            "Длинный гребок",
            "Тянись вперёд и скользи: меньше частых гребков — дальше проплываешь на тех же силах.",
        ),
        "challenge": (
            "1 км без остановки",
            "Проплыви километр в спокойном темпе без отдыха на бортике.",
        ),
    },
    "Йога": {
        "long": "Гибкость, баланс и дыхание через асаны. Регулярная практика снимает зажимы, "
        "укрепляет корпус и учит управлять вниманием и дыханием.",
        "exercises": (
            ("Приветствие солнцу", "skill", "круги"),
            ("Поза планки", "strength", "сек"),
            ("Поза воина", "skill", "сек"),
            ("Поза дерева (баланс)", "skill", "сек"),
            ("Дыхание уджайи", "skill", "мин"),
        ),
        "event": ("Йога-ретрит выходного дня", 38, "Подмосковье"),
        "mentor": ("Нина Кравцова", "Сертифицированный преподаватель хатха- и виньяса-йоги."),
        "rec": (
            "Дыхание ведёт движение",
            "Не тянись через боль: входи в асану на выдохе и держи ровное дыхание.",
        ),
        "challenge": (
            "30 дней практики",
            "Практикуй минимум 15 минут каждый день в течение месяца.",
        ),
    },
    "Сноуборд": {
        "long": "Катание по снегу на доске — трассы и парк. От уверенных дуг на склоне до "
        "прыжков и джиббинга. Баланс, кант и чтение рельефа.",
        "exercises": (
            ("Резаные дуги", "skill", "спуски"),
            ("Олли", "skill", "попытки"),
            ("Торможение на канте", "skill", "попытки"),
            ("Поворот 180°", "skill", "попытки"),
            ("Джиб по перилам", "skill", "попытки"),
        ),
        "event": ("Открытие сезона на склоне", 55, "Шерегеш"),
        "mentor": ("Павел Зимин", "Инструктор по сноуборду, специализация — фрирайд."),
        "rec": (
            "Смотри туда, куда едешь",
            "Веди взгляд по линии спуска, а не под ноги — корпус сам доворачивает доску.",
        ),
        "challenge": ("Первый олли", "Выпрыгни на ровном ходу и приземлись на обе ноги."),
    },
    "Кардио": {
        "long": "Аэробная нагрузка в пульсовых зонах для сердца, выносливости и жиросжигания: "
        "бег, велосипед, гребля, скакалка, эллипс — всё, что держит пульс.",
        "exercises": (
            ("Бег трусцой", "cardio", "км"),
            ("Велозаезд", "cardio", "км"),
            ("Гребля", "cardio", "метры"),
            ("Интервалы", "cardio", "повторы"),
            ("Скакалка", "cardio", "мин"),
        ),
        "event": ("Кардио-челлендж выходного дня", 32, "Москва"),
        "mentor": ("Игорь Беляев", "Тренер по бегу и циклическим видам, специалист по пульсу."),
        "rec": (
            "Держи пульсовую зону",
            "Большую часть кардио делай в аэробной зоне (60–75% от максимума) — так растёт "
            "выносливость без перегруза.",
        ),
        "challenge": (
            "30 минут без остановки",
            "Продержи непрерывное кардио 30 минут в комфортном темпе.",
        ),
    },
}


# База упражнений для дисциплин ВНЕ базового каталога (заведены пользователем, но тоже
# должны иметь набор для отслеживания прогресса). Только упражнения (без события/ментора/
# челленджа) — добавляются идемпотентно по имени к виду, если он есть в каталоге. Так у
# каждой дисциплины набирается база ≥5 трекаемых движений (пользователь свои не добавляет).
EXTRA_SPORT_EXERCISES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "Бег": (
        ("Лёгкий бег", "cardio", "км"),
        ("Интервалы 400 м", "cardio", "повторы"),
        ("Темповый бег", "cardio", "км"),
        ("Длительный бег", "cardio", "км"),
        ("Бег в гору", "cardio", "повторы"),
    ),
    "Калистеника": (
        ("Подтягивания", "strength", "повторы"),
        ("Отжимания на брусьях", "strength", "повторы"),
        ("Отжимания от пола", "strength", "повторы"),
        ("Приседания на одной ноге", "strength", "повторы"),
        ("Планка", "strength", "сек"),
    ),
    "Скалолазание": (
        ("Боулдеринг-проблема", "skill", "попытки"),
        ("Трасса с верёвкой", "skill", "трассы"),
        ("Вис на зацепах", "strength", "сек"),
        ("Лазание на выносливость", "cardio", "трассы"),
        ("Подтягивания на турнике", "strength", "повторы"),
    ),
}


# Каталог навыков по видам спорта: «чему научиться» (тиры foundation→elite). Сеются как
# Achievement(status="locked") сид-юзеру — это план развития, который в «Мой кабинет» помечают
# «В план» (in_progress) и закрывают видео-пруфом (unlocked). Детерминированный список (а не
# только LLM-генерация) гарантирует, что у каждого вида есть с чего начать. Идемпотентно по
# (user_id, sport_id, title). Ключи обязаны совпадать с именами видов.
SPORT_SKILLS: dict[str, tuple[tuple[str, str], ...]] = {
    "Зал": (
        ("Чистая техника приседа и тяги", "foundation"),
        ("Подтягивания 10 раз подряд", "intermediate"),
        ("Жим лёжа = вес тела", "advanced"),
        ("Становая 2× вес тела", "elite"),
    ),
    "Кайт": (
        ("Уверенный вотерстарт", "foundation"),
        ("Ход против ветра и возврат", "intermediate"),
        ("Контролируемый прыжок", "advanced"),
        ("Прыжок с вращением (360)", "elite"),
    ),
    "Эндуро": (
        ("Баланс и трогание в горку", "foundation"),
        ("Проезд по бревну", "intermediate"),
        ("Чистый технический круг", "advanced"),
        ("Подъём по камням (хард-эндуро)", "elite"),
    ),
    "Вейкборд": (
        ("Уверенная стойка и резка", "foundation"),
        ("Прыжок через волну", "intermediate"),
        ("Грэб в прыжке", "advanced"),
        ("Рейли", "elite"),
    ),
    "Падел": (
        ("Подача и приём", "foundation"),
        ("Игра от задней стены", "intermediate"),
        ("Bandeja", "advanced"),
        ("Vibora / смэш с отскоком", "elite"),
    ),
    "Бокс": (
        ("Стойка и передвижение", "foundation"),
        ("Прямые и защита", "intermediate"),
        ("Связки в 3–4 удара", "advanced"),
        ("Спарринг 3 раунда", "elite"),
    ),
    "Футбол": (
        ("Приём и пас в одно касание", "foundation"),
        ("Дриблинг на скорости", "intermediate"),
        ("Удар с обеих ног", "advanced"),
        ("Гол с игры в матче", "elite"),
    ),
    "Баскетбол": (
        ("Стабильный штрафной", "foundation"),
        ("Ведение слабой рукой", "intermediate"),
        ("Бросок в прыжке", "advanced"),
        ("Трёхочковый стабильно", "elite"),
    ),
    "Теннис": (
        ("Стабильный розыгрыш", "foundation"),
        ("Подача в квадрат", "intermediate"),
        ("Удар с лёта", "advanced"),
        ("Кручёная подача", "elite"),
    ),
    "Плавание": (
        ("Дыхание и кроль 25 м", "foundation"),
        ("400 м без остановки", "intermediate"),
        ("Все четыре стиля", "advanced"),
        ("1 км на технике", "elite"),
    ),
    "Йога": (
        ("Приветствие солнцу", "foundation"),
        ("Планка 2 минуты", "intermediate"),
        ("Стойка на руках у стены", "advanced"),
        ("Стойка на руках без опоры", "elite"),
    ),
    "Сноуборд": (
        ("Резаные дуги", "foundation"),
        ("Олли с приземлением", "intermediate"),
        ("Поворот 180", "advanced"),
        ("Джиб по перилам", "elite"),
    ),
    "Кардио": (
        ("30 минут без остановки", "foundation"),
        ("Бег 5 км", "intermediate"),
        ("Интервалы по пульсовым зонам", "advanced"),
        ("10 км / полумарафон", "elite"),
    ),
    "Бег": (
        ("Лёгкий бег 30 минут", "foundation"),
        ("5 км без остановки", "intermediate"),
        ("10 км", "advanced"),
        ("Полумарафон", "elite"),
    ),
    "Калистеника": (
        ("Отжимания 20 раз", "foundation"),
        ("Подтягивания 10 раз", "intermediate"),
        ("Выход силой", "advanced"),
        ("Передний вис (front lever)", "elite"),
    ),
    "Скалолазание": (
        ("Трасса 5+", "foundation"),
        ("Боулдеринг 6A", "intermediate"),
        ("Трасса 6B+ с верёвкой", "advanced"),
        ("Боулдеринг 7A", "elite"),
    ),
}


# Базовый челлендж (M7·B39): встроенный вызов WIPEOUTS для категории action. У challenge
# обязательны sport_id и creator_user_id, поэтому привязываем его к первой глобальной
# action-дисциплине (фильтр is_global отсекает тест-данные) и к сид-юзеру как автору.
# is_base=True отделяет встроенный челлендж от пользовательских — UI рисует ему бейдж
# WIPEOUT и акцентную рамку на странице «Челленджи».
# Короткие подписи дисциплин из BASE_SPORTS (имя → description) — для бэкфилла пустых описаний
# у видов, заведённых ранними сидами без description (seed_sports их пропускает по имени).
BASE_SPORT_DESC: dict[str, str] = {name: desc for name, _category, desc in BASE_SPORTS}

BASE_CHALLENGE_TITLE = "WIPEOUTS"
BASE_CHALLENGE_DESCRIPTION = (
    "Серия заездов на грани контроля: держись на доске и не лови вайпаут. "
    "Упал — это вайпаут, отсчёт начинается заново."
)


def seed_user(session: Session) -> User | None:
    """Создаёт сид-юзера, если таблица пуста. Возвращает нового User либо None (уже есть)."""
    if session.exec(select(User)).first() is not None:
        return None
    user = User(
        email=settings.seed_user_email,
        password_hash=hash_password(settings.seed_user_password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def seed_sports(session: Session) -> int:
    """Сидит базовый каталог дисциплин, пропуская уже существующие по имени.

    Возвращает число добавленных строк (0 при повторном старте). Идемпотентно:
    уникальный Sport.name гарантирует, что повтор не плодит дубли. is_global=True —
    это встроенные дисциплины приложения, а не заведённые пользователем.
    """
    added = 0
    for name, category, description in BASE_SPORTS:
        if session.exec(select(Sport).where(Sport.name == name)).first() is not None:
            continue
        session.add(Sport(name=name, category=category, description=description, is_global=True))
        added += 1
    if added:
        session.commit()
    return added


def seed_sport_levels(session: Session) -> int:
    """Сидит лестницы уровней базовых дисциплин, пропуская уже заведённые ступени.

    Возвращает число добавленных ступеней (0 при повторном старте). Идемпотентно:
    ступень добавляется, только если для этой дисциплины ещё нет уровня с таким code
    (uq_sport_level_sport_code). rank берётся из позиции в лестнице (1 — низшая) и
    детерминирован, поэтому повтор не конфликтует по uq_sport_level_sport_rank.
    Дисциплину, которой нет в каталоге, пропускаем — сид уровней не создаёт спорты.
    """
    added = 0
    for sport_name, ladder in BASE_SPORT_LEVELS.items():
        sport = session.exec(select(Sport).where(Sport.name == sport_name)).first()
        if sport is None:
            continue
        existing = set(
            session.exec(select(SportLevel.code).where(SportLevel.sport_id == sport.id)).all()
        )
        for rank, (code, label) in enumerate(ladder, start=1):
            if code in existing:
                continue
            session.add(SportLevel(sport_id=sport.id, code=code, label=label, rank=rank))
            added += 1
    if added:
        session.commit()
    return added


def seed_base_challenge(session: Session) -> Challenge | None:
    """Сидит базовый челлендж WIPEOUTS (is_base=True) для категории action, идемпотентно.

    Единственность держится в сервисе — у challenge нет уникального индекса, поэтому
    повтор пропускаем, если базовый челлендж с этим заголовком уже есть. Требует сид-юзера
    (creator_user_id) и хотя бы одну глобальную action-дисциплину (sport_id); если чего-то
    нет — возвращаем None и ничего не пишем. Возвращает новый Challenge либо None.
    """
    existing = session.exec(
        select(Challenge).where(
            Challenge.title == BASE_CHALLENGE_TITLE, Challenge.is_base.is_(True)
        )
    ).first()
    if existing is not None:
        return None
    creator = session.exec(select(User).order_by(User.id)).first()
    sport = session.exec(
        select(Sport)
        .where(Sport.is_global.is_(True), Sport.category == SportCategory.action)
        .order_by(Sport.id)
    ).first()
    if creator is None or sport is None:
        return None
    challenge = Challenge(
        sport_id=sport.id,
        creator_user_id=creator.id,
        title=BASE_CHALLENGE_TITLE,
        description=BASE_CHALLENGE_DESCRIPTION,
        is_base=True,
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    return challenge


def seed_sport_content(session: Session) -> int:
    """Сидит богатый контент дисциплин из SPORT_CONTENT: long_description, упражнения, событие,
    наставник, рекомендация и встроенный челлендж — чтобы у каждого вида был полный набор.

    Возвращает число добавленных строк (0 при повторном старте). Идемпотентно: long_description
    и короткое description пишем только если пусты (бэкфилл старых видов без описаний);
    упражнения/события/наставники/рекомендации — по уникальности
    имени/заголовка в пределах вида; челлендж — по (sport_id, title). Челлендж требует сид-юзера
    как автора; если пользователя ещё нет — челлендж пропускаем (остальное сидим). Дисциплину,
    которой нет в каталоге, пропускаем — этот сид не создаёт спорты.
    """
    creator = session.exec(select(User).order_by(User.id)).first()
    today = dt.date.today()
    added = 0
    for name, content in SPORT_CONTENT.items():
        sport = session.exec(select(Sport).where(Sport.name == name)).first()
        if sport is None:
            continue

        long_desc = content["long"]
        short_desc = BASE_SPORT_DESC.get(name)
        touched = False
        if not sport.long_description and isinstance(long_desc, str):
            sport.long_description = long_desc
            touched = True
        if not sport.description and short_desc:
            sport.description = short_desc
            touched = True
        if touched:
            session.add(sport)
            added += 1

        for ex_name, kind, unit in content["exercises"]:
            exists = session.exec(
                select(Exercise).where(Exercise.sport_id == sport.id, Exercise.name == ex_name)
            ).first()
            if exists is None:
                session.add(Exercise(sport_id=sport.id, name=ex_name, kind=kind, unit=unit))
                added += 1

        ev_title, offset_days, location = content["event"]
        if (
            session.exec(
                select(SportEvent).where(
                    SportEvent.sport_id == sport.id, SportEvent.title == ev_title
                )
            ).first()
            is None
        ):
            session.add(
                SportEvent(
                    sport_id=sport.id,
                    title=ev_title,
                    starts_on=today + dt.timedelta(days=offset_days),
                    location=location,
                )
            )
            added += 1

        m_name, m_bio = content["mentor"]
        if (
            session.exec(
                select(SportMentor).where(
                    SportMentor.sport_id == sport.id, SportMentor.name == m_name
                )
            ).first()
            is None
        ):
            session.add(SportMentor(sport_id=sport.id, name=m_name, bio=m_bio))
            added += 1

        rec_title, rec_body = content["rec"]
        if (
            session.exec(
                select(SportRecommendation).where(
                    SportRecommendation.sport_id == sport.id,
                    SportRecommendation.title == rec_title,
                )
            ).first()
            is None
        ):
            session.add(SportRecommendation(sport_id=sport.id, title=rec_title, body=rec_body))
            added += 1

        ch_title, ch_desc = content["challenge"]
        if creator is not None and (
            session.exec(
                select(Challenge).where(Challenge.sport_id == sport.id, Challenge.title == ch_title)
            ).first()
            is None
        ):
            session.add(
                Challenge(
                    sport_id=sport.id,
                    creator_user_id=creator.id,
                    title=ch_title,
                    description=ch_desc,
                )
            )
            added += 1

    if added:
        session.commit()
    return added


def seed_extra_exercises(session: Session) -> int:
    """Добавляет базу упражнений дисциплинам вне основного каталога (EXTRA_SPORT_EXERCISES).

    Идемпотентно: упражнение добавляется, только если у вида ещё нет упражнения с таким
    именем. Вид, которого нет в каталоге, пропускаем (сид упражнений не создаёт спорты).
    Возвращает число добавленных строк (0 при повторном старте).
    """
    added = 0
    for sport_name, exercises in EXTRA_SPORT_EXERCISES.items():
        sport = session.exec(select(Sport).where(Sport.name == sport_name)).first()
        if sport is None:
            continue
        for ex_name, kind, unit in exercises:
            exists = session.exec(
                select(Exercise).where(Exercise.sport_id == sport.id, Exercise.name == ex_name)
            ).first()
            if exists is None:
                session.add(Exercise(sport_id=sport.id, name=ex_name, kind=kind, unit=unit))
                added += 1
    if added:
        session.commit()
    return added


def seed_sport_skills(session: Session) -> int:
    """Сеет каталог навыков (SPORT_SKILLS) КАЖДОМУ пользователю как Achievement(locked) — план
    развития. Ачивки владельческие (per-user), а каталог нужен всем, поэтому проходим по всем
    юзерам (их в личном трекере единицы). Идемпотентно: навык добавляется, только если у юзера
    ещё нет ачивки с таким title по этому виду. Возвращает число добавленных строк (0 при повторе).
    """
    users = session.exec(select(User)).all()
    if not users:
        return 0
    sport_ids = {
        name: sport.id
        for name in SPORT_SKILLS
        if (sport := session.exec(select(Sport).where(Sport.name == name)).first()) is not None
    }
    added = 0
    for user in users:
        for sport_name, skills in SPORT_SKILLS.items():
            sport_id = sport_ids.get(sport_name)
            if sport_id is None:
                continue
            existing = set(
                session.exec(
                    select(Achievement.title).where(
                        Achievement.user_id == user.id, Achievement.sport_id == sport_id
                    )
                ).all()
            )
            for title, tier in skills:
                if title in existing:
                    continue
                session.add(
                    Achievement(
                        user_id=user.id, sport_id=sport_id, title=title, level=tier, status="locked"
                    )
                )
                added += 1
    if added:
        session.commit()
    return added


def seed_initial_user() -> None:
    """Точка вызова на старте: открывает сессию и сидит пользователя при необходимости."""
    with Session(engine) as session:
        seed_user(session)


def seed_initial_sports() -> None:
    """Точка вызова на старте: открывает сессию и сидит базовый каталог дисциплин."""
    with Session(engine) as session:
        seed_sports(session)


def seed_initial_sport_levels() -> None:
    """Точка вызова на старте: открывает сессию и сидит лестницы уровней дисциплин."""
    with Session(engine) as session:
        seed_sport_levels(session)


def seed_initial_base_challenge() -> None:
    """Точка вызова на старте: открывает сессию и сидит базовый челлендж WIPEOUTS."""
    with Session(engine) as session:
        seed_base_challenge(session)


def seed_initial_sport_content() -> None:
    """Точка вызова на старте: сидит богатый контент дисциплин (описания/упражнения/события/…)."""
    with Session(engine) as session:
        seed_sport_content(session)


def seed_initial_extra_exercises() -> None:
    """Точка вызова на старте: добавляет базу упражнений дисциплинам вне основного каталога."""
    with Session(engine) as session:
        seed_extra_exercises(session)


def seed_initial_sport_skills() -> None:
    """Точка вызова на старте: сеет каталог навыков (план развития) сид-юзеру."""
    with Session(engine) as session:
        seed_sport_skills(session)
