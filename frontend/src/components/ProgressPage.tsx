/** Экран «Прогресс»: графики динамики тела (S2.7) + энергобаланса (S2.8).
 *  Тело — вес/обхваты из /progress/body (S2.4); энергия — калории, дефицит,
 *  макросы и активность из /progress/energy (S2.5). Только реальные данные из БД:
 *  нет записей — честный empty-state («не загружено»), демо/выдуманные ряды не рисуем.
 *  ResponsiveContainer Recharts даёт адаптивность на 320/768/1440 без брейкпоинтов. */

import { useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useBodyProgress, useEnergyProgress, useInbodyProgress } from '../lib/progress';
import TrainingProgress from './TrainingProgress';
import { useActiveGoal } from '../lib/goals';
import { effectiveTargets, goalTarget } from '../lib/metricRegistry';
import { classifyDays, countByQuality, type DayQuality } from '../lib/dayQuality';
import type { SeriesPoint } from '../lib/api';

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
  calf_l_cm: 'Бедро Л',
  calf_r_cm: 'Бедро П',
  chest_cm: 'Грудь',
  shoulders_cm: 'Плечи',
  biceps_l_cm: 'Бицепс Л',
  biceps_r_cm: 'Бицепс П',
  glutes_cm: 'Ягодицы',
};

// Обхваты по цели: мышечные — растут (хорошо вверх), жировые (талия/живот) — снижаются
// (хорошо вниз). Раздельные графики читаются однозначно вместо мешанины в одном.
const CIRC_GROW = [
  'chest_cm',
  'shoulders_cm',
  'biceps_l_cm',
  'biceps_r_cm',
  'glutes_cm',
  'calf_l_cm',
  'calf_r_cm',
];
const CIRC_SHRINK = ['waist_cm', 'belly_cm'];

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

/** Состав тела InBody (S2.12): поле → подпись, единицы, цвет линии (дизайн-токены). */
const INBODY_META = [
  { field: 'body_fat_pct', label: 'Процент жира', unit: '%', color: 'var(--color-amber)' },
  { field: 'muscle_mass_kg', label: 'Мышечная масса', unit: 'кг', color: 'var(--color-cat-training)' }, // prettier-ignore
  { field: 'visceral_fat', label: 'Висцеральный жир', unit: 'уровень', color: 'var(--color-cat-food)' }, // prettier-ignore
  { field: 'water', label: 'Вода', unit: 'л', color: 'var(--color-cat-measurement)' },
] as const;

/** Макро-поле → подпись и цвет стека (только дизайн-токены, 3 разных оттенка). */
const MACRO_META = [
  { field: 'protein_g', label: 'Белки', color: 'var(--color-cat-training)' },
  { field: 'fat_g', label: 'Жиры', color: 'var(--color-amber)' },
  { field: 'carb_g', label: 'Углеводы', color: 'var(--color-cat-measurement)' },
] as const;

/** Дефицит: знак → цвет столбца. >0 — расход больше прихода (дефицит, худеем),
 *  <0 — профицит. Разные оттенки + нулевая линия делают знак однозначным. */
const DEFICIT_POS = 'var(--color-accent)';
const DEFICIT_NEG = 'var(--color-amber)';

/** Качество дня (S2.9) → подпись и цвет ячейки/легенды (только дизайн-токены).
 *  good — лайм (дефицит достигнут + полный лог), bad — амбер (лог полный, дефицита
 *  нет), incomplete — нейтральный (нет одного из источников за день). */
const QUALITY_META: Record<DayQuality, { label: string; color: string }> = {
  good: { label: 'Хороший', color: 'var(--color-accent)' },
  bad: { label: 'Плохой', color: 'var(--color-amber)' },
  incomplete: { label: 'Неполный', color: 'var(--color-line)' },
};
const QUALITY_ORDER: DayQuality[] = ['good', 'bad', 'incomplete'];

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

