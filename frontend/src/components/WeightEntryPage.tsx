/** Вкладка «Вес» (Ввод данных): простой ручной ввод веса (кг) за дату — раз в 1–2 недели.
 *  Без фото: вес апсёртится в inbody_measurement по дню (POST /body/weight), откуда его
 *  читает график прогресса веса. Валидация на сабмите: положительное число в разумных границах. */

import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type InbodyMeasurement, type WeightInput } from '../lib/api';

const MAX_WEIGHT_KG = 500; // верхняя граница — отсекает явные опечатки (совпадает с бэкендом)

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

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Не удалось сохранить (${error.status}). ${error.message}`;
  return 'Не удалось сохранить. Проверьте, что сервер запущен.';
}

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

export default function WeightEntryPage({ initialDate }: { initialDate?: string }) {
  const qc = useQueryClient();
  const [date, setDate] = useState<string>(initialDate ?? todayIso());
  const [weight, setWeight] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const save = useMutation<InbodyMeasurement, unknown, WeightInput>({
    mutationFn: (input) => api.createWeight(input),
    onSuccess: () => {
      // вес виден в графике прогресса и в дашборде — освежаем оба кэша
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['progress'] });
    },
  });

  function reset() {
    setValidationError(null);
    save.reset(); // правка после сохранения — снова даём сохранить
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!date) {
      setValidationError('Укажите дату.');
      return;
    }
    const n = Number(weight.trim());
    if (!weight.trim() || !Number.isFinite(n) || n <= 0) {
      setValidationError('Введите вес — положительное число в килограммах.');
      return;
    }
    if (n > MAX_WEIGHT_KG) {
      setValidationError('Слишком большое значение веса — проверьте ввод.');
      return;
    }
    setValidationError(null);
    save.mutate({ date, weight_kg: n });
  }

  return (
    <section aria-labelledby="weight-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Вес
        </p>
        <h1 id="weight-heading" className="mt-3 text-display">
          Запись веса
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Взвешивайтесь раз в одну-две недели в одинаковых условиях — утром, натощак. Введите число
          в килограммах: запись попадёт в историю прогресса веса.
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        noValidate
        aria-label="Запись веса"
        className="flex max-w-sm flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6"
      >
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Дата</span>
          <input
            type="date"
            value={date}
            max={todayIso()}
            onChange={(e) => {
              setDate(e.target.value);
              reset();
            }}
            className={`${inputCls} [color-scheme:dark]`}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Вес, кг</span>
          <input
            type="number"
            inputMode="decimal"
            step="any"
            min="0"
            value={weight}
            onChange={(e) => {
              setWeight(e.target.value);
              reset();
            }}
            placeholder="—"
            className={`${inputCls} tabular-nums`}
          />
        </label>

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
            {save.data.weight_kg != null && ` · ${save.data.weight_kg} кг`}
          </p>
        )}

        <button
          type="submit"
          disabled={save.isPending || save.isSuccess}
          className="mt-1 self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить вес'}
        </button>
      </form>
    </section>
  );
}
