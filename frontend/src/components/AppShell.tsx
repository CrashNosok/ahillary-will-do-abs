import { useState } from 'react';
import Dashboard from './Dashboard';

/** Разделы интерфейса. Роутинга пока нет (каркас) — активный раздел держим в state. */
const SECTIONS = ['Обзор', 'Тренировки', 'Питание', 'Прогресс'] as const;
type Section = (typeof SECTIONS)[number];

export default function AppShell() {
  const [active, setActive] = useState<Section>('Обзор');

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex items-center justify-between gap-4 py-5">
        <a href="#" className="group flex items-center gap-2.5" aria-label="ABS — на главную">
          <span className="grid size-9 place-items-center rounded-xl bg-accent font-display text-lg font-bold text-accent-ink shadow-[0_0_24px_-6px] shadow-accent/50 transition-transform duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] group-hover:-rotate-6">
            A
          </span>
          <span className="font-display text-xl font-semibold tracking-tight">
            ABS<span className="text-muted">.трекер</span>
          </span>
        </a>

        <nav aria-label="Основная навигация">
          <ul className="flex items-center gap-1 rounded-full border border-line bg-surface/60 p-1 backdrop-blur">
            {SECTIONS.map((section) => {
              const isActive = section === active;
              return (
                <li key={section}>
                  <button
                    type="button"
                    onClick={() => setActive(section)}
                    aria-current={isActive ? 'page' : undefined}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
                      isActive
                        ? 'bg-accent text-accent-ink'
                        : 'text-muted hover:bg-panel hover:text-fg'
                    }`}
                  >
                    {section}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div
          className="hidden size-9 place-items-center rounded-full border border-line bg-surface font-medium text-muted sm:grid"
          title="me@example.com"
          aria-hidden="true"
        >
          МЯ
        </div>
      </header>

      <main className="flex-1 py-[var(--space-section)]">
        {active === 'Обзор' ? <Dashboard /> : <SectionStub name={active} />}
      </main>

      <footer className="border-t border-line py-6 text-sm text-muted">
        ABS · личный трекер веса и тренировок · v0.1
      </footer>
    </div>
  );
}

/** Заглушка раздела вне «Обзора» — честно для каркаса спринта 0. */
function SectionStub({ name }: { name: Section }) {
  return (
    <section aria-labelledby="stub-heading" className="max-w-2xl">
      <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
        {name}
      </p>
      <h1 id="stub-heading" className="mt-3 text-display">
        Раздел в разработке
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-muted">
        Каркас интерфейса готов: дизайн-токены, типографика и базовый лейаут на месте. Наполнение
        раздела «{name}» появится в следующих спринтах.
      </p>
    </section>
  );
}
