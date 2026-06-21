/** Экран настройки SMART-цели (S1.4): форма задания цели + витрина текущей цели.
 *  Бэкенд (S1.3) держит инвариант «одна активная цель»; здесь — ввод и чтение. */

import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, type Goal, type GoalInput } from '../lib/api';
import { useActiveGoal, useSaveGoal } from '../lib/goals';

// Фиксированный набор обхватов (см) — самые ходовые замеры. Хранятся в target_measurements_json.
const MEASUREMENTS = [
  { key: 'waist', label: 'Талия' },
  { key: 'chest', label: 'Грудь' },
  { key: 'hips', label: 'Бёдра' },
] as const;

type FormState = {
  target_weight_kg: string;
  target_body_fat_pct: string;
  deadline: string;
  why_notes: string;
  measurements: Record<string, string>;
};

const EMPTY: FormState = {
  target_weight_kg: '',
  target_body_fat_pct: '',
  deadline: '',
  why_notes: '',
  measurements: {},
};

function toForm(goal: Goal | null): FormState {
  if (!goal) return EMPTY;
  const measurements: Record<string, string> = {};
  for (const { key } of MEASUREMENTS) {
    const v = goal.target_measurements_json?.[key];
    measurements[key] = v == null ? '' : String(v);
  }
  return {
    target_weight_kg: goal.target_weight_kg == null ? '' : String(goal.target_weight_kg),
    target_body_fat_pct: goal.target_body_fat_pct == null ? '' : String(goal.target_body_fat_pct),
    deadline: goal.deadline ?? '',
    why_notes: goal.why_notes ?? '',
    measurements,
  };
}

const numOrNull = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

// ponytail: дата как локальная (YYYY-MM-DD) — new Date(iso) трактует строку как UTC и сдвигает день.
function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function daysLeft(deadlineIso: string): number {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((parseLocalDate(deadlineIso).getTime() - today.getTime()) / 86_400_000);
}

function pluralDays(n: number): string {
  const mod100 = n % 100;
  const mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) return 'дней';
  if (mod10 === 1) return 'день';
  if (mod10 >= 2 && mod10 <= 4) return 'дня';
  return 'дней';
}

function deadlineLabel(deadlineIso: string): string {
  const n = daysLeft(deadlineIso);
  if (n > 0) return `осталось ${n} ${pluralDays(n)}`;
  if (n === 0) return 'дедлайн сегодня';
  return `срок истёк ${-n} ${pluralDays(-n)} назад`;
}

const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

