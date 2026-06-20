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

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
};