/** Мини-спарклайн: нормализованная ломаная по значениям ряда (без осей). Растягивается
 *  по ширине плитки; толщина штриха фиксирована (non-scaling-stroke), чтобы не плыла.
 *  target — пунктирная целевая линия (включаем её в масштаб, чтобы была в кадре). */
function Sparkline({
  values,
  color,
  target,
}: {
  values: number[];
  color: string;
  target?: number | null;
}) {
  if (values.length < 2) return <div className="h-9" />;
  const scale = target != null ? [...values, target] : values;
  const min = Math.min(...scale);
  const max = Math.max(...scale);
  const span = max - min || 1;
  const y = (v: number) => 2 + (1 - (v - min) / span) * 32; // паддинг 2, высота поля 36
  const pts = values
    .map((v, i) => `${((i / (values.length - 1)) * 100).toFixed(1)},${y(v).toFixed(1)}`)
    .join(' ');
  return (
    <svg viewBox="0 0 100 36" preserveAspectRatio="none" className="h-9 w-full" aria-hidden>
      {target != null && (
        <line
          x1="0"
          x2="100"
          y1={y(target).toFixed(1)}
          y2={y(target).toFixed(1)}
          stroke="var(--color-cat-measurement)"
          strokeWidth={1}
          strokeDasharray="3 2"
          vectorEffect="non-scaling-stroke"
        />
      )}
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Плитка одного показателя: подпись · текущее значение · дельта за период (стрелка+цвет
 *  по «правильности» направления) · спарклайн (+ пунктирная цель) · подпись «цель X».
 *  Очевидно и компактно вместо мешанины линий. */
function MetricTile({
  label,
  unit,
  points,
  goodDir,
  target,
}: {
  label: string;
  unit: string;
  points: SeriesPoint[];
  goodDir: 'up' | 'down';
  target?: number | null;
}) {
  const has = points.length > 0;
  const current = has ? points[points.length - 1].value : null;
  const delta = points.length > 1 ? current! - points[0].value : null;
  const good = delta == null || delta === 0 ? null : goodDir === 'up' ? delta > 0 : delta < 0;
  const deltaColor = good == null ? 'text-muted' : good ? 'text-accent' : 'text-amber';
  const lineColor = good === false ? 'var(--color-amber)' : 'var(--color-accent)';
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-panel p-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-xs font-medium uppercase tracking-wide text-muted">
          {label}
        </span>
        {delta != null && delta !== 0 && (
          <span className={`shrink-0 text-xs font-semibold tabular-nums ${deltaColor}`}>
            {delta > 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
          </span>
        )}
      </div>
      <div className="flex items-end gap-1">
        <span className="font-display text-2xl font-bold leading-none tabular-nums">
          {has ? current!.toFixed(1) : '—'}
        </span>
        {has && <span className="text-xs text-muted">{unit}</span>}
      </div>
      <Sparkline values={points.map((p) => p.value)} color={lineColor} target={target} />
      {target != null && (
        <span className="text-[0.65rem] text-[var(--color-cat-measurement)]">
          цель {target} {unit}
        </span>
      )}
    </div>
  );
}

/** Группа обхватов (рост ИЛИ снижение) — бенто из плиток показателей с данными. */
function CircGroup({
  title,
  hint,
  fields,
  series,
  goodDir,
  targets,
}: {
  title: string;
  hint: string;
  fields: readonly string[];
  series: Record<string, SeriesPoint[]>;
  goodDir: 'up' | 'down';
  targets: Record<string, number>;
}) {
  const present = fields.filter((f) => (series[f]?.length ?? 0) > 0);
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-muted">{hint}</p>
      {present.length > 0 ? (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {present.map((f) => (
            <MetricTile
              key={f}
              label={CIRC_LABELS[f] ?? f}
              unit="см"
              points={series[f]}
              goodDir={goodDir}
              target={targets[f] ?? null}
            />
          ))}
        </div>
      ) : (
        <EmptyNote text="Нет данных за период." />
      )}
    </div>
  );
}

/** Вес — герой-блок: крупное текущее значение + дельта за период + «до цели», под ним
 *  area-график с заливкой-градиентом и целевой линией. Нет данных → честный empty-state. */
function WeightHero({
  points,
  targetWeight,
}: {
  points: SeriesPoint[];
  targetWeight: number | null;
}) {
  const has = points.length > 0;
  const current = has ? points[points.length - 1].value : null;
  const delta = points.length > 1 ? current! - points[0].value : null;
  const toGoal = current != null && targetWeight != null ? current - targetWeight : null;
  const values = points.map((p) => p.value);
  const domain: [number | string, number | string] =
    targetWeight !== null && values.length > 0
      ? [
          Math.floor(Math.min(...values, targetWeight) - 1),
          Math.ceil(Math.max(...values, targetWeight) + 1),
        ]
      : ['auto', 'auto'];
  const rows = points.map((p) => ({ date: p.date, weight: p.value }));

  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold">
            Вес <span className="text-sm font-normal text-muted">(кг)</span>
          </h2>
          {has ? (
            <div className="mt-2 flex flex-wrap items-end gap-x-3 gap-y-1">
              <span className="font-display text-4xl font-bold leading-none tabular-nums">
                {current!.toFixed(1)}
              </span>
              {delta != null && delta !== 0 && (
                <span
                  className={`mb-0.5 text-sm font-semibold ${delta < 0 ? 'text-accent' : 'text-amber'}`}
                >
                  {delta < 0 ? '▼' : '▲'} {Math.abs(delta).toFixed(1)} кг за период
                </span>
              )}
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted">Нет данных веса за период.</p>
          )}
        </div>
        {toGoal != null && (
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-muted">До цели</div>
            <div className="font-display text-2xl font-bold tabular-nums text-[var(--color-cat-measurement)]">
              {Math.abs(toGoal).toFixed(1)}{' '}
              <span className="text-sm font-normal text-muted">кг</span>
            </div>
          </div>
        )}
      </div>

      {has && (
        <div className="mt-4">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <defs>
                <linearGradient id="weightFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtTick}
                tick={axisTick}
                stroke="var(--color-line)"
                minTickGap={24}
              />
              <YAxis tick={axisTick} stroke="var(--color-line)" width={44} domain={domain} />
              <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: 'var(--color-muted)' }} />
              {targetWeight !== null && (
                <ReferenceLine
                  y={targetWeight}
                  stroke="var(--color-cat-measurement)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  ifOverflow="extendDomain"
                  label={{
                    value: `Цель ${targetWeight} кг`,
                    position: 'insideTopRight',
                    fill: 'var(--color-cat-measurement)',
                    fontSize: 12,
                  }}
                />
              )}
              <Area
                type="monotone"
                dataKey="weight"
                name="Вес, кг"
                stroke="var(--color-accent)"
                strokeWidth={2.5}
                fill="url(#weightFill)"
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function ProgressPage() {
  const [periodDays, setPeriodDays] = useState<number>(180);
  const start = isoDaysAgo(periodDays - 1);
  const end = iso(new Date());

  const { data, isLoading, isError } = useBodyProgress(start, end);

  // Цель (S2.9): целевой вес активной SMART-цели → линия поверх графика веса.
  const { data: goal } = useActiveGoal();
  // Целевые значения по реестру метрик (из «Мой кабинет») → целевые линии на графиках.
  const targets = effectiveTargets(goal);
  const targetWeight = goalTarget(goal, 'weight_kg');

  // Только реальные замеры тела: нет записей → честный empty-state, демо не рисуем.
  // Вес/обхваты рисуют WeightHero и CircGroup (герой-блок + бенто-плитки) из этих рядов.
  const weightPts = data?.weight_kg ?? [];
  const circumferences = data?.circumferences ?? {};

  // Состав тела InBody (S2.12): только реальные замеры. Ни одного → «InBody не загружен».
  const inbodyQuery = useInbodyProgress(start, end);
  const composition = inbodyQuery.data?.composition ?? {};
  const hasInbody = Object.values(composition).some((s) => s.length > 0);

  // Энергобаланс (S2.8): только реальные ряды; нет данных → честный empty-state.
  const energyQuery = useEnergyProgress(start, end);
  const energy = energyQuery.data ?? null;
  const hasEnergy =
    !!energy &&
    (energy.kcal_in.length > 0 ||
      energy.kcal_out.length > 0 ||
      energy.deficit.length > 0 ||
      Object.values(energy.macros).some((s) => s.length > 0) ||
      energy.steps.length > 0 ||
      energy.active_min.length > 0);

  const caloriesRows = energy ? mergeSeries({ in: energy.kcal_in, out: energy.kcal_out }) : [];
  const deficitRows = energy ? energy.deficit.map((p) => ({ date: p.date, deficit: p.value })) : [];
  const macroFields = MACRO_META.filter((m) => (energy?.macros[m.field]?.length ?? 0) > 0);
  const macroRows = energy
    ? mergeSeries(Object.fromEntries(macroFields.map((m) => [m.field, energy.macros[m.field]])))
    : [];
  const activityRows = energy
    ? mergeSeries({ steps: energy.steps, active_min: energy.active_min })
    : [];
  const hasActivity = !!energy && (energy.steps.length > 0 || energy.active_min.length > 0);

  // Качество дней (S2.9): классифицируем каждый залогированный день периода.
  const dayClasses = energy ? classifyDays(energy) : [];
  const qualityCounts = countByQuality(dayClasses);

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
          Вес, обхваты и энергобаланс во времени. Выберите период — графики перестроятся под
          выбранный диапазон.
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
      </div>

      {isLoading ? (
        <p className="text-muted">Загрузка…</p>
      ) : (
        <div className="flex flex-col gap-6">
          {isError && (
            <p role="alert" className="text-sm font-medium text-amber">
              Не удалось получить данные с сервера.
            </p>
          )}

          <WeightHero points={weightPts} targetWeight={targetWeight} />

          <CircGroup
            title="Обхваты: цель — рост ↑"
            hint="Мышечные объёмы — грудь, плечи, бицепсы, бёдра, ягодицы. Зелёная стрелка ▲ = растёт (прогресс)."
            fields={CIRC_GROW}
            series={circumferences}
            goodDir="up"
            targets={targets}
          />
          <CircGroup
            title="Обхваты: цель — снижение ↓"
            hint="Талия и живот — жировые отложения. Зелёная стрелка ▼ = снижается (прогресс)."
            fields={CIRC_SHRINK}
            series={circumferences}
            goodDir="down"
            targets={targets}
          />
        </div>
      )}

      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-[var(--space-section)]">
          <div className="max-w-2xl">
            <h2 id="inbody-heading" className="font-display text-2xl font-semibold">
              Состав тела (InBody)
            </h2>
            <p className="mt-2 text-muted">
              Процент жира, мышечная масса, висцеральный жир и вода по замерам InBody за выбранный
              период.
            </p>
          </div>
        </div>

        {inbodyQuery.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : inbodyQuery.isError ? (
          <p role="alert" className="text-sm font-medium text-amber">
            Не удалось получить данные с сервера.
          </p>
        ) : !hasInbody ? (
          <EmptyNote text="InBody ещё не загружен. Загрузите анализ в недельной ячейке календаря — здесь появится динамика состава тела." />
        ) : (
          <div className="flex flex-col gap-6">
            <div className="grid gap-6 lg:grid-cols-2">
              {INBODY_META.map((m) => {
                const rows = (composition[m.field] ?? []).map((p) => ({
                  date: p.date,
                  value: p.value,
                }));
                const target = targets[m.field] ?? null;
                return (
                  <ChartCard key={m.field} title={m.label} unit={m.unit}>
                    {rows.length > 0 ? (
                      <ResponsiveContainer width="100%" height={260}>
                        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
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
                          {target != null && (
                            <ReferenceLine
                              y={target}
                              stroke="var(--color-cat-measurement)"
                              strokeWidth={2}
                              strokeDasharray="6 4"
                              ifOverflow="extendDomain"
                              label={{
                                value: `Цель ${target}`,
                                position: 'insideTopRight',
                                fill: 'var(--color-cat-measurement)',
                                fontSize: 12,
                              }}
                            />
                          )}
                          <Line
                            type="monotone"
                            dataKey="value"
                            name={`${m.label}, ${m.unit}`}
                            stroke={m.color}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            activeDot={{ r: 5 }}
                            connectNulls
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <EmptyNote text="Нет данных за период." />
                    )}
                  </ChartCard>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-[var(--space-section)]">
          <div className="max-w-2xl">
            <h2 id="energy-heading" className="font-display text-2xl font-semibold">
              Энергобаланс
            </h2>
            <p className="mt-2 text-muted">
              Калории, дефицит, макросы и активность по дням за выбранный период.
            </p>
          </div>
        </div>

        {energyQuery.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : energyQuery.isError ? (
          <p role="alert" className="text-sm font-medium text-amber">
            Не удалось получить данные с сервера.
          </p>
        ) : !hasEnergy ? (
          <EmptyNote text="Нет данных питания и активности за период. Импортируйте еду и активность в календаре — здесь появятся калории, дефицит, макросы и шаги." />
        ) : (
          <div className="flex flex-col gap-6">
            <ChartCard title="Калории: приход и расход" unit="ккал/день">
              {caloriesRows.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart
                    data={caloriesRows}
                    margin={{ top: 8, right: 12, bottom: 4, left: -8 }}
                  >
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtTick}
                      tick={axisTick}
                      stroke="var(--color-line)"
                      minTickGap={24}
                    />
                    <YAxis tick={axisTick} stroke="var(--color-line)" width={44} />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelStyle={{ color: 'var(--color-muted)' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {targets.kcal_in != null && (
                      <ReferenceLine
                        y={targets.kcal_in}
                        stroke="var(--color-cat-measurement)"
                        strokeWidth={2}
                        strokeDasharray="6 4"
                        ifOverflow="extendDomain"
                        label={{
                          value: `Цель съедено ${targets.kcal_in}`,
                          position: 'insideTopRight',
                          fill: 'var(--color-cat-measurement)',
                          fontSize: 12,
                        }}
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="in"
                      name="Съедено"
                      stroke="var(--color-cat-food)"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                      connectNulls
                    />
                    <Line
                      type="monotone"
                      dataKey="out"
                      name="Потрачено"
                      stroke="var(--color-amber)"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyNote text="Нет данных калорий за период." />
              )}
            </ChartCard>

            <ChartCard title="Дефицит калорий" unit="ккал/день">
              <p className="-mt-3 mb-3 text-xs text-muted">
                <span className="font-medium text-accent">Выше нуля</span> — дефицит (потрачено
                больше съеденного, идёт снижение).{' '}
                <span className="font-medium text-amber">Ниже нуля</span> — профицит.
              </p>
              {deficitRows.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={deficitRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtTick}
                      tick={axisTick}
                      stroke="var(--color-line)"
                      minTickGap={24}
                    />
                    <YAxis tick={axisTick} stroke="var(--color-line)" width={44} />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelStyle={{ color: 'var(--color-muted)' }}
                    />
                    <ReferenceLine y={0} stroke="var(--color-fg)" strokeWidth={1.5} />
                    {targets.deficit_kcal != null && (
                      <ReferenceLine
                        y={targets.deficit_kcal}
                        stroke="var(--color-cat-measurement)"
                        strokeWidth={2}
                        strokeDasharray="6 4"
                        ifOverflow="extendDomain"
                        label={{
                          value: `Цель ${targets.deficit_kcal}`,
                          position: 'insideTopRight',
                          fill: 'var(--color-cat-measurement)',
                          fontSize: 12,
                        }}
                      />
                    )}
                    <Bar dataKey="deficit" name="Дефицит, ккал" radius={[3, 3, 0, 0]}>
                      {deficitRows.map((r) => (
                        <Cell
                          key={r.date}
                          fill={Number(r.deficit) >= 0 ? DEFICIT_POS : DEFICIT_NEG}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyNote text="Нет данных дефицита за период." />
              )}
            </ChartCard>

            <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6">
              <h2 className="font-display text-lg font-semibold">
                Качество дней{' '}
                <span className="text-sm font-normal text-muted">
                  (хороший = дефицит достигнут и лог полный)
                </span>
              </h2>
              {dayClasses.length > 0 ? (
                <>
                  <div
                    role="img"
                    aria-label={`Качество дней за период: хороших ${qualityCounts.good}, плохих ${qualityCounts.bad}, неполных ${qualityCounts.incomplete}`}
                    className="mt-4 flex flex-wrap gap-1.5"
                  >
                    {dayClasses.map((d) => (
                      <span
                        key={d.date}
                        title={`${fmtTick(d.date)} — ${QUALITY_META[d.quality].label}${
                          d.deficit !== null ? ` · дефицит ${Math.round(d.deficit)} ккал` : ''
                        }`}
                        className="size-6 rounded-md border border-line/60"
                        style={{ background: QUALITY_META[d.quality].color }}
                      />
                    ))}
                  </div>
                  <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
                    {QUALITY_ORDER.map((q) => (
                      <li key={q} className="flex items-center gap-2 text-muted">
                        <span
                          className="size-3 rounded-sm"
                          style={{ background: QUALITY_META[q].color }}
                        />
                        {QUALITY_META[q].label}:{' '}
                        <span className="font-medium text-fg">{qualityCounts[q]}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <EmptyNote text="Нет залогированных дней за период." />
              )}
            </div>

            <ChartCard title="Макросы (стек)" unit="г/день">
              {macroFields.length > 0 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={macroRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtTick}
                      tick={axisTick}
                      stroke="var(--color-line)"
                      minTickGap={24}
                    />
                    <YAxis tick={axisTick} stroke="var(--color-line)" width={44} />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelStyle={{ color: 'var(--color-muted)' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {macroFields.map((m) => (
                      <Bar
                        key={m.field}
                        dataKey={m.field}
                        name={m.label}
                        stackId="macros"
                        fill={m.color}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyNote text="Нет данных макросов за период." />
              )}
            </ChartCard>

            <ChartCard title="Шаги и активность" unit="шаги · мин">
              {hasActivity ? (
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart
                    data={activityRows}
                    margin={{ top: 8, right: 4, bottom: 4, left: -8 }}
                  >
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtTick}
                      tick={axisTick}
                      stroke="var(--color-line)"
                      minTickGap={24}
                    />
                    <YAxis yAxisId="steps" tick={axisTick} stroke="var(--color-line)" width={48} />
                    <YAxis
                      yAxisId="min"
                      orientation="right"
                      tick={axisTick}
                      stroke="var(--color-line)"
                      width={36}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelStyle={{ color: 'var(--color-muted)' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {targets.steps != null && (
                      <ReferenceLine
                        yAxisId="steps"
                        y={targets.steps}
                        stroke="var(--color-cat-measurement)"
                        strokeWidth={2}
                        strokeDasharray="6 4"
                        ifOverflow="extendDomain"
                        label={{
                          value: `Цель ${targets.steps}`,
                          position: 'insideTopRight',
                          fill: 'var(--color-cat-measurement)',
                          fontSize: 12,
                        }}
                      />
                    )}
                    <Bar
                      yAxisId="steps"
                      dataKey="steps"
                      name="Шаги"
                      fill="var(--color-cat-training)"
                      radius={[3, 3, 0, 0]}
                    />
                    <Line
                      yAxisId="min"
                      type="monotone"
                      dataKey="active_min"
                      name="Активные мин"
                      stroke="var(--color-accent)"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                      connectNulls
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <EmptyNote text="Нет данных активности за период." />
              )}
            </ChartCard>
          </div>
        )}
      </div>

      {/* Тренировочный прогресс (S3.12): силовые + кардио рядом с прогрессом тела. */}
      <TrainingProgress start={start} end={end} />
    </section>
  );
}
