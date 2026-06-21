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

/** Загрузка файла (multipart). Не ставим Content-Type — браузер сам выставит
 *  boundary; ручной заголовок сломал бы парсинг формы на бэке. */
async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
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

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),

  // Список (200 + []), а не /goals/active (404 при отсутствии) — чтобы пустое
  // состояние не порождало console.error/4xx; активную цель выбираем на клиенте.
  listGoals: () => request<Goal[]>('/goals'),
  createGoal: (input: GoalInput) =>
    request<Goal>('/goals', { method: 'POST', body: JSON.stringify(input) }),
  updateGoal: (id: number, input: GoalInput) =>
    request<Goal>(`/goals/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),

  // Импорт еды: превью разбирает CSV без записи; save пишет идемпотентно по дню.
  previewImport: (file: File) => upload<DiaryPreview>('/import/food/preview', file),
  saveImport: (file: File) => upload<DiaryPreview>('/import/food', file),
};
