import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { useLogin, useMe, useRegister } from '../lib/auth';

// Простой формат — ловит опечатки до запроса; строгую проверку делает бэкенд.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Mode = 'login' | 'register';

/** Серверная ошибка активного режима → человеческий текст. Известные коды:
 *  401 (логин: неверная пара) и 409 (регистрация: email занят); прочее — общий фолбэк. */
function serverErrorMessage(error: unknown, mode: Mode): string | null {
  if (!error) return null;
  if (error instanceof ApiError) {
    if (mode === 'login' && error.status === 401) return 'Неверный email или пароль';
    if (mode === 'register' && error.status === 409) return 'Email уже зарегистрирован';
  }
  return mode === 'login'
    ? 'Не удалось войти. Проверьте, что сервер запущен.'
    : 'Не удалось зарегистрироваться. Проверьте, что сервер запущен.';
}

/** Экран входа/регистрации — цель редиректа из ProtectedRoute. Тоггл переключает
 *  режим, переиспользуя ту же форму и клиентскую валидацию; меняется лишь мутация
 *  (login/register) и тексты. Успех любого режима выставляет сессию → возврат на
 *  исходный защищённый маршрут (или дашборд). */
export default function LoginPage() {
  const { data: user, isPending } = useMe();
  const login = useLogin();
  const register = useRegister();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // Ошибка клиентской валидации; null = поля прошли проверку.
  const [formError, setFormError] = useState<string | null>(null);

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/';

  // Уже залогинен (например, вернулись на /login) — уводим из формы.
  if (!isPending && user) {
    return <Navigate to={from} replace />;
  }

  const isRegister = mode === 'register';
  // Активная мутация под текущий режим — форма и валидация общие.
  const action = isRegister ? register : login;

  // Смена режима сбрасывает прошлую серверную ошибку, чтобы не висела от другого режима.
  function switchMode(next: Mode) {
    if (next === mode) return;
    setMode(next);
    setFormError(null);
    login.reset();
    register.reset();
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedEmail = email.trim();
    if (!EMAIL_RE.test(trimmedEmail)) {
      setFormError('Введите корректный email');
      return;
    }
    if (!password) {
      setFormError('Введите пароль');
      return;
    }
    setFormError(null);
    action.mutate(
      { email: trimmedEmail, password },
      { onSuccess: () => navigate(from, { replace: true }) },
    );
  }

  // Локальная валидация важнее серверной: показываем её первой.
  const errorMessage = formError ?? serverErrorMessage(action.error, mode);

  const tabClass = (active: boolean) =>
    `rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
      active ? 'bg-accent text-accent-ink' : 'text-muted hover:text-fg'
    }`;

  return (
    <main className="grid min-h-screen place-items-center px-5">
      <section className="w-full max-w-sm" aria-labelledby="auth-heading">
        <div className="mb-7 flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl bg-accent font-display text-lg font-bold text-accent-ink shadow-[0_0_24px_-6px] shadow-accent/50">
            A
          </span>
          <span className="font-display text-xl font-semibold tracking-tight">
            ABS<span className="text-muted">.трекер</span>
          </span>
        </div>

        <div
          role="group"
          aria-label="Режим формы"
          className="mb-6 grid grid-cols-2 gap-1 rounded-xl border border-line bg-surface p-1"
        >
          <button
            type="button"
            aria-pressed={!isRegister}
            onClick={() => switchMode('login')}
            className={tabClass(!isRegister)}
          >
            Вход
          </button>
          <button
            type="button"
            aria-pressed={isRegister}
            onClick={() => switchMode('register')}
            className={tabClass(isRegister)}
          >
            Регистрация
          </button>
        </div>

        <h1 id="auth-heading" className="text-display">
          {isRegister ? 'Регистрация' : 'Вход'}
        </h1>
        <p className="mt-2 text-muted">
          {isRegister ? 'Создайте аккаунт личного трекера.' : 'Личный трекер веса и тренировок.'}
        </p>

        <form onSubmit={onSubmit} noValidate className="mt-7 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Email</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setFormError(null);
              }}
              className="rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Пароль</span>
            <input
              type="password"
              name="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setFormError(null);
              }}
              className="rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent"
            />
          </label>

          {errorMessage && (
            <p role="alert" className="text-sm font-medium text-amber">
              {errorMessage}
            </p>
          )}

          <button
            type="submit"
            disabled={action.isPending}
            className="mt-1 rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {action.isPending
              ? isRegister
                ? 'Регистрируем…'
                : 'Входим…'
              : isRegister
                ? 'Зарегистрироваться'
                : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  );
}
