/** Экран ингеста скрина InBody (S2.11): загрузка → сверка → сохранение.
 *  Превью распознаёт скрин без записи; пользователь сверяет пять ключевых полей с
 *  картинкой рядом, правит при необходимости и сохраняет — пишутся именно выверенные
 *  значения. Прочие показатели (BMI, базовый обмен и т.п.) показаны как есть. */

import { useEffect, useState, type DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  api,
  ApiError,
  type InbodyFields,
  type InbodyMeasurement,
  type InbodyPreview,
} from '../lib/api';

/** Пять ключевых показателей InBody → подпись поля и единица. */
const FIELDS: { key: keyof InbodyFields; label: string; unit: string }[] = [
  { key: 'weight_kg', label: 'Вес', unit: 'кг' },
  { key: 'body_fat_pct', label: 'Процент жира', unit: '%' },
  { key: 'muscle_mass_kg', label: 'Мышечная масса', unit: 'кг' },
  { key: 'visceral_fat', label: 'Висцеральный жир', unit: '' },
  { key: 'water', label: 'Вода', unit: 'л' },
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

function pickFields(p: InbodyPreview): InbodyFields {
  return {
    weight_kg: p.weight_kg,
    body_fat_pct: p.body_fat_pct,
    muscle_mass_kg: p.muscle_mass_kg,
    visceral_fat: p.visceral_fat,
    water: p.water,
  };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError)
    return `Не удалось обработать скрин (${error.status}). ${error.message}`;
  return 'Не удалось обработать скрин. Проверьте, что сервер запущен.';
}

export default function InbodyImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [date, setDate] = useState<string>(todayIso());
  const [fields, setFields] = useState<InbodyFields | null>(null);
  const [metricsJson, setMetricsJson] = useState<Record<string, unknown>>({});

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

  const preview = useMutation<InbodyPreview, unknown, File>({
    mutationFn: (f) => api.previewInbody(f, date),
    onSuccess: (data) => {
      setFields(pickFields(data));
      setMetricsJson(data.metrics_json ?? {});
    },
  });

  const save = useMutation<InbodyMeasurement, unknown, void>({
    mutationFn: () => {
      if (!file || !fields) throw new Error('нет данных для сохранения');
      return api.saveInbody(file, date, fields, metricsJson);
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

  function setField(key: keyof InbodyFields, raw: string) {
    setFields((prev) => {
      if (!prev) return prev;
      if (raw.trim() === '') return { ...prev, [key]: null };
      const n = Number(raw);
      return Number.isFinite(n) ? { ...prev, [key]: n } : prev;
    });
    save.reset(); // правка после сохранения — снова даём сохранить
  }

  const metricsEntries = Object.entries(metricsJson);

  return (
    <section aria-labelledby="inbody-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Ингест InBody
        </p>
        <h1 id="inbody-heading" className="mt-3 text-display">
          Скрин InBody
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Загрузите скрин состава тела (InBody или умные весы) — распознаем ключевые показатели и
          покажем рядом с картинкой. Сверьте, при необходимости поправьте значения и нажмите
          «Сохранить»: повторная загрузка того же дня заменит запись.
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
                alt="Загруженный скрин InBody"
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
              Здесь появятся распознанные показатели — сверьте их с картинкой и поправьте при
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
                        inputMode="decimal"
                        step="0.1"
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

              {metricsEntries.length > 0 && (
                <div className="flex flex-col gap-2 border-t border-line pt-4">
                  <h3 className="text-sm font-medium text-muted">Прочие показатели</h3>
                  <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
                    {metricsEntries.map(([key, value]) => (
                      <div key={key} className="flex items-baseline justify-between gap-2 text-sm">
                        <dt className="text-muted">{key}</dt>
                        <dd className="font-medium tabular-nums text-fg">{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              <div className="mt-1 flex flex-col gap-3 border-t border-line pt-5">
                {save.isError && (
                  <p role="alert" className="text-sm font-medium text-amber">
                    {errorText(save.error)}
                  </p>
                )}
                {save.isSuccess && (
                  <p role="status" className="text-sm font-medium text-accent">
                    Сохранено за {dateFmt.format(parseLocalDate(save.data.date))}
                    {save.data.weight_kg != null && ` · ${save.data.weight_kg} кг`}
                    {save.data.body_fat_pct != null && `, ${save.data.body_fat_pct}% жира`}
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
