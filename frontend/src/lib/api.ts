/** Типизированный HTTP-клиент к бэкенду ABS.
 *  Все запросы шлют cookie сессии (`credentials: 'include'`) — без неё защищённые
 *  роуты вернут 401. Ошибки не-2xx превращаются в ApiError со статусом. */

// ponytail: локальный бэкенд захардкожен — проект локальный (один пользователь).
// Вынести в env, если когда-нибудь появится не-локальный деплой.
export const API_BASE = 'http://localhost:8000';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** POST multipart-формы. Не ставим Content-Type — браузер сам выставит boundary;
 *  ручной заголовок сломал бы парсинг формы на бэке. */
async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  return (await res.json()) as T;
}

/** Загрузка одного файла (поле `file`). */
function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  return postForm<T>(path, form);
}

/** Пользователь (M0·B2): + опц. отображаемое имя и флаг активности. */
export type User = {
  id: number;
  email: string;
  display_name: string | null;
  is_active: boolean;
};

/** Категория дисциплины (S3.1, таксономия M1·B14): сменила тройку strength/cardio/skill. */
export type SportCategory =
  | 'strength'
  | 'endurance'
  | 'combat'
  | 'team'
  | 'racket'
  | 'action'
  | 'precision'
  | 'artistic'
  | 'other';

/** Категории дисциплины с русскими ярлыками (S3.3) — единый источник для форм и бейджей.
 *  value уходит на бэкенд (== SportCategory), label рисуется в UI.
 *  `satisfies` валидирует value/label, `as const` даёт литералы для гарда полноты ниже. */
export const SPORT_CATEGORIES = [
  { value: 'strength', label: 'Силовая' },
  { value: 'endurance', label: 'Выносливость' },
  { value: 'combat', label: 'Единоборства' },
  { value: 'team', label: 'Командный' },
  { value: 'racket', label: 'Ракеточный' },
  { value: 'action', label: 'Экстрим' },
  { value: 'precision', label: 'Точность' },
  { value: 'artistic', label: 'Артистическая' },
  { value: 'other', label: 'Другое' },
] as const satisfies readonly { value: SportCategory; label: string }[];

/** Полнота каталога (M1·F3): tsc падает здесь, если в SportCategory появилось значение,
 *  которого нет в SPORT_CATEGORIES — иначе категория тихо пропала бы из фильтра и формы.
 *  Без привязки к переменной (иначе noUnusedLocals); проверяет, что «недостающих» нет. */
true satisfies [Exclude<SportCategory, (typeof SPORT_CATEGORIES)[number]['value']>] extends [never]
  ? true
  : false;

/** Русский ярлык категории дисциплины; неизвестное значение возвращаем как есть. */
export const sportCategoryLabel = (category: SportCategory): string =>
  SPORT_CATEGORIES.find((c) => c.value === category)?.label ?? category;

/** Вид спорта (S3.1): дисциплина с категорией. name уникален (повтор → 409).
 *  M5·B22 rich-поля: slug — ЧПУ-идентификатор (server-managed, авто из name),
 *  long_description — развёрнутое описание, is_global — встроенная дисциплина vs своя. */
export type Sport = {
  id: number;
  name: string;
  category: SportCategory;
  description: string | null;
  slug: string | null;
  long_description: string | null;
  is_global: boolean;
};

/** Поля формы создания вида спорта (S3.3). */
export type SportInput = {
  name: string;
  category: SportCategory;
  description: string | null;
};

/** Дисциплина пользователя (M2·B19): связка user_sport + данные каталога вида спорта.
 *  current_level_id/rating — личные атрибуты (уровень/рейтинг); таблицы уровней пока нет,
 *  поэтому current_level_id — просто int без FK. joined_at — когда привязал дисциплину. */
export type UserSport = {
  sport_id: number;
  name: string;
  category: SportCategory;
  description: string | null;
  current_level_id: number | null;
  rating: number | null;
  joined_at: string; // ISO datetime
};

/** Тело привязки дисциплины к себе: какой вид спорта (+ опц. уровень и рейтинг). */
export type UserSportLink = {
  sport_id: number;
  current_level_id?: number | null;
  rating?: number | null;
};

