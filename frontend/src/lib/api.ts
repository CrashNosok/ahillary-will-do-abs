/** Типизированный HTTP-клиент к бэкенду ABS.
 *  Все запросы шлют cookie сессии (`credentials: 'include'`) — без неё защищённые
 *  роуты вернут 401. Ошибки не-2xx превращаются в ApiError со статусом. */

// ponytail: локальный бэкенд захардкожен — проект локальный (один пользователь).
// Вынести в env, если когда-нибудь появится не-локальный деплой.
const API_BASE = 'http://localhost:8000';

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

export type User = { id: number; email: string };

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

/** Дашборд (S1.13): по каждому дню диапазона — флаги наличия данных 4 типов. */
export type DayFlags = {
  date: string; // ISO YYYY-MM-DD
  has_food: boolean;
  has_activity: boolean;
  has_training: boolean;
  has_measurement: boolean;
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

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),

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

  // Замеры тела (S2.3): создать запись обхватов (см) на дату. Бэкенд — POST /body-measurements.
  createMeasurement: (input: BodyMeasurementInput) =>
    request<BodyMeasurement>('/body-measurements', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  // Импорт еды: превью разбирает CSV без записи; save пишет идемпотентно по дню.
  previewImport: (file: File) => upload<DiaryPreview>('/import/food/preview', file),
  saveImport: (file: File) => upload<DiaryPreview>('/import/food', file),

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
