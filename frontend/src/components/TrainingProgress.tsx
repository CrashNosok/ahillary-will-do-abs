/** Тренировочный прогресс на экране «Прогресс» (S3.12): силовые (рабочий вес, 1ПМ,
 *  тоннаж) с подсветкой PR + кардио-графики (дистанция, темп, пульс, эффективность).
 *  Встроено в ProgressPage рядом с прогрессом тела — динамика силовых и кардио на
 *  одном экране (критерий приёмки). Данные — S3.11 (/progress/strength|cardio) +
 *  PR S3.10 (/workouts/prs); при пустой БД рисуем демо (см. lib/trainingProgress). */

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
import { useCardioProgress, usePersonalRecords, useStrengthProgress } from '../lib/progress';
import { useExercises, useSports } from '../lib/sports';
import {
  buildCardioView,
  buildStrengthView,
  type CardioExerciseView,
  type StrengthExerciseView,
} from '../lib/trainingProgress';
import type { SeriesPoint } from '../lib/api';

type Props = { periodDays: number; start: string; end: string };
type Row = Record<string, string | number>;

const tooltipStyle = {
  background: 'var(--color-panel)',
  border: '1px solid var(--color-line)',
  borderRadius: '0.75rem',
  color: 'var(--color-fg)',
};
const axisTick = { fill: 'var(--color-muted)', fontSize: 12 };
const labelStyle = { color: 'var(--color-muted)' };

/** Палитра линий тоннажа по группам — только дизайн-токены. */
const GROUP_PALETTE = [
  'var(--color-cat-training)',
  'var(--color-accent)',
  'var(--color-amber)',
  'var(--color-cat-measurement)',
  'var(--color-cat-food)',
];

function fmtTick(value: string): string {
  const [, m, d] = value.split('-');
  return `${d}.${m}`;
}

/** Слить именованные ряды в строки Recharts по дате (по строке на дату). */
function mergeSeries(series: Record<string, SeriesPoint[]>): Row[] {
  const byDate = new Map<string, Row>();
  for (const [key, points] of Object.entries(series)) {
    for (const p of points) {
      const row = byDate.get(p.date) ?? { date: p.date };
      row[key] = p.value;
      byDate.set(p.date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

/** Точки звезды (5 лучей) вокруг (cx,cy) — маркер личного рекорда. */
function starPoints(cx: number, cy: number, outer: number, inner: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? outer : inner;
    const a = (Math.PI / 5) * i - Math.PI / 2;
    pts.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`);
  }
  return pts.join(' ');
}

type DotProps = { cx?: number; cy?: number; index?: number; payload?: { date?: string } };

/** Рендер точки линии: PR-день — звезда (подсветка), остальные — обычная точка. */
function prDot(prDates: Set<string>, color: string) {
  return function renderDot(props: DotProps): React.ReactElement {
    const { cx, cy, index, payload } = props;
    if (cx == null || cy == null) return <g key={index} />;
    if (payload?.date && prDates.has(payload.date)) {
      return (
        <polygon
          key={index}
          points={starPoints(cx, cy, 7, 3.2)}
          fill="var(--color-accent)"
          stroke="var(--color-panel)"
          strokeWidth={1}
        />
      );
    }
    return <circle key={index} cx={cx} cy={cy} r={2.5} fill={color} />;
  };
}

function ChartCard({
  title,
  unit,
  hint,
  children,
}: {
  title: string;
  unit: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6">
      <h3 className="font-display text-lg font-semibold">
        {title} <span className="text-sm font-normal text-muted">({unit})</span>
      </h3>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="py-12 text-center text-sm text-muted">{text}</p>;
}

function SampleBadge() {
  return (
    <span className="rounded-full border border-amber/40 px-3 py-1 text-xs font-medium text-amber">
      Демо-данные
    </span>
  );
}

/** Пилюли-переключатели упражнений (как селектор периода на экране). */
function ExercisePills({
  items,
  active,
  onSelect,
  ariaLabel,
}: {
  items: { name: string }[];
  active: number;
  onSelect: (i: number) => void;
  ariaLabel: string;
}) {
  if (items.length < 2) return null;
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="flex flex-wrap gap-1 rounded-full border border-line bg-surface/60 p-1 backdrop-blur"
    >
      {items.map((it, i) => (
        <button
          key={it.name}
          type="button"
          aria-pressed={active === i}
          onClick={() => onSelect(i)}
          className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
            active === i ? 'bg-accent text-accent-ink' : 'text-muted hover:bg-panel hover:text-fg'
          }`}
        >
          {it.name}
        </button>
      ))}
    </div>
  );
}