/** Упражнение библиотеки (S3.2): принадлежит виду спорта (sport_id). */
export type Exercise = {
  id: number;
  sport_id: number;
  name: string;
  kind: string | null;
  unit: string | null;
  notes: string | null;
};

/** Поля формы добавления упражнения (sport_id — из карточки вида спорта). */
export type ExerciseInput = {
  sport_id: number;
  name: string;
  unit: string | null;
  notes: string | null;
};

/** Силовой подход — ввод (S3.7). exercise_id обязателен, метрики опциональны.
 *  set_index проставляет фронт по порядку строк (1-based). */
export type StrengthSetInput = {
  exercise_id: number;
  set_index: number | null;
  weight_kg: number | null;
  reps: number | null;
  rest_sec: number | null;
  rpe: number | null;
};

/** Создание силовой сессии (S3.7): шапка + ≥1 подход, всё уходит одним POST. */
export type WorkoutInput = {
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  title: string | null;
  sets: StrengthSetInput[];
};

/** Силовой подход — ответ бэкенда (S3.4). */
export type StrengthSet = {
  id: number;
  exercise_id: number;
  set_index: number | null;
  weight_kg: number | null;
  reps: number | null;
  rest_sec: number | null;
  rpe: number | null;
};

/** Силовая сессия с подходами — ответ POST /workouts (S3.4/S3.7). */
export type Workout = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  title: string | null;
  notes: string | null;
  created_at: string;
  sets: StrengthSet[];
};

/** Кардио-сессия — ввод (S3.8). distance_km/duration_sec обязательны (>0); пульс опционален. */
export type CardioInput = {
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  title: string | null;
  distance_km: number;
  duration_sec: number;
  avg_hr: number | null;
  max_hr: number | null;
};

/** Кардио-сессия — ответ бэкенда (S3.5): метрики + рассчитанный темп (avg_pace). */
export type CardioLog = {
  id: number;
  session_id: number;
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  exercise_id: number | null;
  title: string | null;
  notes: string | null;
  created_at: string;
  distance_km: number | null;
  duration_sec: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_pace: string | null;
};

/** Элемент скилл-сессии — ввод (S3.8). attempts ≥ 1, landed 0..attempts. */
export type SkillEntryInput = {
  exercise_id: number;
  attempts: number;
  landed: number;
  notes: string | null;
};

/** Создание скилл-сессии (S3.8): шапка + ≥1 элемент, всё уходит одним POST. */
export type SkillInput = {
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  title: string | null;
  entries: SkillEntryInput[];
};

/** Элемент скилл-сессии — ответ бэкенда (S3.6). */
export type SkillEntry = {
  id: number;
  exercise_id: number;
  attempts: number | null;
  landed: number | null;
  notes: string | null;
};

/** Скилл-сессия с элементами — ответ POST /workouts/skill (S3.6). */
export type SkillSession = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  sport_id: number | null;
  title: string | null;
  notes: string | null;
  created_at: string;
  entries: SkillEntry[];
};

/** Тип тренировки в минимальном («быстром») логе (S3.11). */
export type WorkoutKind = 'cardio' | 'strength' | 'skill' | 'other';

export type SimpleWorkoutMedia = { id: number; media_type: 'image' | 'video' };

/** Минимальный лог тренировки — ответ POST /workouts/simple (S3.11). */
export type SimpleWorkout = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  kind: WorkoutKind;
  sport_id: number | null;
  duration_min: number | null;
  rpe: number | null;
  notes: string | null;
  surpassed_self: boolean; // «превзошёл себя» (M2·B16/B17): отмечен ли личный рекорд в сессии
  created_at: string;
  media: SimpleWorkoutMedia[];
};

/** Ввод минимального лога: тип, длительность, усилие, заметка и медиа (фото/видео).
 *  Длительность опциональна — для видео рекорда/трюка минуты не нужны.
 *  sportId — опц. привязка к виду спорта (M2·F6): фронт ставит его из выбранной категории. */
export type SimpleWorkoutInput = {
  date: string;
  kind: WorkoutKind;
  sportId: number | null;
  durationMin: number | null;
  rpe: number | null;
  note: string | null;
  surpassedSelf: boolean; // «превзошёл себя» (M2·F9): отметка личного рекорда сессии
  files: File[];
};

