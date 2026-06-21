/** Календарь-хитмап дашборда (S1.14): CSS-grid без либы, 4 типа данных раздельно.
 *  По каждому дню месяца — цветные точки наличия данных (еда/активность/тренировки/
 *  замеры), навигация по месяцам и выделение сегодня. Данные — GET /dashboard. */

import { useMemo, useState } from 'react';
import { type DayFlags } from '../lib/api';
import { useDashboard } from '../lib/dashboard';

// Неделя с понедельника (ru). Порядок задаёт раскладку CSS-grid из 7 колонок.
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'] as const;

// 4 типа данных: ключ флага → ярлык + класс цвета (токены из index.css). Один
// источник правды и для легенды, и для точек на ячейке — добавить тип = одна строка.
const TYPES = [
  { key: 'has_food', label: 'Еда', dot: 'bg-cat-food' },
  { key: 'has_activity', label: 'Активность', dot: 'bg-cat-activity' },
  { key: 'has_training', label: 'Тренировки', dot: 'bg-cat-training' },
  { key: 'has_measurement', label: 'Замеры', dot: 'bg-cat-measurement' },
] as const satisfies ReadonlyArray<{ key: keyof DayFlags; label: string; dot: string }>;

const pad = (n: number) => String(n).padStart(2, '0');

// Локальный ISO (без UTC-сдвига): new Date(iso) трактует строку как UTC и теряет день.
const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

const firstOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1);

const monthTitleFmt = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });
const dayLabelFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Ячейки месяца: ведущие null под смещение первого дня (Пн=0), затем 1..N. */
export function buildMonthCells(monthStart: Date): ({ day: number; iso: string } | null)[] {
  const year = monthStart.getFullYear();
  const month = monthStart.getMonth();
  const offset = (new Date(year, month, 1).getDay() + 6) % 7; // Вс(0)→6, Пн(1)→0
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: ({ day: number; iso: string } | null)[] = Array(offset).fill(null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ day, iso: toISO(new Date(year, month, day)) });
  }
  return cells;
}

export default function CalendarHeatmap() {
  const [monthStart, setMonthStart] = useState(() => firstOfMonth(new Date()));
  const todayIso = toISO(new Date());

  const start = toISO(monthStart);
  const end = toISO(new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0));
  const { data, isPending, error } = useDashboard(start, end);

  const flagsByDate = useMemo(() => {
    const map = new Map<string, DayFlags>();
    for (const d of data?.days ?? []) map.set(d.date, d);
    return map;
  }, [data]);

  const cells = useMemo(() => buildMonthCells(monthStart), [monthStart]);

  const shiftMonth = (delta: number) =>
    setMonthStart((d) => new Date(d.getFullYear(), d.getMonth() + delta, 1));

  const isCurrentMonth = toISO(monthStart) === toISO(firstOfMonth(new Date()));

  return (
    <section
      aria-labelledby="heatmap-heading"
      className="rounded-[var(--radius-card)] border border-line bg-surface p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 id="heatmap-heading" className="text-display">
            Календарь
          </h2>
          <p className="mt-1 text-sm text-muted">Что загружено по дням</p>
        </div>

        <div className="flex items-center gap-2">
          {!isCurrentMonth && (
            <button
              type="button"
              onClick={() => setMonthStart(firstOfMonth(new Date()))}
              className="rounded-full border border-line px-3 py-1.5 text-sm font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
            >
              Сегодня
            </button>
          )}
          <button
            type="button"
            aria-label="Предыдущий месяц"
            onClick={() => shiftMonth(-1)}
            className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
          >
            ‹
          </button>
          <span
            data-testid="heatmap-month"
            className="min-w-40 text-center font-display text-lg font-semibold tracking-tight"
            aria-live="polite"
          >
            {cap(monthTitleFmt.format(monthStart))}
          </span>
          <button
            type="button"
            aria-label="Следующий месяц"
            onClick={() => shiftMonth(1)}
            className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
          >
            ›
          </button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-7 gap-1.5" role="grid" aria-label="Дни месяца">
        {WEEKDAYS.map((w) => (
          <div key={w} className="pb-1 text-center text-xs font-medium uppercase text-muted">
            {w}
          </div>
        ))}
        {cells.map((cell, i) =>
          cell === null ? (
            <div key={`pad-${i}`} aria-hidden="true" />
          ) : (
            <DayCell
              key={cell.iso}
              day={cell.day}
              iso={cell.iso}
              flags={flagsByDate.get(cell.iso)}
              isToday={cell.iso === todayIso}
            />
          ),
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm font-medium text-amber">
          Не удалось загрузить данные. Проверьте, что сервер запущен.
        </p>
      )}
      {isPending && !error && <p className="mt-4 text-sm text-muted">Загрузка…</p>}

      <Legend />
    </section>
  );
}

function DayCell({
  day,
  iso,
  flags,
  isToday,
}: {
  day: number;
  iso: string;
  flags: DayFlags | undefined;
  isToday: boolean;
}) {
  const active = flags ? TYPES.filter((t) => flags[t.key]) : [];
  const summary = active.length
    ? active.map((t) => t.label.toLowerCase()).join(', ')
    : 'нет данных';
  const dateLabel = cap(dayLabelFmt.format(new Date(iso + 'T00:00:00')));

  return (
    <div
      role="gridcell"
      data-testid={`day-${iso}`}
      aria-label={`${dateLabel}: ${summary}`}
      aria-current={isToday ? 'date' : undefined}
      title={`${dateLabel} — ${summary}`}
      className={`relative flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border text-sm transition-colors duration-[var(--duration-fast)] ${
        isToday
          ? 'border-accent font-semibold text-accent'
          : active.length
            ? 'border-line bg-panel text-fg'
            : 'border-line text-muted'
      }`}
    >
      <span>{day}</span>
      <span className="flex h-1.5 items-center gap-0.5" aria-hidden="true">
        {active.map((t) => (
          <span key={t.key} className={`size-1.5 rounded-full ${t.dot}`} />
        ))}
      </span>
    </div>
  );
}

function Legend() {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-4 text-sm text-muted">
      {TYPES.map((t) => (
        <span key={t.key} className="flex items-center gap-1.5">
          <span className={`size-2.5 rounded-full ${t.dot}`} aria-hidden="true" />
          {t.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full border border-accent" aria-hidden="true" />
        Сегодня
      </span>
    </div>
  );
}
