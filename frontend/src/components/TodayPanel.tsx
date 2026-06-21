/** Панель «Сегодня» дашборда (S1.15): кольца завершённости дня + бейдж стрика +
 *  сводка энергобаланса (съедено / потрачено / дефицит). Всё на реальных данных
 *  GET /dashboard за сегодня (start=end=сегодня): days[0] → кольца, current_streak →
 *  бейдж, today → ккал. Кольцо разбито на 4 дуги — по одному источнику данных. */

import { type DayFlags, type TodaySummary } from '../lib/api';
import { useDashboard } from '../lib/dashboard';

// 4 источника данных = 4 дуги кольца. Цвета — те же токены, что у легенды хитмапа.
const SOURCES = [
  { key: 'has_food', label: 'Еда', color: 'var(--color-cat-food)' },
  { key: 'has_activity', label: 'Активность', color: 'var(--color-cat-activity)' },
  { key: 'has_training', label: 'Тренировки', color: 'var(--color-cat-training)' },
  { key: 'has_measurement', label: 'Замеры', color: 'var(--color-cat-measurement)' },
] as const satisfies ReadonlyArray<{ key: keyof DayFlags; label: string; color: string }>;

const pad = (n: number) => String(n).padStart(2, '0');
const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fmtKcal = (n: number) => n.toLocaleString('ru-RU');

// Склонение «день/дня/дней» по числу (1 день, 2 дня, 5 дней, 11 дней).
function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'дня';
  return 'дней';
}

// — Геометрия сегментного кольца —
const SIZE = 132;
const STROKE = 13;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;
const SEG = C / 4; // длина четверти
const GAP = 10; // зазор между дугами (px по окружности)

export default function TodayPanel() {
  const todayIso = toISO(new Date());
  const { data, isPending, error } = useDashboard(todayIso, todayIso);

  const flags = data?.days[0];
  const filled = SOURCES.filter((s) => flags?.[s.key]).length;

  return (
    <section
      aria-labelledby="today-panel-heading"
      className="rounded-[var(--radius-card)] border border-line bg-surface p-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 id="today-panel-heading" className="text-display">
            Сегодня
          </h2>
          <p className="mt-1 text-sm text-muted">Дисциплина логирования за день</p>
        </div>
        <StreakBadge streak={data?.current_streak ?? 0} />
      </div>

      {error ? (
        <p role="alert" className="mt-6 text-sm font-medium text-amber">
          Не удалось загрузить данные. Проверьте, что сервер запущен.
        </p>
      ) : isPending ? (
        <p className="mt-6 text-sm text-muted">Загрузка…</p>
      ) : (
        <div className="mt-6 grid items-center gap-6 sm:grid-cols-[auto_1fr]">
          <div className="flex items-center gap-5">
            <CompletionRing flags={flags} filled={filled} />
            <ul className="flex flex-col gap-2">
              {SOURCES.map((s) => {
                const on = Boolean(flags?.[s.key]);
                return (
                  <li key={s.key} className="flex items-center gap-2 text-sm">
                    <span
                      className="size-2.5 rounded-full"
                      style={{ backgroundColor: on ? s.color : 'var(--color-line)' }}
                      aria-hidden="true"
                    />
                    <span className={on ? 'text-fg' : 'text-muted'}>{s.label}</span>
                    <span className="text-muted" aria-hidden="true">
                      {on ? '✓' : '—'}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          <KcalSummary today={data.today} />
        </div>
      )}
    </section>
  );
}

function CompletionRing({ flags, filled }: { flags: DayFlags | undefined; filled: number }) {
  return (
    <div
      className="relative grid shrink-0 place-items-center"
      style={{ width: SIZE, height: SIZE }}
    >
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`Заполнено источников за сегодня: ${filled} из ${SOURCES.length}`}
      >
        {SOURCES.map((s, i) => {
          const on = Boolean(flags?.[s.key]);
          return (
            <circle
              key={s.key}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={R}
              fill="none"
              stroke={on ? s.color : 'var(--color-line)'}
              strokeWidth={STROKE}
              strokeDasharray={`${SEG - GAP} ${C - (SEG - GAP)}`}
              strokeDashoffset={-i * SEG}
              transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            />
          );
        })}
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-display text-3xl font-semibold leading-none tabular-nums">
          {filled}
          <span className="text-muted">/{SOURCES.length}</span>
        </span>
        <span className="mt-1 text-xs uppercase tracking-wide text-muted">источников</span>
      </div>
    </div>
  );
}

function StreakBadge({ streak }: { streak: number }) {
  const active = streak > 0;
  return (
    <div
      className="flex items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-2.5"
      data-testid="streak-badge"
    >
      <span aria-hidden="true" className={`text-2xl ${active ? '' : 'opacity-40 grayscale'}`}>
        🔥
      </span>
      <div className="leading-tight">
        <p className="font-display text-2xl font-semibold tabular-nums">{streak}</p>
        <p className="text-xs text-muted">{pluralDays(streak)} подряд</p>
      </div>
    </div>
  );
}

function KcalSummary({ today }: { today: TodaySummary }) {
  const isDeficit = today.deficit >= 0;
  return (
    <div className="grid grid-cols-3 gap-3" data-testid="kcal-summary">
      <Metric label="Съедено" value={today.kcal_in} accent="var(--color-cat-food)" />
      <Metric label="Потрачено" value={today.kcal_out} accent="var(--color-cat-activity)" />
      <Metric
        label={isDeficit ? 'Дефицит' : 'Профицит'}
        value={Math.abs(today.deficit)}
        accent={isDeficit ? 'var(--color-accent)' : 'var(--color-amber)'}
      />
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-2xl border border-line bg-panel p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 flex items-baseline gap-1">
        <span
          className="font-display text-2xl font-semibold tabular-nums"
          style={{ color: accent }}
        >
          {fmtKcal(value)}
        </span>
        <span className="text-xs text-muted">ккал</span>
      </p>
    </div>
  );
}
