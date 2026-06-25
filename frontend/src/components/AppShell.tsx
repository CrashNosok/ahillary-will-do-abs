import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useLogout, useMe } from '../lib/auth';

/** Защищённые маршруты приложения. Метки — для UI, пути — для роутера.
 *  Весь ввод данных собран в один пункт «Ввод данных» (вкладки внутри): еда, активность,
 *  тренировки, замеры, вес, InBody, фото, виды спорта, цель. Их прямые маршруты остаются
 *  рабочими (см. App.tsx) для старых ссылок — просто не дублируются в меню. */
const NAV = [
  { to: '/', label: 'Дашборд', end: true },
  { to: '/profile', label: 'Мой кабинет', end: false },
  { to: '/data-entry', label: 'Ввод данных', end: false },
  { to: '/progress', label: 'Прогресс', end: false },
  { to: '/achievements', label: 'Достижения', end: false },
  { to: '/challenges', label: 'Челленджи', end: false },
  { to: '/recommendations', label: 'Рекомендации', end: false },
  { to: '/coach-phrases', label: 'Фразы коуча', end: false },
  { to: '/settings', label: 'Настройки', end: false },
] as const;

export default function AppShell() {
  const { data: user } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();

  function onLogout() {
    logout.mutate(undefined, { onSuccess: () => navigate('/login', { replace: true }) });
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 py-5">
        <NavLink to="/" className="group flex items-center gap-2.5" aria-label="ABS — на дашборд">
          <span className="grid size-9 place-items-center rounded-xl bg-accent font-display text-lg font-bold text-accent-ink shadow-[0_0_24px_-6px] shadow-accent/50 transition-transform duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] group-hover:-rotate-6">
            A
          </span>
          <span className="font-display text-xl font-semibold tracking-tight">
            ABS<span className="text-muted">.трекер</span>
          </span>
        </NavLink>

        <nav aria-label="Основная навигация" className="order-last w-full sm:order-none sm:w-auto">
          <ul className="flex flex-wrap items-center gap-1 rounded-2xl border border-line bg-surface/60 p-1 backdrop-blur sm:rounded-full">
            {NAV.map(({ to, label, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `block rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
                      isActive
                        ? 'bg-accent text-accent-ink'
                        : 'text-muted hover:bg-panel hover:text-fg'
                    }`
                  }
                >
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden text-sm text-muted sm:inline" title={user.email}>
              {user.display_name || user.email}
            </span>
          )}
          <button
            type="button"
            onClick={onLogout}
            disabled={logout.isPending}
            className="rounded-full border border-line px-3.5 py-1.5 text-sm font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg disabled:opacity-60"
          >
            Выйти
          </button>
        </div>
      </header>

      <main className="flex-1 py-[var(--space-section)]">
        <Outlet />
      </main>

      <footer className="border-t border-line py-6 text-sm text-muted">
        ABS · личный трекер веса и тренировок · v0.1
      </footer>
    </div>
  );
}
