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
};