/** SMART-цель: ответ бэкенда (см. backend SmartGoal). Даты — ISO `YYYY-MM-DD`. */
export type Goal = {
  id: number;
  target_weight_kg: number | null;
  target_body_fat_pct: number | null;
  target_measurements_json: Record<string, number> | null;
  start_date: string | null;
  deadline: string | null;
  baseline_json: Record<string, unknown> | null;
  why_notes: string | null;
  status: string;
  created_at: string;
};

/** Поля формы цели — только то, что задаёт пользователь на экране настройки. */
export type GoalInput = {
  target_weight_kg: number | null;
  target_body_fat_pct: number | null;
  target_measurements_json: Record<string, number> | null;
  deadline: string | null;
  why_notes: string | null;
};

/** Замер тела (S2.2): обхваты в см, дата ISO `YYYY-MM-DD`. Все обхваты опциональны. */
export type BodyMeasurement = {
  id: number;
  date: string;
  height_cm: number | null;
  waist_cm: number | null;
  belly_cm: number | null;
  calf_l_cm: number | null;
  calf_r_cm: number | null;
  chest_cm: number | null;
  shoulders_cm: number | null;
  biceps_l_cm: number | null;
  biceps_r_cm: number | null;
  glutes_cm: number | null;
  notes: string | null;
};

/** Поля формы замеров (S2.3) — то, что задаёт пользователь (без id/notes). */
export type BodyMeasurementInput = Omit<BodyMeasurement, 'id' | 'notes'>;

/** Ввод веса (вкладка «Вес»): дата + вес (кг). Бэкенд апсёртит в inbody_measurement по дню. */
export type WeightInput = { date: string; weight_kg: number };

/** Фото прогресса тела (вкладка «Фото»): метаданные; сам файл — по bodyPhotoUrl(id). */
export type ProgressPhoto = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  notes: string | null;
  uploaded_at: string;
};

/** Точка временного ряда прогресса (S2.4): дата ISO + значение. */
export type SeriesPoint = { date: string; value: number };

/** Ряды тела за период (S2.4): вес (InBody) + обхваты (по полю → ряд). */
export type BodyProgress = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  weight_kg: SeriesPoint[];
  circumferences: Record<string, SeriesPoint[]>;
};

/** Ряды энергии/питания за период (S2.5): для графиков энергобаланса (S2.8).
 *  deficit = kcal_out − kcal_in (>0 — дефицит/расход больше прихода). macros —
 *  ряды protein_g/fat_g/carb_g. Точка есть только там, где значение не-null. */
export type EnergyProgress = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  kcal_in: SeriesPoint[];
  kcal_out: SeriesPoint[];
  deficit: SeriesPoint[];
  macros: Record<string, SeriesPoint[]>;
  steps: SeriesPoint[];
  active_min: SeriesPoint[];
};

/** Ряды состава тела InBody за период (S2.12): по одному ряду на показатель
 *  (%жира, мыш.масса, висцеральный жир, вода). Точка есть только там, где значение
 *  не-null — редкие замеры не дают ложных нулей. */
export type InbodyProgress = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  composition: Record<string, SeriesPoint[]>;
};

/** Тип личного рекорда (S3.10): дискриминатор рода рекорда упражнения. */
export type PrMetric = 'max_weight' | 'best_1rm' | 'best_pace' | 'max_distance';

/** Личный рекорд (S3.10): лучший результат по упражнению. Для темпа value — сек/км
 *  (меньше = лучше). date — день, когда рекорд установлен (для подсветки на графике). */
export type PersonalRecord = {
  id: number;
  exercise_id: number;
  metric: PrMetric;
  date: string; // ISO YYYY-MM-DD
  value: number;
  unit: string | null;
};

/** Ряды силовых по упражнению (S3.11): рабочий вес (макс/день), 1ПМ (Эпли),
 *  тоннаж (Σ вес·повт/день). Точка есть только где значение реально посчитано. */
export type ExerciseStrengthSeries = {
  exercise_id: number;
  working_weight: SeriesPoint[];
  best_1rm: SeriesPoint[];
  tonnage: SeriesPoint[];
};

