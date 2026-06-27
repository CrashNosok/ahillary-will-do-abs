/** «Целевые параметры» в «Мой кабинет»: необязательная цель по каждой метрике реестра
 *  (состав тела / обхваты / дневные нормы — кроме роста) + дедлайн и мотивация. Сохраняется
 *  в target_metrics_json активной цели (useSaveGoal: PATCH при наличии, иначе POST; инвариант
 *  «одна активная» держит бэкенд). Эти цели рисуются целевыми линиями на «Прогресс» и питают
 *  рекомендации. Легаси-поля цели затираем на каждом сохранении — карта становится источником
 *  правды (иначе очистка значения в форме не убрала бы старую цель из легаси-колонки). */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, type GoalInput, type MetricGroup, type MetricSpec } from '../lib/api';
import { useActiveGoal, useSaveGoal } from '../lib/goals';
import {
  effectiveTargets,
  metricsByGroup,
  useCurrentMetrics,
  useMetricRegistry,
} from '../lib/metricRegistry';

// Базовый стиль поля без цвета рамки — цвет задаётся per-field по состоянию (см. fieldBorder).
const inputBase =
  'rounded-xl border bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)]';

// Совпадение цели с текущим считаем по округлению до 1 знака (так же отдаёт бэкенд).
const EPS = 0.05;

const GROUPS: { group: MetricGroup; title: string; hint: string }[] = [
  { group: 'composition', title: 'Состав тела', hint: 'Вес и показатели InBody.' },
  { group: 'circumference', title: 'Обхваты', hint: 'Целевые обхваты, см.' },
  {
    group: 'daily',
    title: 'Дневные нормы',
    hint: 'Среднесуточные ориентиры (питание/активность).',
  },
];

const numOrNull = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