/** Карточка одного ряда: одна линия + опциональная подсветка PR-точек. */
function SingleLineCard({
  title,
  unit,
  hint,
  points,
  name,
  color,
  prDates,
}: {
  title: string;
  unit: string;
  hint?: string;
  points: SeriesPoint[];
  name: string;
  color: string;
  prDates?: Set<string>;
}) {
  const rows = points.map((p) => ({ date: p.date, value: p.value }));
  return (
    <ChartCard title={title} unit={unit} hint={hint}>
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
            <Tooltip contentStyle={tooltipStyle} labelStyle={labelStyle} />
            <Line
              type="monotone"
              dataKey="value"
              name={name}
              stroke={color}
              strokeWidth={2}
              dot={prDates ? prDot(prDates, color) : { r: 2.5 }}
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
}

function StrengthBlock({ exercise }: { exercise: StrengthExerciseView }) {
  const wRows = mergeSeries({ weight: exercise.weight, oneRm: exercise.oneRm });
  return (
    <div className="flex flex-col gap-6">
      <ChartCard
        title="Рабочий вес и 1ПМ"
        unit="кг"
        hint="★ — личный рекорд (PR): новый максимум рабочего веса или оценки 1ПМ."
      >
        {wRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={wRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
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
              <Tooltip contentStyle={tooltipStyle} labelStyle={labelStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="weight"
                name="Рабочий вес"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={prDot(exercise.prWeightDates, 'var(--color-accent)')}
                activeDot={{ r: 5 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="oneRm"
                name="1ПМ (оценка)"
                stroke="var(--color-cat-training)"
                strokeWidth={2}
                dot={prDot(exercise.pr1rmDates, 'var(--color-cat-training)')}
                activeDot={{ r: 5 }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyNote text="Нет силовых подходов за период." />
        )}
      </ChartCard>

      <SingleLineCard
        title="Тоннаж"
        unit="кг"
        hint="Суммарная нагрузка за день: Σ вес × повторения."
        points={exercise.tonnage}
        name="Тоннаж"
        color="var(--color-amber)"
      />
    </div>
  );
}

export default function TrainingProgress({ periodDays, start, end }: Props) {
  const strengthQuery = useStrengthProgress(start, end);
  const cardioQuery = useCardioProgress(start, end);
  const prsQuery = usePersonalRecords();
  const exercisesQuery = useExercises();
  const sportsQuery = useSports();

  const prs = prsQuery.data ?? [];
  const exercises = exercisesQuery.data ?? [];
  const sports = sportsQuery.data ?? [];

  const strength = buildStrengthView(strengthQuery.data, exercises, sports, prs, periodDays);
  const cardio = buildCardioView(cardioQuery.data, exercises, prs, periodDays);

  const [strengthIdx, setStrengthIdx] = useState(0);
  const [cardioIdx, setCardioIdx] = useState(0);
  const selStrength: StrengthExerciseView | undefined =
    strength.exercises[Math.min(strengthIdx, strength.exercises.length - 1)];
  const selCardio: CardioExerciseView | undefined =
    cardio.exercises[Math.min(cardioIdx, cardio.exercises.length - 1)];

  const groupRows = mergeSeries(
    Object.fromEntries(strength.groups.map((g, i) => [`g${i}`, g.tonnage])),
  );

  return (
    <div className="flex flex-col gap-[var(--space-section)]">
      {/* Силовые */}
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-[var(--space-section)]">
          <div className="max-w-2xl">
            <h2 id="strength-heading" className="font-display text-2xl font-semibold">
              Силовые тренировки
            </h2>
            <p className="mt-2 text-muted">
              Рабочий вес, 1ПМ и тоннаж по упражнениям за выбранный период. Личные рекорды (PR)
              подсвечены звёздами на графике.
            </p>
          </div>
          {strength.isSample && <SampleBadge />}
        </div>

        {strengthQuery.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : selStrength ? (
          <>
            <ExercisePills
              items={strength.exercises}
              active={strengthIdx}
              onSelect={setStrengthIdx}
              ariaLabel="Упражнение (силовые)"
            />
            <StrengthBlock exercise={selStrength} />

            <ChartCard
              title="Тоннаж по видам спорта"
              unit="кг"
              hint="Суммарная нагрузка по группам упражнений."
            >
              {groupRows.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={groupRows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtTick}
                      tick={axisTick}
                      stroke="var(--color-line)"
                      minTickGap={24}
                    />
                    <YAxis tick={axisTick} stroke="var(--color-line)" width={44} />
                    <Tooltip contentStyle={tooltipStyle} labelStyle={labelStyle} />
                    <Legend
                      formatter={(value) => {
                        const idx = Number(String(value).replace('g', ''));
                        return strength.groups[idx]?.name ?? value;
                      }}
                      wrapperStyle={{ fontSize: 12 }}
                    />
                    {strength.groups.map((g, i) => (
                      <Line
                        key={g.sportId ?? `null-${i}`}
                        type="monotone"
                        dataKey={`g${i}`}
                        name={`g${i}`}
                        stroke={GROUP_PALETTE[i % GROUP_PALETTE.length]}
                        strokeWidth={2}
                        dot={{ r: 2.5 }}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyNote text="Нет данных тоннажа за период." />
              )}
            </ChartCard>
          </>
        ) : (
          <EmptyNote text="Нет силовых тренировок за период." />
        )}
      </div>

      {/* Кардио */}
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-[var(--space-section)]">
          <div className="max-w-2xl">
            <h2 id="cardio-heading" className="font-display text-2xl font-semibold">
              Кардио
            </h2>
            <p className="mt-2 text-muted">
              Дистанция, темп, средний пульс и пульсовая эффективность по дням за выбранный период.
            </p>
          </div>
          {cardio.isSample && <SampleBadge />}
        </div>

        {cardioQuery.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : selCardio ? (
          <>
            <ExercisePills
              items={cardio.exercises}
              active={cardioIdx}
              onSelect={setCardioIdx}
              ariaLabel="Упражнение (кардио)"
            />
            <div className="grid gap-6 lg:grid-cols-2">
              <SingleLineCard
                title="Дистанция"
                unit="км"
                hint="★ — личный рекорд по максимальной дистанции."
                points={selCardio.distance}
                name="Дистанция, км"
                color="var(--color-cat-training)"
                prDates={selCardio.prDistanceDates}
              />
              <SingleLineCard
                title="Темп"
                unit="сек/км"
                hint="Меньше — быстрее. ★ — личный рекорд (лучший темп)."
                points={selCardio.pace}
                name="Темп, сек/км"
                color="var(--color-accent)"
                prDates={selCardio.prPaceDates}
              />
              <SingleLineCard
                title="Средний пульс"
                unit="уд/мин"
                points={selCardio.avgHr}
                name="Средний пульс"
                color="var(--color-amber)"
              />
              <SingleLineCard
                title="Пульсовая эффективность"
                unit="м/удар"
                hint="Метров пробегаемой дистанции на один удар сердца — выше лучше."
                points={selCardio.efficiency}
                name="Эффективность"
                color="var(--color-cat-measurement)"
              />
            </div>
          </>
        ) : (
          <EmptyNote text="Нет кардио-тренировок за период." />
        )}
      </div>
    </div>
  );
}