/** Тоннаж по виду спорта (группе упражнений) за день (S3.11). */
export type GroupTonnageSeries = {
  sport_id: number | null;
  tonnage: SeriesPoint[];
};

/** Прогресс силовых за период (S3.11): ряды по упражнениям + тоннаж по группам. */
export type StrengthProgress = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  by_exercise: ExerciseStrengthSeries[];
  by_group: GroupTonnageSeries[];
};

/** Ряды кардио по упражнению (S3.11): дистанция (км), темп (сек/км), средний пульс,
 *  пульсовая эффективность (метров на удар). Точка есть только где метрика считается. */
export type ExerciseCardioSeries = {
  exercise_id: number | null;
  distance: SeriesPoint[];
  pace: SeriesPoint[];
  avg_hr: SeriesPoint[];
  efficiency: SeriesPoint[];
};

/** Прогресс кардио за период (S3.11): ряды по упражнениям. */
export type CardioProgress = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  by_exercise: ExerciseCardioSeries[];
};

/** Импорт дневника питания (S1.8): превью разобранного дня и результат сохранения. */
export type ImportTotals = {
  kcal: number;
  fat_g: number;
  carb_g: number;
  protein_g: number;
};

export type ImportProduct = {
  product_name: string;
  portion_raw: string | null;
  kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
};

export type ImportMeal = {
  meal: string;
  products: ImportProduct[];
  totals: ImportTotals;
};

export type DiaryPreview = {
  date: string; // ISO YYYY-MM-DD
  meals: ImportMeal[];
  totals: ImportTotals;
  product_count: number;
  saved: boolean;
  import_id: string | null;
};

/** Импорт скрина активности Welltory (S1.11): распознанные метрики дня.
 *  Все поля — целые или null (плитки не было / не распозналось). */
export type ActivityFields = {
  total_kcal: number | null;
  active_kcal: number | null;
  steps: number | null;
  moving_min: number | null;
  idle_min: number | null;
  warmup_min: number | null;
  active_met: number | null;
  intense_met: number | null;
};

/** Результат шага сверки: распознанные поля + дата + сырой разбор модели. */
export type ActivityPreview = ActivityFields & {
  date: string; // ISO YYYY-MM-DD
  raw_json: Record<string, unknown>;
  saved: boolean;
};

/** Сохранённый день активности (ответ /import/activity). */
export type ActivityDay = ActivityFields & {
  date: string; // ISO YYYY-MM-DD
  raw_json: Record<string, unknown> | null;
  source_image_path: string | null;
  parsed_at: string;
};

/** Ингест скрина InBody (S2.11): пять ключевых показателей. Все — float или null
 *  (поля нет на скрине / не распозналось). */
export type InbodyFields = {
  weight_kg: number | null;
  body_fat_pct: number | null;
  muscle_mass_kg: number | null;
  visceral_fat: number | null;
  water: number | null;
};

/** Результат шага сверки: ключевые поля + дата + прочие показатели (metrics_json). */
export type InbodyPreview = InbodyFields & {
  date: string; // ISO YYYY-MM-DD
  metrics_json: Record<string, unknown>;
  saved: boolean;
};

/** Сохранённый замер InBody (ответ /import/inbody). */
export type InbodyMeasurement = InbodyFields & {
  id: number;
  date: string; // ISO YYYY-MM-DD
  metrics_json: Record<string, unknown> | null;
  source_image_path: string | null;
  parsed_at: string;
};

/** Дашборд (S1.13): по каждому дню диапазона — флаги наличия данных.
 *  Ежедневные (дневной «стакан»): food/activity/training.
 *  Недельные (наливаются в «общую чашу» недели): weight/body/photo.
 *  has_measurement (body|inbody) — легаси-флаг для «Заряда дня».
 *  Новые сигналы (M4·B20), по дню и со скоупом по пользователю:
 *  surpassed_self (личный рекорд), workout_media (медиа тренировки),
 *  full_measurements (обхваты И вес за один день). */
