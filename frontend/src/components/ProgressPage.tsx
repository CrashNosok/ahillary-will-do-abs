/** Экран «Прогресс»: графики динамики тела (S2.7) + энергобаланса (S2.8).
 *  Тело — вес/обхваты из /progress/body (S2.4); энергия — калории, дефицит,
 *  макросы и активность из /progress/energy (S2.5). Данные за выбранный период;
 *  если реальных записей ещё нет (БД пустая), рисуем демо-набор — графики обязаны
 *  рисоваться (критерий приёмки), а ResponsiveContainer Recharts даёт
 *  адаптивность на 320/768/1440 без ручных брейкпоинтов. */

import { useState } from 'react';
import {
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
import { useBodyProgress, useEnergyProgress } from '../lib/progress';
import { useActiveGoal } from '../lib/goals';
import { classifyDays, countByQuality, type DayQuality } from '../lib/dayQuality';
import type { BodyProgress, EnergyProgress, SeriesPoint } from '../lib/api';

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

/** Демо-данные энергобаланса: 14 подряд идущих дней до сегодня. Дефицит
 *  намеренно пересекает ноль (есть и дефицитные, и профицитные дни) — чтобы знак
 *  читался однозначно. ponytail: детерминированная синусоида, стабильный демо. */
function buildEnergySample(): EnergyProgress {
  const days = 14;
  const end = new Date();
  const kcalIn: SeriesPoint[] = [];
  const kcalOut: SeriesPoint[] = [];
  const deficit: SeriesPoint[] = [];
  const protein: SeriesPoint[] = [];
  const fat: SeriesPoint[] = [];
  const carb: SeriesPoint[] = [];
  const steps: SeriesPoint[] = [];
  const activeMin: SeriesPoint[] = [];

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(d.getDate() - i);
    const date = iso(d);
    const wave = Math.sin(i * 0.9);
    // Базы прихода/расхода равны (2200), а амплитуды расходятся — поэтому дефицит
    // (cout − cin) заметно гуляет вокруг нуля: есть и дефицитные, и профицитные дни.
    const cin = Math.round(2200 + wave * 300);
    kcalIn.push({ date, value: cin });
    protein.push({ date, value: Math.round(130 + wave * 20) });
    fat.push({ date, value: Math.round(70 + wave * 12) });
    carb.push({ date, value: Math.round(210 + wave * 35) });
    // ponytail: 2 дня без активности → «неполный лог» (нет расхода и дефицита),
    // чтобы подсветка качества дней (S2.9) показывала все три категории на демо.
    if (i === 4 || i === 10) continue;
    const cout = Math.round(2200 + Math.cos(i * 0.6) * 450);
    kcalOut.push({ date, value: cout });
    deficit.push({ date, value: cout - cin });
    steps.push({ date, value: Math.round(8500 + wave * 2800) });
    activeMin.push({ date, value: Math.round(55 + wave * 22) });
  }

  return {
    start: kcalIn[0].date,
    end: kcalIn[kcalIn.length - 1].date,
    kcal_in: kcalIn,
    kcal_out: kcalOut,
    deficit,
    macros: { protein_g: protein, fat_g: fat, carb_g: carb },
    steps,
    active_min: activeMin,
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

  // Цель (S2.9): целевой вес активной SMART-цели → линия поверх графика веса.
  const { data: goal } = useActiveGoal();
  const targetWeight = goal?.target_weight_kg ?? null;

  const hasReal =
    !!data &&
    (data.weight_kg.length > 0 || Object.values(data.circumferences).some((s) => s.length > 0));
  const isSample = !hasReal;
  const source = hasReal ? data! : buildSample(periodDays);

  const weightRows = source.weight_kg.map((p) => ({ date: p.date, weight: p.value }));
  // Домен оси веса расширяем так, чтобы целевая линия гарантированно попала в кадр
  // (цель ниже текущего веса легко уехала бы за нижнюю границу 'auto').
  const weightValues = weightRows.map((r) => r.weight);
  const weightDomain: [number | string, number | string] =
    targetWeight !== null && weightValues.length > 0
      ? [
          Math.floor(Math.min(...weightValues, targetWeight) - 1),
          Math.ceil(Math.max(...weightValues, targetWeight) + 1),
        ]
      : ['auto', 'auto'];
  const circFields = Object.entries(source.circumferences)
    .filter(([, points]) => points.length > 0)
    .map(([field]) => field);
  const circRows = mergeSeries(
    Object.fromEntries(circFields.map((f) => [f, source.circumferences[f]])),
  );

  // Энергобаланс (S2.8): тот же период. Показываем реальные ряды только когда они
  // наполняют ВСЕ 4 графика (ккал, дефицит, макросы, активность) — иначе один-два
  // случайных дня оставили бы графики (в т.ч. ключевой «Дефицит») пустыми. Пока
  // полного дня нет — рисуем демо целиком, чтобы 4 графика и знак дефицита читались.
  const energyQuery = useEnergyProgress(start, end);
  const energy = energyQuery.data;
  const energyComplete =
    !!energy &&
    (energy.kcal_in.length > 0 || energy.kcal_out.length > 0) &&
    energy.deficit.length > 0 &&
    Object.values(energy.macros).some((s) => s.length > 0) &&
    (energy.steps.length > 0 || energy.active_min.length > 0);
  const energySample = !energyComplete;
  const energySource = energyComplete ? energy! : buildEnergySample();

  const caloriesRows = mergeSeries({ in: energySource.kcal_in, out: energySource.kcal_out });
  const deficitRows = energySource.deficit.map((p) => ({ date: p.date, deficit: p.value }));
  const macroFields = MACRO_META.filter((m) => (energySource.macros[m.field]?.length ?? 0) > 0);
  const macroRows = mergeSeries(
    Object.fromEntries(macroFields.map((m) => [m.field, energySource.macros[m.field]])),
  );
  const activityRows = mergeSeries({
    steps: energySource.steps,
    active_min: energySource.active_min,
  });
  const hasActivity = energySource.steps.length > 0 || energySource.active_min.length > 0;

  // Качество дней (S2.9): классифицируем каждый залогированный день периода.
  const dayClasses = classifyDays(energySource);
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
                    domain={weightDomain}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: 'var(--color-muted)' }}
                  />
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
          {energySample && (
            <span className="rounded-full border border-amber/40 px-3 py-1 text-xs font-medium text-amber">
              Демо-данные
            </span>
          )}
        </div>

        {energyQuery.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : (
          <div className="flex flex-col gap-6">
            {energyQuery.isError && (
              <p role="alert" className="text-sm font-medium text-amber">
                Не удалось получить данные с сервера — показаны демо-данные.
              </p>
            )}

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
    </section>
  );
}
