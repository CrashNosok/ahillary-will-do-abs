/** Экран импорта скрина активности Welltory (S1.11): загрузка → сверка → сохранение.
 *  Превью распознаёт скрин без записи; пользователь сверяет поля с картинкой рядом,
 *  правит при необходимости и сохраняет — пишутся именно выверенные значения. */

import { useEffect, useState, type DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  api,
  ApiError,
  type ActivityDay,
  type ActivityFields,
  type ActivityPreview,
} from '../lib/api';

/** Плитки Welltory → подпись поля и единица. Порядок = порядок на экране. */
const FIELDS: { key: keyof ActivityFields; label: string; unit: string }[] = [
  { key: 'total_kcal', label: 'Всего ккал', unit: 'ккал' },
  { key: 'active_kcal', label: 'Активные ккал', unit: 'ккал' },
  { key: 'steps', label: 'Шаги', unit: '' },
  { key: 'moving_min', label: 'В движении', unit: 'мин' },
  { key: 'idle_min', label: 'Без движения', unit: 'мин' },
  { key: 'warmup_min', label: 'Разминка', unit: 'мин' },
  { key: 'active_met', label: 'Активные МЕТ', unit: 'МЕТ' },
  { key: 'intense_met', label: 'Интенсивные МЕТ', unit: 'МЕТ' },
];

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

function pickFields(p: ActivityPreview): ActivityFields {
  return {
    total_kcal: p.total_kcal,
    active_kcal: p.active_kcal,
    steps: p.steps,
    moving_min: p.moving_min,
    idle_min: p.idle_min,
    warmup_min: p.warmup_min,
    active_met: p.active_met,
    intense_met: p.intense_met,
  };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError)
    return `Не удалось обработать скрин (${error.status}). ${error.message}`;
  return 'Не удалось обработать скрин. Проверьте, что сервер запущен.';
}

export default function ActivityImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [date, setDate] = useState<string>(todayIso());
  const [fields, setFields] = useState<ActivityFields | null>(null);
  const [rawJson, setRawJson] = useState<unknown>(null);

  // Превью картинки из локального файла — без round-trip; чистим objectURL за собой.
  useEffect(() => {
    if (!file) {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const preview = useMutation<ActivityPreview, unknown, File>({
    mutationFn: (f) => api.previewActivity(f, date),
    onSuccess: (data) => {
      setFields(pickFields(data));
      setRawJson(data.raw_json);
    },
  });

  const save = useMutation<ActivityDay, unknown, void>({
    mutationFn: () => {
      if (!file || !fields) throw new Error('нет данных для сохранения');
      return api.saveActivity(file, date, fields, rawJson);
    },
  });

  function handleFile(next: File | undefined) {
    if (!next) return;
    setFile(next);
    setFields(null);
    save.reset();
    preview.mutate(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragOver(false);
    handleFile(event.dataTransfer.files[0]);
  }

  function setField(key: keyof ActivityFields, raw: string) {
    setFields((prev) => {
      if (!prev) return prev;
      if (raw.trim() === '') return { ...prev, [key]: null };
      const n = Number(raw);
      return Number.isFinite(n) ? { ...prev, [key]: Math.round(n) } : prev;
    });
    save.reset(); // правка после сохранения — снова даём сохранить
  }

  return (
    <section
      aria-labelledby="activity-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Импорт активности
        </p>
        <h1 id="activity-heading" className="mt-3 text-display">
          Скрин Welltory
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Загрузите скрин «Анализ активности» — распознаем поля и покажем рядом с картинкой.
          Сверьте, при необходимости поправьте значения и нажмите «Сохранить»: повторная загрузка
          того же дня заменит запись.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Левая колонка — загрузка и превью картинки для сверки */}
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`flex min-h-64 cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-[var(--radius-card)] border-2 border-dashed p-4 text-center transition-colors duration-[var(--duration-fast)] ${
            dragOver ? 'border-accent bg-accent/5' : 'border-line bg-surface hover:border-accent/50'
          }`}
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          {imageUrl ? (
            <>
              <img
                src={imageUrl}
                alt="Загруженный скрин активности Welltory"
                className="max-h-[28rem] w-auto rounded-xl border border-line object-contain"
              />
              <span className="text-sm font-medium text-accent">{file?.name}</span>
              <span className="text-xs text-muted">Нажмите, чтобы выбрать другой скрин</span>
            </>
          ) : (
            <>
              <span className="font-display text-lg font-semibold">Перетащите скрин сюда</span>
              <span className="text-sm text-muted">или нажмите, чтобы выбрать файл</span>
            </>
          )}
        </label>

        {/* Правая колонка — распознанные поля для сверки и правки */}
        <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-display">Распознанные поля</h2>
            <label className="flex items-center gap-2 text-sm text-muted">
              День
              <input
                type="date"
                value={date}
                onChange={(e) => {
                  setDate(e.target.value);
                  save.reset();
                }}
                className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-fg outline-none focus:border-accent"
              />
            </label>
          </div>

          {preview.isPending ? (
            <p className="text-muted">Распознаём скрин…</p>
          ) : preview.error ? (
            <p role="alert" className="text-sm font-medium text-amber">
              {errorText(preview.error)}
            </p>
          ) : !fields ? (
            <p className="text-muted">
              Здесь появятся распознанные поля — сверьте их с картинкой и поправьте при
              необходимости перед сохранением.
            </p>
          ) : (
            <>
              <dl className="grid gap-3 sm:grid-cols-2">
                {FIELDS.map(({ key, label, unit }) => (
                  <div key={key} className="flex flex-col gap-1">
                    <label htmlFor={`f-${key}`} className="text-sm text-muted">
                      {label}
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        id={`f-${key}`}
                        type="number"
                        inputMode="numeric"
                        value={fields[key] ?? ''}
                        onChange={(e) => setField(key, e.target.value)}
                        placeholder="—"
                        className="w-full rounded-lg border border-line bg-surface px-3 py-2 font-display text-lg font-semibold tabular-nums text-fg outline-none focus:border-accent"
                      />
                      {unit && <span className="shrink-0 text-sm text-muted">{unit}</span>}
                    </div>
                  </div>
                ))}
              </dl>

              <div className="mt-1 flex flex-col gap-3 border-t border-line pt-5">
                {save.isError && (
                  <p role="alert" className="text-sm font-medium text-amber">
                    {errorText(save.error)}
                  </p>
                )}
                {save.isSuccess && (
                  <p role="status" className="text-sm font-medium text-accent">
                    Сохранено за {dateFmt.format(parseLocalDate(save.data.date))}
                    {save.data.total_kcal != null && ` · ${save.data.total_kcal} ккал`}
                    {save.data.steps != null && `, ${save.data.steps} шагов`}
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => save.mutate()}
                  disabled={save.isPending || save.isSuccess}
                  className="rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
