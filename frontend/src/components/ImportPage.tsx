/** Экран импорта дневника питания (S1.8): drag&drop CSV → разобранный день → «Сохранить».
 *  Превью разбирает файл на бэке без записи; «Сохранить» пишет идемпотентно по дню. */

import { useState, type DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, type DiaryPreview, type ImportMeal, type ImportTotals } from '../lib/api';

const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

const kcal = (n: number): string => `${Math.round(n)} ккал`;
const grams = (n: number | null): string => (n == null ? '—' : `${Math.round(n * 10) / 10} г`);

function errorText(error: unknown): string {
  if (error instanceof ApiError)
    return `Не удалось обработать файл (${error.status}). ${error.message}`;
  return 'Не удалось обработать файл. Проверьте, что сервер запущен.';
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const preview = useMutation<DiaryPreview, unknown, File>({ mutationFn: api.previewImport });
  const save = useMutation<DiaryPreview, unknown, File>({ mutationFn: (f) => api.saveImport(f) });

  function handleFile(next: File | undefined) {
    if (!next) return;
    setFile(next);
    save.reset(); // новый файл — сбрасываем прежний результат сохранения
    preview.mutate(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragOver(false);
    handleFile(event.dataTransfer.files[0]);
  }

  const day = preview.data;

  return (
    <section aria-labelledby="import-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Импорт еды
        </p>
        <h1 id="import-heading" className="mt-3 text-display">
          Импорт дневника
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Перетащите CSV-экспорт дневника FatSecret — разберём день, приёмы и итоги. Проверьте и
          нажмите «Сохранить»; повторная загрузка того же дня заменит записи.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`flex min-h-48 cursor-pointer flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed p-8 text-center transition-colors duration-[var(--duration-fast)] ${
            dragOver ? 'border-accent bg-accent/5' : 'border-line bg-surface hover:border-accent/50'
          }`}
        >
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <span className="font-display text-lg font-semibold">Перетащите CSV сюда</span>
          <span className="text-sm text-muted">или нажмите, чтобы выбрать файл</span>
          {file && <span className="mt-1 text-sm font-medium text-accent">{file.name}</span>}
        </label>

        <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
          <h2 className="text-display">Разобранный день</h2>

          {preview.isPending ? (
            <p className="text-muted">Разбираем файл…</p>
          ) : preview.error ? (
            <p role="alert" className="text-sm font-medium text-amber">
              {errorText(preview.error)}
            </p>
          ) : !day ? (
            <p className="text-muted">
              Здесь появится разобранный день: дата, приёмы и итоги — после загрузки файла.
            </p>
          ) : (
            <DayPreview day={day} />
          )}

          {day && (
            <div className="mt-1 flex flex-col gap-3 border-t border-line pt-5">
              {save.isError && (
                <p role="alert" className="text-sm font-medium text-amber">
                  {errorText(save.error)}
                </p>
              )}
              {save.isSuccess && (
                <p role="status" className="text-sm font-medium text-accent">
                  Сохранено: {save.data.product_count} записей за{' '}
                  {dateFmt.format(parseLocalDate(save.data.date))}
                </p>
              )}
              <button
                type="button"
                onClick={() => file && save.mutate(file)}
                disabled={save.isPending || save.isSuccess}
                className="rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить'}
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DayPreview({ day }: { day: DiaryPreview }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="font-display text-2xl font-semibold tracking-tight">
          {dateFmt.format(parseLocalDate(day.date))}
        </span>
        <span className="rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-ink">
          {kcal(day.totals.kcal)} · {day.product_count} продуктов
        </span>
      </div>

      <ul className="flex flex-col gap-4">
        {day.meals.map((meal) => (
          <MealBlock key={meal.meal} meal={meal} />
        ))}
      </ul>

      <DayMacros totals={day.totals} />
    </div>
  );
}

function MealBlock({ meal }: { meal: ImportMeal }) {
  return (
    <li className="rounded-xl border border-line bg-surface/60 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-display font-semibold">{meal.meal}</span>
        <span className="text-sm text-muted">{kcal(meal.totals.kcal)}</span>
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {meal.products.map((p, i) => (
          <li
            key={`${p.product_name}-${i}`}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="text-fg">
              {p.product_name}
              {p.portion_raw && <span className="ml-2 text-muted">{p.portion_raw}</span>}
            </span>
            <span className="shrink-0 tabular-nums text-muted">{kcal(p.kcal ?? 0)}</span>
          </li>
        ))}
      </ul>
    </li>
  );
}

function DayMacros({ totals }: { totals: ImportTotals }) {
  const macros = [
    { label: 'Белки', value: totals.protein_g },
    { label: 'Жиры', value: totals.fat_g },
    { label: 'Углеводы', value: totals.carb_g },
  ];
  return (
    <dl className="grid grid-cols-3 gap-3 border-t border-line pt-4">
      {macros.map((m) => (
        <div key={m.label} className="flex flex-col">
          <dt className="text-sm text-muted">{m.label}</dt>
          <dd className="font-display text-lg font-semibold tabular-nums">{grams(m.value)}</dd>
        </div>
      ))}
    </dl>
  );
}