export type DayFlags = {
  date: string; // ISO YYYY-MM-DD
  has_food: boolean;
  has_activity: boolean;
  has_training: boolean;
  has_measurement: boolean;
  has_weight: boolean;
  has_body: boolean;
  has_photo: boolean;
  has_surpassed_self: boolean;
  has_workout_media: boolean;
  has_full_measurements: boolean;
};

/** Контракт M4·F14: `DayFlags` обязан нести три новых сигнала-флага (boolean,
 *  семантический дефолт — false; рантайм-значения приходят с бэкенда /dashboard).
 *  Это compile-time-замок: `tsc` падает здесь, если поле убрали, переименовали
 *  или сменили его тип — дешёвый регресс-гард без рантайм-веса и без зависимостей. */
export const DAYFLAGS_NEW_SIGNALS: Pick<
  DayFlags,
  'has_surpassed_self' | 'has_workout_media' | 'has_full_measurements'
> = {
  has_surpassed_self: false,
  has_workout_media: false,
  has_full_measurements: false,
};

/** Сводка энергобаланса за сегодня (S1.15). deficit = kcal_out − kcal_in. */
export type TodaySummary = {
  date: string; // ISO YYYY-MM-DD
  kcal_in: number;
  kcal_out: number;
  deficit: number;
};

export type DashboardData = {
  start: string; // ISO YYYY-MM-DD
  end: string; // ISO YYYY-MM-DD
  days: DayFlags[];
  current_streak: number;
  today: TodaySummary;
};

/** Макронутриенты в граммах (S4.3). */
export type Macros = { protein_g: number; carbs_g: number; fat_g: number };

/** Один приём пищи (S4.3): название + калории + макросы. */
export type Meal = { name: string; calories: number; macros: Macros };

/** Рацион одного типа дня (S4.3): тренировочный день или день отдыха. */
export type DayNutrition = {
  day_type: 'training' | 'rest';
  calories: number;
  macros: Macros;
  meals: Meal[];
};

/** План питания (S4.3): раздельно тренировочный день и день отдыха. */
export type MealPlan = {
  training_day: DayNutrition;
  rest_day: DayNutrition;
  notes: string | null;
};

/** Назначение упражнения (S4.3). working_weight_kg = null → свой вес/кардио. */
export type ExercisePrescription = {
  name: string;
  sets: number;
  reps: number;
  working_weight_kg: number | null;
};

/** Одна тренировка недели (S4.3): номер, фокус и упражнения. */
export type WorkoutDay = { day: number; focus: string; exercises: ExercisePrescription[] };

/** Шаг недельной прогрессии (S4.3). */
export type WeekProgression = { week: number; adjustment: string };

/** План тренировок (S4.3): расписание недели + недельная прогрессия. */
export type WorkoutPlan = {
  days_per_week: number;
  schedule: WorkoutDay[];
  weekly_progression: WeekProgression[];
};

/** Структурированный план рекомендации (S4.3): еда + тренировки + их связка. */
export type RecommendationPlan = {
  meal_plan: MealPlan;
  workout_plan: WorkoutPlan;
  sync_note: string;
};

/** Прогресс по одной метрике цели в снапшоте (S4.1): baseline→current→target. */
export type GoalProgress = {
  metric: string;
  target: number;
  baseline: number | null;
  current: number | null;
  remaining: number | null;
  percent: number | null;
};

/** Цель из снапшота рекомендации (input_snapshot_json.goal, S4.1): та цель, что была
 *  активна на момент генерации. null — активной цели не было. */
export type GoalSnapshot = {
  id: number | null;
  target_weight_kg: number | null;
  target_body_fat_pct: number | null;
  target_measurements: Record<string, number>;
  start_date: string | null;
  deadline: string | null;
  why_notes: string | null;
  progress: GoalProgress[];
};

/** Снапшот входа, поданного модели (S4.1). Поля гибкие; в UI читаем секцию goal. */
export type RecommendationSnapshot = {
  goal?: GoalSnapshot | null;
  [key: string]: unknown;
};

/** Сохранённая рекомендация (S4.4/S4.5): запись истории с распарсенным планом.
 *  output_json = null только у битой записи; обычно несёт RecommendationPlan. raw_text —
 *  сырой ответ модели для отладки. */
