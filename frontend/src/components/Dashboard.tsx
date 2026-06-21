/** Контент раздела «Обзор» — витрина каркаса: герой + панель дня + хитмап.
 *  Панель «Сегодня» (S1.15) и календарь-хитмап (S1.14) — на реальных данных
 *  GET /dashboard. Карточки «План на сегодня»/«Цель» — плейсхолдеры до своих спринтов. */

import CalendarHeatmap from './CalendarHeatmap';
import Coach from './Coach';
import TodayPanel from './TodayPanel';

const TODAY = [
  { time: '08:30', title: 'Замер веса', done: true },
  { time: '13:00', title: 'Обед — 620 ккал', done: true },
  { time: '19:00', title: 'Силовая: ноги + пресс', done: false },
];

export default function Dashboard() {
  return (
    <div className="flex flex-col gap-[var(--space-section)]">
      <section aria-labelledby="hero-heading">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Обзор · сегодня
        </p>
        <h1 id="hero-heading" className="mt-3 max-w-3xl text-hero">
          С возвращением.
          <br />
          Держим <span className="text-accent">темп</span>.
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
          Личный трекер веса, питания и тренировок. Одна цель, ежедневный ритм и честные цифры — без
          лишнего шума.
        </p>
      </section>

      <Coach />

      <TodayPanel />

      <CalendarHeatmap />

      <section aria-labelledby="today-heading" className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-[var(--radius-card)] border border-line bg-surface p-6">
          <div className="flex items-center justify-between">
            <h2 id="today-heading" className="text-display">
              План на сегодня
            </h2>
            <span className="rounded-full bg-panel px-3 py-1 text-sm text-muted">2 из 3</span>
          </div>
          <ul className="mt-5 flex flex-col divide-y divide-line">
            {TODAY.map((item) => (
              <li key={item.title} className="flex items-center gap-4 py-3.5">
                <span
                  className={`grid size-6 shrink-0 place-items-center rounded-full border text-xs ${
                    item.done ? 'border-accent bg-accent text-accent-ink' : 'border-line text-muted'
                  }`}
                  aria-hidden="true"
                >
                  {item.done ? '✓' : ''}
                </span>
                <span className="w-14 shrink-0 font-mono text-sm text-muted">{item.time}</span>
                <span className={item.done ? 'text-muted line-through' : 'text-fg'}>
                  {item.title}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col justify-between gap-6 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
          <div>
            <h2 className="text-display">Цель</h2>
            <p className="mt-2 text-muted">До 75,0 кг осталось</p>
            <p className="mt-1 font-display text-4xl font-semibold text-accent">3,4 кг</p>
          </div>
          <button
            type="button"
            className="w-full rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0"
          >
            Записать тренировку
          </button>
        </div>
      </section>
    </div>
  );
}