export default function ParameterTargetsForm() {
  const { data: goal } = useActiveGoal();
  const { data: registry } = useMetricRegistry();
  const { data: current } = useCurrentMetrics();
  const save = useSaveGoal(goal ?? null);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [deadline, setDeadline] = useState('');
  const [why, setWhy] = useState('');
  // Гидрируем форму один раз (на пару goalId+реестр), а не на каждый goal-рефетч — иначе
  // фоновое обновление кэша затёрло бы то, что пользователь печатает. useSaveGoal обновляет
  // кэш по успеху; новая гидрация — только если сменилась цель (другой id) или загрузился реестр.
  const hydratedFor = useRef<string | null>(null);

  useEffect(() => {
    // Гидрируем только когда загружены и цель, и реестр, и текущие показатели — иначе
    // префилл «текущим» промахнётся. Дефолт поля: сохранённая цель → текущий показатель → пусто.
    if (goal === undefined || !registry || current === undefined) return;
    const key = `${goal?.id ?? 'none'}:${registry.length}`;
    if (hydratedFor.current === key) return;
    const t = effectiveTargets(goal);
    const next: Record<string, string> = {};
    for (const m of registry) {
      const saved = t[m.key];
      const cur = current[m.key];
      next[m.key] = saved != null ? String(saved) : cur != null ? String(cur) : '';
    }
    setVals(next);
    setDeadline(goal?.deadline ?? '');
    setWhy(goal?.why_notes ?? '');
    hydratedFor.current = key;
  }, [goal, registry, current]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const metrics: Record<string, number> = {};
    for (const m of registry ?? []) {
      const n = numOrNull(vals[m.key] ?? '');
      if (n != null) metrics[m.key] = n;
    }
    const input: GoalInput = {
      target_metrics_json: Object.keys(metrics).length ? metrics : null,
      deadline: deadline || null,
      why_notes: why.trim() || null,
    };
    save.mutate(input);
  }

  // Поле одной метрики: рамка зелёная, если ТЕКУЩЕЕ уже не хуже цели (цель достигнута/превзойдена
  // по направлению метрики: для талии/живота — текущее ≤ цели, для бицепса/груди — текущее ≥ цели),
  // красная — если цель ещё не достигнута, нейтральная пока чего-то нет. Под полем — текущее и Δ.
  function renderMetric(m: MetricSpec) {
    const cur = current?.[m.key] ?? null;
    const tgt = numOrNull(vals[m.key] ?? '');
    const hasBoth = cur != null && tgt != null;
    const reached = hasBoth && (m.good_dir === 'up' ? cur >= tgt - EPS : cur <= tgt + EPS);
    const border = !hasBoth
      ? 'border-line focus:border-accent'
      : reached
        ? 'border-accent'
        : 'border-danger';
    const delta = hasBoth ? Math.round((tgt - cur) * 10) / 10 : null;
    const unit = m.unit ? ` ${m.unit}` : '';
    return (
      <label key={m.key} className="flex flex-col gap-1">
        <span className="text-xs text-muted">
          {m.label}
          {m.unit ? `, ${m.unit}` : ''}
        </span>
        <input
          type="number"
          inputMode="decimal"
          step="any"
          min="0"
          value={vals[m.key] ?? ''}
          onChange={(e) => setVals((v) => ({ ...v, [m.key]: e.target.value }))}
          placeholder="—"
          aria-describedby={cur != null ? `cur-${m.key}` : undefined}
          className={`${inputBase} ${border} tabular-nums`}
        />
        {cur != null && (
          <span id={`cur-${m.key}`} className="text-[11px] text-muted tabular-nums">
            Сейчас {cur}
            {unit}
            {delta != null && Math.abs(delta) >= EPS && (
              <>
                {' · Δ '}
                {delta > 0 ? '+' : '−'}
                {Math.abs(delta)}
                {unit}
              </>
            )}
          </span>
        )}
      </label>
    );
  }

  const saveError =
    save.error instanceof ApiError
      ? `Не удалось сохранить (${save.error.status}).`
      : save.error
        ? 'Не удалось сохранить. Проверьте, что сервер запущен.'
        : null;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Целевые параметры"
      className="flex flex-col gap-6 rounded-[var(--radius-card)] border border-line bg-surface p-6"
    >
      <div>
        <h2 className="text-display">Целевые параметры</h2>
        <p className="mt-2 text-sm text-muted">
          Поля заполнены текущими показателями — поменяйте на целевые. Зелёная рамка: цель уже
          достигнута или превзойдена, красная: цель ещё не достигнута (Δ под полем). Заданная цель
          появится линией на «Прогресс» и учтётся в рекомендациях. Рост целью не является.
        </p>
      </div>

      {GROUPS.map(({ group, title, hint }) => (
        <fieldset key={group} className="flex flex-col gap-3 border-t border-line pt-4">
          <legend className="text-sm font-semibold uppercase tracking-wide text-muted">
            {title} <span className="font-normal normal-case">— {hint}</span>
          </legend>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {metricsByGroup(registry ?? [], group).map(renderMetric)}
          </div>
        </fieldset>
      ))}

      <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Дедлайн</span>
          <input
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            className={`${inputBase} border-line [color-scheme:dark] focus:border-accent`}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Мотивация</span>
          <input
            type="text"
            value={why}
            onChange={(e) => setWhy(e.target.value)}
            placeholder="Зачем эта цель"
            className={`${inputBase} border-line focus:border-accent`}
          />
        </label>
      </div>

      {/* Статус-строка с зарезервированной высотой: success/error появляются и исчезают, но
          высота формы не скачет — иначе блоки ниже («Мои дисциплины») дёргаются на каждом сохранении. */}
      <p aria-live="polite" className="min-h-5 text-sm font-medium">
        {saveError ? (
          <span className="text-amber">{saveError}</span>
        ) : save.isSuccess ? (
          <span className="text-accent">Цели сохранены ✓</span>
        ) : null}
      </p>

      <button
        type="submit"
        disabled={save.isPending}
        className="w-fit rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {save.isPending ? 'Сохраняем…' : 'Сохранить цели'}
      </button>
    </form>
  );
}