export type Recommendation = {
  id: number;
  created_at: string; // ISO datetime
  model: string;
  input_snapshot_json: RecommendationSnapshot | null;
  output_json: RecommendationPlan | null;
  raw_text: string | null;
  goal_id: number | null;
  generation_ms: number | null; // S4.9: длительность генерации, мс (null у записей до S4.9)
};

/** Тир сложности ачивки (S5.1): хранится в поле `level`, по возрастанию сложности. */
export type AchievementTier = 'foundation' | 'intermediate' | 'advanced' | 'elite';

/** Статус ачивки (S1.2): закрыта / в процессе / открыта. */
export type AchievementStatus = 'locked' | 'in_progress' | 'unlocked';

/** Ачивка вида спорта (S5.1/S5.2): достижение-вызов. `level` — тир сложности
 *  (AchievementTier), но хранится строкой, поэтому тип широкий. `has_proof` (S5.6) —
 *  есть ли видео-пруф: по нему карточка решает, рисовать ли превью. Опционально, т.к.
 *  ответы /proofs и /unlock возвращают ачивку без этого поля. */
export type Achievement = {
  id: number;
  sport_id: number | null;
  title: string;
  description: string | null;
  level: string | null;
  status: AchievementStatus;
  created_at: string;
  unlocked_at: string | null;
  has_proof?: boolean;
};

/** Видео-пруф ачивки (S5.4): пути к видео/превью на диске + метаданные. */
export type AchievementProof = {
  id: number;
  achievement_id: number;
  video_path: string | null;
  thumbnail_path: string | null;
  uploaded_at: string;
  notes: string | null;
};

/** URL превью последнего видео-пруфа ачивки (S5.6): картинка для карточки.
 *  Cache-bust (`v`) — чтобы после новой загрузки бралась свежая картинка, а не из кеша. */
export const achievementThumbnailUrl = (achievementId: number, v?: string | number): string =>
  `${API_BASE}/achievements/${achievementId}/proof/thumbnail${v != null ? `?v=${v}` : ''}`;

/** URL файла фото прогресса для <img>. Грузится с сессионной cookie (same-site localhost).
 *  Cache-bust (`v`) — чтобы после новой загрузки бралась свежая картинка, а не из кеша. */
export const bodyPhotoUrl = (photoId: number, v?: string | number): string =>
  `${API_BASE}/body-photos/${photoId}${v != null ? `?v=${v}` : ''}`;