export default function GoalPage() {
  const { data: goal, isPending } = useActiveGoal();
  const save = useSaveGoal(goal ?? null);
  const [form, setForm] = useState<FormState>(EMPTY);

  // Подставляем сохранённую цель в форму, как только она прочитана (и после сохранения).
  useEffect(() => {
    if (goal !== undefined) setForm(toForm(goal));
  }, [goal]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const entries = MEASUREMENTS.map(
      ({ key }) => [key, numOrNull(form.measurements[key] ?? '')] as const,
    ).filter(([, v]) => v != null) as [string, number][];

    const input: GoalInput = {
      target_weight_kg: numOrNull(form.target_weight_kg),
      target_body_fat_pct: numOrNull(form.target_body_fat_pct),
      target_measurements_json: entries.length ? Object.fromEntries(entries) : null,
      deadline: form.deadline || null,
      why_notes: form.why_notes.trim() || null,
    };
    save.mutate(input);
  }

  const hasGoal = Boolean(goal);
  const saveError =
    save.error instanceof ApiError
      ? `Не удалось сохранить (${save.error.status}).`
      : save.error
        ? 'Не удалось сохранить. Проверьте, что сервер запущен.'
        : null;

  return (
    <section aria-labelledby="goal-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Цель
        </p>
        <h1 id="goal-heading" className="mt-3 text-display">
          SMART-цель
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Задайте измеримый ориентир и срок. Активной может быть одна цель — она и попадёт на
          дашборд.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <CurrentGoal goal={goal ?? null} isPending={isPending} />

        <form
          onSubmit={onSubmit}
          noValidate
          aria-label="Настройка цели"
          className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6"
        >
          <h2 className="text-display">{hasGoal ? 'Изменить цель' : 'Новая цель'}</h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Целевой вес, кг"
              value={form.target_weight_kg}
              onChange={(v) => setForm((f) => ({ ...f, target_weight_kg: v }))}
            />
            <Field
              label="Целевой %жира"
              value={form.target_body_fat_pct}
              onChange={(v) => setForm((f) => ({ ...f, target_body_fat_pct: v }))}
            />
          </div>

          <fieldset className="grid gap-4 sm:grid-cols-3">
            <legend className="mb-1 text-sm font-medium text-muted">Целевые обхваты, см</legend>
            {MEASUREMENTS.map(({ key, label }) => (
              <Field
                key={key}
                label={label}
                value={form.measurements[key] ?? ''}
                onChange={(v) =>
                  setForm((f) => ({ ...f, measurements: { ...f.measurements, [key]: v } }))
                }
              />
            ))}
          </fieldset>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Дедлайн</span>
            <input
              type="date"
              name="deadline"
              value={form.deadline}
              onChange={(e) => setForm((f) => ({ ...f, deadline: e.target.value }))}
              className={`${inputCls} [color-scheme:dark]`}
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Мотивация</span>
            <textarea
              name="why_notes"
              rows={3}
              value={form.why_notes}
              onChange={(e) => setForm((f) => ({ ...f, why_notes: e.target.value }))}
              placeholder="Зачем эта цель — что станет лучше, когда вы её достигнете."
              className={`${inputCls} resize-y`}
            />
          </label>

          {saveError && (
            <p role="alert" className="text-sm font-medium text-amber">
              {saveError}
            </p>
          )}

          <button
            type="submit"
            disabled={save.isPending}
            className="mt-1 rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {save.isPending ? 'Сохраняем…' : hasGoal ? 'Сохранить изменения' : 'Создать цель'}
          </button>
        </form>
      </div>
    </section>
  );
}

function CurrentGoal({ goal, isPending }: { goal: Goal | null; isPending: boolean }) {
  return (
    <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
      <h2 className="text-display">Текущая цель</h2>

      {isPending ? (
        <p className="text-muted">Загрузка…</p>
      ) : !goal ? (
        <p className="text-muted">
          Активной цели пока нет. Заполните форму справа и сохраните — она появится здесь.
        </p>
      ) : (
        <dl className="flex flex-col gap-4">
          <Metric label="Целевой вес" value={goal.target_weight_kg} unit="кг" />
          <Metric label="Целевой %жира" value={goal.target_body_fat_pct} unit="%" />
          {MEASUREMENTS.map(({ key, label }) => (
            <Metric
              key={key}
              label={label}
              value={goal.target_measurements_json?.[key] ?? null}
              unit="см"
            />
          ))}

          <div className="border-t border-line pt-4">
            <dt className="text-sm text-muted">Дедлайн</dt>
            {goal.deadline ? (
              <dd className="mt-1 flex flex-wrap items-baseline gap-2">
                <span className="font-display text-2xl font-semibold tracking-tight">
                  {dateFmt.format(parseLocalDate(goal.deadline))}
                </span>
                <span
                  data-testid="days-left"
                  className="rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-ink"
                >
                  {deadlineLabel(goal.deadline)}
                </span>
              </dd>
            ) : (
              <dd className="mt-1 text-muted">не задан</dd>
            )}
          </div>

          {goal.why_notes && (
            <div className="border-t border-line pt-4">
              <dt className="text-sm text-muted">Мотивация</dt>
              <dd className="mt-1 leading-relaxed">{goal.why_notes}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}

function Metric({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="font-display text-xl font-semibold tracking-tight">
        {value == null ? <span className="text-base font-normal text-muted">—</span> : value}
        {value != null && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
      </dd>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-muted">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="any"
        min="0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    </label>
  );
}
