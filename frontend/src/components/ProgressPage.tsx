/** Экран «Прогресс» (S2.7): графики динамики тела — вес и обхваты.
 *  Данные берём из /progress/body (S2.4) за выбранный период. Если реальных
 *  замеров ещё нет (БД пустая), рисуем демо-набор за тот же период — графики
 *  обязаны рисоваться (критерий приёмки), а ResponsiveContainer Recharts даёт
 *  адаптивность на 320/768/1440 без ручных брейкпоинтов. */

import { useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useBodyProgress } from '../lib/progress';
import type { BodyProgress, SeriesPoint } from '../lib/api';

/** Варианты периода (дни). 180 — дефолт бэкенда для редких замеров тела. */
const PERIODS = [
  { days: 30, label: '30 дней' },
  { days: 90, label: '90 дней' },
  { days: 180, label: '180 дней' },
  { days: 365, label: 'Год' },
] as const;

/** Поле обхвата → русская подпись (как на экране замеров). */
const CIRC_LABELS: Record<string, string> = {
  waist_cm: 'Талия',
  belly_cm: 'Живот',
  calf_l_cm: 'Голень Л',
  calf_r_cm: 'Голень П',
  chest_cm: 'Грудь',
  shoulders_cm: 'Плечи',
  biceps_l_cm: 'Бицепс Л',
  biceps_r_cm: 'Бицепс П',
  glutes_cm: 'Ягодицы',
};

/** Палитра линий — только из дизайн-токенов, без хардкода цвета. */
const PALETTE = [
  'var(--color-accent)',
  'var(--color-cat-measurement)',
  'var(--color-cat-training)',
  'var(--color-amber)',
  'var(--color-cat-food)',
  'var(--color-muted)',
];

type Row = Record<string, string | number>;

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return iso(d);
}

/** ISO `YYYY-MM-DD` → короткая метка оси `dd.mm`. */
function fmtTick(value: string): string {
  const [, m, d] = value.split('-');
  return `${d}.${m}`;
}

/** Слить ряды `{поле: точки}` в строки Recharts по дате (по одной строке на дату). */
function mergeSeries(series: Record<string, SeriesPoint[]>): Row[] {
  const byDate = new Map<string, Row>();
  for (const [field, points] of Object.entries(series)) {
    for (const p of points) {
      const row = byDate.get(p.date) ?? { date: p.date };
      row[field] = p.value;
      byDate.set(p.date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

/** Демо-данные за выбранный период: 7 точек с плавным снижением. Рисуются,
 *  когда реальных замеров нет, чтобы графики всё равно отрисовались. */
function buildSample(periodDays: number): BodyProgress {
  const points = 7;
  const end = new Date();
  const step = Math.max(1, Math.floor((periodDays - 1) / (points - 1)));
  const dates: string[] = [];
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(d.getDate() - i * step);
    dates.push(iso(d));
  }

  const trend = (from: number, to: number): SeriesPoint[] =>
    dates.map((date, idx) => ({
      date,
      value: Math.round((from - ((from - to) * idx) / (points - 1)) * 10) / 10,
    }));

  return {
    start: dates[0],
    end: dates[dates.length - 1],
    weight_kg: trend(92, 85.4),
    circumferences: {
      waist_cm: trend(96, 88.5),
      belly_cm: trend(102, 93.7),
      chest_cm: trend(104, 100.2),
      glutes_cm: trend(103, 98.1),
    },
  };
}

const tooltipStyle = {
  background: 'var(--color-panel)',
  border: '1px solid var(--color-line)',
  borderRadius: '0.75rem',
  color: 'var(--color-fg)',
};
const axisTick = { fill: 'var(--color-muted)', fontSize: 12 };

function ChartCard({
  title,
  unit,
  children,
}: {
  title: string;
  unit: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6">
      <h2 className="font-display text-lg font-semibold">
        {title} <span className="text-sm font-normal text-muted">({unit})</span>
      </h2>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="py-12 text-center text-sm text-muted">{text}</p>;
}

export default function ProgressPage() {
  const [periodDays, setPeriodDays] = useState<number>(180);
  const start = isoDaysAgo(periodDays - 1);
  const end = iso(new Date());

  const { data, isLoading, isError } = useBodyProgress(start, end);

  const hasReal =
    !!data &&
    (data.weight_kg.length > 0 || Object.values(data.circumferences).some((s) => s.length > 0));
  const isSample = !hasReal;
  const source = hasReal ? data! : buildSample(periodDays);

  const weightRows = source.weight_kg.map((p) => ({ date: p.date, weight: p.value }));
  const circFields = Object.entries(source.circumferences)
    .filter(([, points]) => points.length > 0)
    .map(([field]) => field);
  const circRows = mergeSeries(
    Object.fromEntries(circFields.map((f) => [f, source.circumferences[f]])),
  );

  return (
    <section
      aria-labelledby="progress-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Прогресс
        </p>
        <h1 id="progress-heading" className="mt-3 text-display">
          Динамика тела
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Вес и обхваты во времени. Выберите период — графики перестроятся под выбранный диапазон.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div
          role="group"
          aria-label="Период"
          className="flex flex-wrap gap-1 rounded-full border border-line bg-surface/60 p-1 backdrop-blur"
        >
          {PERIODS.map(({ days, label }) => (
            <button
              key={days}
              type="button"
              aria-pressed={periodDays === days}
              onClick={() => setPeriodDays(days)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
                periodDays === days
                  ? 'bg-accent text-accent-ink'
                  : 'text-muted hover:bg-panel hover:text-fg'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {isSample && (
          <span className="rounded-full border border-amber/40 px-3 py-1 text-xs font-medium text-amber">
            Демо-данные
          </span>
        )}
      </div>

      {isLoading ? (
        <p className="text-muted">Загрузка…</p>
      ) : (
        <div className="flex flex-col gap-6">
          {isError && (
            <p role="alert" className="text-sm font-medium text-amber">
              Не удалось получить данные с сервера — показаны демо-данные.
            </p>
          )}

          <ChartCard title="Вес" unit="кг">
            {weightRows.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={weightRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={fmtTick}
                    tick={axisTick}
                    stroke="var(--color-line)"
                    minTickGap={24}
                  />
                  <YAxis
                    tick={axisTick}
                    stroke="var(--color-line)"
                    width={44}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: 'var(--color-muted)' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="weight"
                    name="Вес, кг"
                    stroke="var(--color-accent)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyNote text="Нет данных веса за период." />
            )}
          </ChartCard>

          <ChartCard title="Обхваты" unit="см">
            {circFields.length > 0 ? (
              <ResponsiveContainer width="100%" height={340}>
                <LineChart data={circRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={fmtTick}
                    tick={axisTick}
                    stroke="var(--color-line)"
                    minTickGap={24}
                  />
                  <YAxis
                    tick={axisTick}
                    stroke="var(--color-line)"
                    width={44}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: 'var(--color-muted)' }}
                  />
                  <Legend
                    formatter={(value) => CIRC_LABELS[value] ?? value}
                    wrapperStyle={{ fontSize: 12 }}
                  />
                  {circFields.map((field, i) => (
                    <Line
                      key={field}
                      type="monotone"
                      dataKey={field}
                      name={field}
                      stroke={PALETTE[i % PALETTE.length]}
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyNote text="Нет данных обхватов за период." />
            )}
          </ChartCard>
        </div>
      )}
    </section>
  );
}