/** URL файла медиа тренировки (S3.11) — для <img>/<video src>. */
export const workoutMediaUrl = (mediaId: number): string => `${API_BASE}/workouts/media/${mediaId}`;

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  // Регистрация (M0·B1): создаёт юзера и выставляет ту же сессию, что login → возвращает User.
  // 409, если email уже занят (ApiError.status === 409).
  register: (email: string, password: string) =>
    request<User>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),

  // Виды спорта (S3.1): каталог дисциплин (бэкенд сортирует по имени).
  // category — фильтр по таксономии (M1·B15): без него все, иначе только эта категория.
  listSports: (category?: SportCategory) =>
    request<Sport[]>(category == null ? '/sports' : `/sports?category=${category}`),
  // Канонический список категорий дисциплин (M1·B15) — источник опций для фильтра каталога.
  listSportCategories: () => request<SportCategory[]>('/sports/categories'),
  createSport: (input: SportInput) =>
    request<Sport>('/sports', { method: 'POST', body: JSON.stringify(input) }),

  // Ачивки вида спорта (S5.2): набор достижений со статусами (locked/in_progress/unlocked).
  listAchievements: (sportId: number) => request<Achievement[]>(`/sports/${sportId}/achievements`),

  // Мои дисциплины (M2·B19): личные привязки видов спорта, скоуп по сессии.
  // link → 404 (нет sport) / 409 (уже привязана); unlink → 404 (связки нет), иначе 204.
  listMySports: () => request<UserSport[]>('/me/sports'),
  linkSport: (input: UserSportLink) =>
    request<UserSport>('/me/sports', { method: 'POST', body: JSON.stringify(input) }),
  unlinkSport: (sportId: number) => request<void>(`/me/sports/${sportId}`, { method: 'DELETE' }),

  // Видео-пруф ачивки (S5.4): загрузка видео (multipart) → запись пруфа + превью.
  uploadAchievementProof: (achievementId: number, file: File) =>
    upload<AchievementProof>(`/achievements/${achievementId}/proofs`, file),
  // Закрытие ачивки (S5.5): сервер требует наличия пруфа, иначе 409 → status=unlocked.
  unlockAchievement: (achievementId: number) =>
    request<Achievement>(`/achievements/${achievementId}/unlock`, { method: 'POST' }),

  // Упражнения библиотеки (S3.2): без sport_id — все; иначе фильтр по виду спорта.
  listExercises: (sportId?: number) =>
    request<Exercise[]>(sportId == null ? '/exercises' : `/exercises?sport_id=${sportId}`),
  createExercise: (input: ExerciseInput) =>
    request<Exercise>('/exercises', { method: 'POST', body: JSON.stringify(input) }),

  // Силовая сессия (S3.7): шапка + все подходы одним POST → сессия с подходами.
  createWorkout: (input: WorkoutInput) =>
    request<Workout>('/workouts', { method: 'POST', body: JSON.stringify(input) }),

  // Кардио-сессия (S3.8): дистанция/время/пульс одним POST; бэкенд считает темп.
  createCardio: (input: CardioInput) =>
    request<CardioLog>('/workouts/cardio', { method: 'POST', body: JSON.stringify(input) }),

  // Скилл-сессия (S3.8): шапка + элементы (попытки/приземления) одним POST.
  createSkill: (input: SkillInput) =>
    request<SkillSession>('/workouts/skill', { method: 'POST', body: JSON.stringify(input) }),

  // Минимальный («быстрый») лог тренировки (S3.11): multipart — поля + опц. медиа (фото/видео).
  createSimpleWorkout: (input: SimpleWorkoutInput) => {
    const form = new FormData();
    form.append('date', input.date);
    form.append('kind', input.kind);
    if (input.sportId != null) form.append('sport_id', String(input.sportId));
    if (input.durationMin != null) form.append('duration_min', String(input.durationMin));
    if (input.rpe != null) form.append('rpe', String(input.rpe));
    if (input.note) form.append('note', input.note);
    if (input.surpassedSelf) form.append('surpassed_self', 'true');
    for (const file of input.files) form.append('files', file);
    return postForm<SimpleWorkout>('/workouts/simple', form);
  },

  // Медиа дня (M2·B18): id+type всех медиа тренировок владельца за день; байты — workoutMediaUrl(id).
  listDayWorkoutMedia: (date: string) =>
    request<SimpleWorkoutMedia[]>(`/workouts/media?date=${date}`),

  // Дашборд-хитмап: флаги данных по дням месяца (start/end — ISO YYYY-MM-DD).
  getDashboard: (start: string, end: string) =>
    request<DashboardData>(`/dashboard?start=${start}&end=${end}`),

  // Список (200 + []), а не /goals/active (404 при отсутствии) — чтобы пустое
  // состояние не порождало console.error/4xx; активную цель выбираем на клиенте.
  listGoals: () => request<Goal[]>('/goals'),
  createGoal: (input: GoalInput) =>
    request<Goal>('/goals', { method: 'POST', body: JSON.stringify(input) }),
  updateGoal: (id: number, input: GoalInput) =>
    request<Goal>(`/goals/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),

  // Прогресс тела (S2.4): ряды веса/обхватов за период [start; end] (ISO) для графиков.
  getBodyProgress: (start: string, end: string) =>
    request<BodyProgress>(`/progress/body?start=${start}&end=${end}`),

  // Прогресс энергии (S2.5): ряды ккал/дефицита/макросов/активности за период (S2.8).
  getEnergyProgress: (start: string, end: string) =>
    request<EnergyProgress>(`/progress/energy?start=${start}&end=${end}`),

  // Прогресс состава тела InBody (S2.12): ряды %жира/мышц/висцерального жира/воды.
  getInbodyProgress: (start: string, end: string) =>
    request<InbodyProgress>(`/progress/inbody?start=${start}&end=${end}`),

  // Прогресс силовых (S3.11): ряды веса/1ПМ/тоннажа за период для графиков (S3.12).
  getStrengthProgress: (start: string, end: string) =>
    request<StrengthProgress>(`/progress/strength?start=${start}&end=${end}`),

  // Прогресс кардио (S3.11): ряды дистанции/темпа/пульса/эффективности за период.
  getCardioProgress: (start: string, end: string) =>
    request<CardioProgress>(`/progress/cardio?start=${start}&end=${end}`),

  // Личные рекорды (S3.10): все PR упражнений — для подсветки точек на графиках (S3.12).
  listPersonalRecords: () => request<PersonalRecord[]>('/workouts/prs'),

  // Замеры тела (S2.3): создать запись обхватов (см) на дату. Бэкенд — POST /body-measurements.
  createMeasurement: (input: BodyMeasurementInput) =>
    request<BodyMeasurement>('/body-measurements', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  // Вес (вкладка «Вес»): ручной ввод числа без фото; бэкенд апсёртит по дню в inbody_measurement.
  createWeight: (input: WeightInput) =>
    request<InbodyMeasurement>('/body/weight', { method: 'POST', body: JSON.stringify(input) }),

  // Фото прогресса (вкладка «Фото»): загрузка (multipart) + список для галереи (новые сверху).
  uploadBodyPhoto: (file: File, date?: string, notes?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (date) form.append('date', date);
    if (notes) form.append('notes', notes);
    return postForm<ProgressPhoto>('/body-photos', form);
  },
  listBodyPhotos: (start?: string, end?: string) => {
    const qs = new URLSearchParams();
    if (start) qs.set('start', start);
    if (end) qs.set('end', end);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return request<ProgressPhoto[]>(`/body-photos${suffix}`);
  },

  // Импорт еды: превью разбирает CSV без записи; save пишет идемпотентно по дню.
  // date — записать дневник на выбранный день (из попапа календаря), а не из файла.
  previewImport: (file: File) => upload<DiaryPreview>('/import/food/preview', file),
  saveImport: (file: File, date?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (date) form.append('date', date);
    return postForm<DiaryPreview>('/import/food', form);
  },

  // Импорт активности Welltory: превью распознаёт скрин без записи; save пишет
  // выверенные пользователем поля (vision не дёргается) идемпотентно по дню.
  previewActivity: (file: File, date: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('date', date);
    return postForm<ActivityPreview>('/import/activity/preview', form);
  },
  saveActivity: (file: File, date: string, fields: ActivityFields, rawJson: unknown) => {
    const form = new FormData();
    form.append('file', file);
    form.append('date', date);
    form.append('fields', JSON.stringify(fields));
    form.append('raw_json', JSON.stringify(rawJson ?? {}));
    return postForm<ActivityDay>('/import/activity', form);
  },
  // Ручной ввод активности (без скрина): дата + 8 метрик, upsert по дню.
  saveActivityManual: (date: string, fields: ActivityFields) =>
    request<ActivityDay>('/import/activity/manual', {
      method: 'POST',
      body: JSON.stringify({ date, ...fields }),
    }),

  // Рекомендации (S4.5): генерация по кнопке (снапшот → Opus → план), история списком,
  // деталь по id. Генерация может вернуть 502, если апстрим LLM недоступен.
  generateRecommendation: () =>
    request<Recommendation>('/recommendations/generate', { method: 'POST' }),
  listRecommendations: () => request<Recommendation[]>('/recommendations'),
  getRecommendation: (id: number) => request<Recommendation>(`/recommendations/${id}`),

  // Ингест скрина InBody (S2.11): превью распознаёт скрин без записи; save пишет
  // выверенные пользователем поля (vision не дёргается) идемпотентно по дню.
  previewInbody: (file: File, date: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('date', date);
    return postForm<InbodyPreview>('/import/inbody/preview', form);
  },
  saveInbody: (file: File, date: string, fields: InbodyFields, metricsJson: unknown) => {
    const form = new FormData();
    form.append('file', file);
    form.append('date', date);
    form.append('fields', JSON.stringify(fields));
    form.append('metrics_json', JSON.stringify(metricsJson ?? {}));
    return postForm<InbodyMeasurement>('/import/inbody', form);
  },
};
