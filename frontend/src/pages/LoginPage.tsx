import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { useLogin, useMe } from '../lib/auth';

/** Экран входа — цель редиректа из ProtectedRoute. Единственный сид-аккаунт,
 *  регистрации нет. Успех → возврат на исходный защищённый маршрут (или дашборд). */
export default function LoginPage() {
  const { data: user, isPending } = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/';

  // Уже залогинен (например, вернулись на /login) — уводим из формы.
  if (!isPending && user) {
    return <Navigate to={from} replace />;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ email, password }, { onSuccess: () => navigate(from, { replace: true }) });
  }

  const errorMessage = login.error
    ? login.error instanceof ApiError && login.error.status === 401
      ? 'Неверный email или пароль'
      : 'Не удалось войти. Проверьте, что сервер запущен.'
    : null;

  return (
    <main className="grid min-h-screen place-items-center px-5">
      <section className="w-full max-w-sm" aria-labelledby="login-heading">
        <div className="mb-7 flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl bg-accent font-display text-lg font-bold text-accent-ink shadow-[0_0_24px_-6px] shadow-accent/50">
            A
          </span>
          <span className="font-display text-xl font-semibold tracking-tight">
            ABS<span className="text-muted">.трекер</span>
          </span>
        </div>

        <h1 id="login-heading" className="text-display">
          Вход
        </h1>
        <p className="mt-2 text-muted">Личный трекер веса и тренировок.</p>

        <form onSubmit={onSubmit} className="mt-7 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Email</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Пароль</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
            disabled={login.isPending}
            className="mt-1 rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {login.isPending ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  );
}
