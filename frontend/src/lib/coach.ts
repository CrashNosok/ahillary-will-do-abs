/** Логика персонажа-коуча (S5.9 + S5.10): состояние дня → реплика.
 *
 *  Коуч живёт на дашборде и комментирует ТЕКУЩЕЕ состояние дня, опираясь на те же
 *  данные GET /dashboard, что и панель «Сегодня»: флаги логирования, активную серию
 *  и энергобаланс. Никакого нового бэкенда — состояние выводится на фронте из уже
 *  загруженных цифр (бэкенд-сервис фраз S5.7/S5.8 не имеет HTTP-эндпоинта).
 *
 *  Тексты реплик (S5.10) правятся из интерфейса: дефолты лежат здесь, а правки
 *  пользователя хранятся в localStorage и накладываются поверх дефолтов. Источник
 *  для дашборда — именно эффективный набор (loadPhrases), поэтому правка СРАЗУ
 *  применяется: и Coach, и редактор читают один и тот же набор. localStorage — это
 *  естественное рантайм-хранилище для однопользовательского локального приложения.
 *
 *  Выбор фразы детерминирован по «семени дня»: в течение суток реплика стабильна
 *  (нет мерцания на ре-рендерах), но меняется день ото дня. Функции чистые —
 *  тривиально проверяются типами и живым прогоном. */

import type { DashboardData } from './api';

export type CoachMood = 'missed' | 'streak' | 'success' | 'progress';

/** Набор фраз по всем состояниям коуча. */
export type PhraseMap = Record<CoachMood, string[]>;

// Порядок категорий в редакторе и человекочитаемые ярлыки (источник правды для UI).
export const MOODS: readonly CoachMood[] = ['missed', 'streak', 'success', 'progress'];

export const MOOD_LABELS: Record<CoachMood, string> = {
  missed: 'Пропуск дня',
  streak: 'Серия',
  success: 'Успех',
  progress: 'В процессе',
};

// Когда коуч показывает эту категорию — подсказка для редактора.
export const MOOD_HINTS: Record<CoachMood, string> = {
  missed: 'когда за день нет ни одной записи',
  streak: 'когда серия идёт 3 дня подряд и дольше',
  success: 'когда за день достигнут дефицит калорий',
  progress: 'обычный день в процессе — фолбэк по умолчанию',
};

// Серия, которую уже стоит праздновать. ponytail: порог-константа, не конфиг —
// одно значение, менять которое можно правкой здесь, а не настройками.
const STREAK_MILESTONE = 3;

// Ключ localStorage для пользовательских правок фраз (S5.10).
const STORAGE_KEY = 'abs.coach.phrases';

// Дефолтные реплики по состояниям. Тон — дерзкий, но без токсичности и стыда за тело
// (тот же контракт, что у coach_phrases.json на бэкенде). Число серии не дублируем:
// его показывает бейдж стрика в панели «Сегодня».
const DEFAULT_PHRASES: PhraseMap = {
  missed: [
    'Пусто. Лог сам себя не заполнит — погнали.',
    'Ноль записей за день. Исправим за минуту?',
    'День — чистый лист. Первая запись за тобой.',
  ],
  streak: [
    'Серия живёт. Не ты её ведёшь — она тебя.',
    'Стрик горит. Подкинь дровишек.',
    'Дни подряд — это уже характер, а не везение.',
  ],
  success: [
    'Дефицит в кармане. Чисто сработано.',
    'Сегодня ты в плюсе — там, где надо в минус.',
    'Баланс сошёлся. Так держать.',
  ],
  progress: [
    'Старт есть. Доведём день до конца.',
    'Неплохо. До идеального дня — пара записей.',
    'Движемся. Темп важнее рывка.',
  ],
};

/** Свежая копия дефолтов — чтобы вызывающий код мог свободно мутировать свой набор. */
function defaultsCopy(): PhraseMap {
  return {
    missed: [...DEFAULT_PHRASES.missed],
    streak: [...DEFAULT_PHRASES.streak],
    success: [...DEFAULT_PHRASES.success],
    progress: [...DEFAULT_PHRASES.progress],
  };
}

/** Эффективный набор фраз: правки из localStorage поверх дефолтов.
 *
 *  localStorage — недоверенный источник, поэтому валидируем на границе: битый JSON,
 *  не-массивы и пустые/нестроковые элементы игнорируются с откатом на дефолт по
 *  соответствующей категории. Инвариант результата: каждая категория непуста. */
export function loadPhrases(): PhraseMap {
  const result = defaultsCopy();

  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return result; // localStorage недоступен (приватный режим и т.п.)
  }
  if (!raw) return result;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return result; // битый JSON → дефолты
  }
  if (!parsed || typeof parsed !== 'object') return result;

  const stored = parsed as Record<string, unknown>;
  for (const mood of MOODS) {
    const arr = stored[mood];
    if (!Array.isArray(arr)) continue;
    const clean = arr.filter((p): p is string => typeof p === 'string' && p.trim() !== '');
    if (clean.length > 0) result[mood] = clean;
  }
  return result;
}

/** Сохранить правки в localStorage и вернуть санированный набор.
 *
 *  Пустые строки выбрасываются (trim); если категория осталась бы пустой — откат на
 *  её дефолт (коуч не должен остаться без реплик). Возвращаем результат, чтобы UI
 *  синхронизировал черновик с тем, что реально сохранилось. */
export function savePhrases(phrases: PhraseMap): PhraseMap {
  const out = {} as PhraseMap;
  for (const mood of MOODS) {
    const list = (phrases[mood] ?? []).map((p) => p.trim()).filter((p) => p !== '');
    out[mood] = list.length > 0 ? list : [...DEFAULT_PHRASES[mood]];
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(out));
  } catch {
    /* запись недоступна — UI просто не увидит изменений, данные не теряются */
  }
  return out;
}

/** Состояние дня для коуча из данных дашборда.
 *
 *  Приоритет: пустой день важнее всего (надо начать), затем веха серии (редкий
 *  повод порадоваться), затем достигнутый дефицит, иначе — «день в процессе». */
export function deriveMood(data: DashboardData): CoachMood {
  const flags = data.days[0];
  const logged = flags
    ? flags.has_food || flags.has_activity || flags.has_training || flags.has_measurement
    : false;
  const anyKcal = data.today.kcal_in > 0 || data.today.kcal_out > 0;

  if (!logged && !anyKcal) return 'missed';
  if (data.current_streak >= STREAK_MILESTONE) return 'streak';
  if (data.today.deficit > 0) return 'success';
  return 'progress';
}

/** Семя дня: целое, стабильное в течение суток и разное день ото дня. */
export function daySeed(now: Date = new Date()): number {
  return Math.floor(now.getTime() / 86_400_000);
}

/** Детерминированная реплика для состояния: стабильна в пределах одного семени.
 *
 *  По умолчанию берёт эффективный набор (дефолты + правки пользователя), так что
 *  правка из редактора применяется к дашборду без отдельной проводки. */
export function pickPhrase(
  mood: CoachMood,
  seed: number,
  phrases: PhraseMap = loadPhrases(),
): string {
  const list = phrases[mood];
  return list[((seed % list.length) + list.length) % list.length];
}
