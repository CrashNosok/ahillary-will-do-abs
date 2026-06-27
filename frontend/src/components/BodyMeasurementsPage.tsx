/** Экран ввода замеров тела (S2.3): форма обхватов (см) + дата → запись в БД.
 *  Бэкенд (S2.2) держит CRUD над body_measurement; здесь — ручной ввод раз в ~2 недели.
 *  Числовые поля валидируются на сабмите: каждый заполненный — положительное число,
 *  и хотя бы один замер обязателен (иначе сохранять нечего). */

import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, type BodyMeasurement, type BodyMeasurementInput } from '../lib/api';

/** Замеры тела → подпись и порядок на экране. Ключи = поля бэкенда (всё в см). */
const FIELDS: { key: keyof Omit<BodyMeasurementInput, 'date'>; label: string }[] = [
  { key: 'height_cm', label: 'Рост' },
  { key: 'waist_cm', label: 'Талия' },
  { key: 'belly_cm', label: 'Живот' },
  { key: 'calf_l_cm', label: 'Бедро Л' },
  { key: 'calf_r_cm', label: 'Бедро П' },
  { key: 'chest_cm', label: 'Грудь' },
  { key: 'shoulders_cm', label: 'Плечи' },
  { key: 'biceps_l_cm', label: 'Бицепс Л' },
  { key: 'biceps_r_cm', label: 'Бицепс П' },
  { key: 'glutes_cm', label: 'Ягодицы' },
];

type Values = Record<(typeof FIELDS)[number]['key'], string>;

const EMPTY_VALUES = Object.fromEntries(FIELDS.map(({ key }) => [key, ''])) as Values;

const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Собрать payload из формы или вернуть текст ошибки валидации (первое нарушение). */
function buildInput(
  date: string,
  values: Values,
): { input?: BodyMeasurementInput; error?: string } {
  if (!date) return { error: 'Укажите дату замера.' };

  const nums = Object.fromEntries(FIELDS.map(({ key }) => [key, null])) as Omit<
    BodyMeasurementInput,
    'date'
  >;
  let filled = 0;
  for (const { key, label } of FIELDS) {
    const raw = values[key].trim();
    if (!raw) continue;
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) {
      return { error: `«${label}» — введите положительное число.` };
    }
    nums[key] = n;
    filled += 1;
  }
  if (filled === 0) return { error: 'Заполните хотя бы один замер.' };

  return { input: { date, ...nums } };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Не удалось сохранить (${error.status}). ${error.message}`;
  return 'Не удалось сохранить. Проверьте, что сервер запущен.';
}

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

export default function BodyMeasurementsPage({ initialDate }: { initialDate?: string }) {
  const [date, setDate] = useState<string>(initialDate ?? todayIso());
  const [values, setValues] = useState<Values>(EMPTY_VALUES);
  const [validationError, setValidationError] = useState<string | null>(null);

  const save = useMutation<BodyMeasurement, unknown, BodyMeasurementInput>({
    mutationFn: (input) => api.createMeasurement(input),
  });

  function setField(key: keyof Values, raw: string) {
    setValues((prev) => ({ ...prev, [key]: raw }));
    setValidationError(null);
    save.reset(); // правка после сохранения — снова даём сохранить
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const { input, error } = buildInput(date, values);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    save.mutate(input!);
  }

  return (
    <section aria-labelledby="body-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Замеры тела
        </p>
        <h1 id="body-heading" className="mt-3 text-display">
          Новый замер
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Снимайте обхваты сантиметром раз в одну-две недели. Все значения в сантиметрах — заполните
          те, что измерили, и сохраните: запись попадёт в историю прогресса.
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        noValidate
        aria-label="Замеры тела"
        className="flex max-w-3xl flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6"
      >
        <label className="flex max-w-xs flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Дата замера</span>
          <input
            type="date"
            name="date"
            value={date}
            max={todayIso()}
            onChange={(e) => {
              setDate(e.target.value);
              setValidationError(null);
              save.reset();
            }}
            className={`${inputCls} [color-scheme:dark]`}
          />
        </label>

        <fieldset className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <legend className="mb-1 text-sm font-medium text-muted">Обхваты, см</legend>
          {FIELDS.map(({ key, label }) => (
            <label key={key} className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-muted">{label}</span>
              <input
                id={`m-${key}`}
                type="number"
                inputMode="decimal"
                step="any"
                min="0"
                value={values[key]}
                onChange={(e) => setField(key, e.target.value)}
                placeholder="—"
                className={`${inputCls} tabular-nums`}
              />
            </label>
          ))}
        </fieldset>

        {validationError && (
          <p role="alert" className="text-sm font-medium text-amber">
            {validationError}
          </p>
        )}
        {save.isError && (
          <p role="alert" className="text-sm font-medium text-amber">
            {errorText(save.error)}
          </p>
        )}
        {save.isSuccess && (
          <p role="status" className="text-sm font-medium text-accent">
            Сохранено за {dateFmt.format(parseLocalDate(save.data.date))}
          </p>
        )}

        <button
          type="submit"
          disabled={save.isPending || save.isSuccess}
          className="mt-1 self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить замер'}
        </button>
      </form>
    </section>
  );
}
