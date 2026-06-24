/** Вкладка «Фото» (Ввод данных): загрузка фото прогресса тела + галерея.
 *  Фото просто хранится на бэке (POST /body-photos) и показывается сеткой (новые сверху).
 *  Превью до загрузки — локальный objectURL без round-trip; миниатюры из бэка грузятся
 *  прямо в <img> с сессионной cookie (same-site localhost). */

import { useEffect, useState, type DragEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, bodyPhotoUrl, type ProgressPhoto } from '../lib/api';

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
  if (error instanceof ApiError) return `Не удалось загрузить (${error.status}). ${error.message}`;
  return 'Не удалось загрузить фото. Проверьте, что сервер запущен.';
}

export default function BodyPhotosPage() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [date, setDate] = useState<string>(todayIso());

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

  const photos = useQuery<ProgressPhoto[]>({
    queryKey: ['body-photos'],
    queryFn: () => api.listBodyPhotos(),
    staleTime: 30_000,
  });

  const upload = useMutation<ProgressPhoto, unknown, void>({
    mutationFn: () => {
      if (!file) throw new Error('нет файла для загрузки');
      return api.uploadBodyPhoto(file, date);
    },
    onSuccess: () => {
      setFile(null); // превью убираем, новое фото появится в галерее
      qc.invalidateQueries({ queryKey: ['body-photos'] });
    },
  });

  function handleFile(next: File | undefined) {
    if (!next) return;
    setFile(next);
    upload.reset();
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragOver(false);
    handleFile(event.dataTransfer.files[0]);
  }

  return (
    <section aria-labelledby="photos-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Фото прогресса
        </p>
        <h1 id="photos-heading" className="mt-3 text-display">
          Фото тела
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Снимайте фото в одинаковых условиях — свет, поза, ракурс. Со временем галерея покажет
          изменения нагляднее любых цифр.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Левая колонка — выбор/превью файла */}
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
                alt="Выбранное фото прогресса"
                className="max-h-[28rem] w-auto rounded-xl border border-line object-contain"
              />
              <span className="text-sm font-medium text-accent">{file?.name}</span>
              <span className="text-xs text-muted">Нажмите, чтобы выбрать другое фото</span>
            </>
          ) : (
            <>
              <span className="font-display text-lg font-semibold">Перетащите фото сюда</span>
              <span className="text-sm text-muted">или нажмите, чтобы выбрать файл</span>
            </>
          )}
        </label>

        {/* Правая колонка — дата + загрузка */}
        <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
          <label className="flex items-center gap-2 text-sm text-muted">
            День
            <input
              type="date"
              value={date}
              max={todayIso()}
              onChange={(e) => {
                setDate(e.target.value);
                upload.reset();
              }}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-fg outline-none focus:border-accent [color-scheme:dark]"
            />
          </label>

          <p className="text-sm leading-relaxed text-muted">
            {file
              ? 'Файл выбран — нажмите «Загрузить», чтобы добавить его в галерею прогресса.'
              : 'Выберите фото слева. Несколько фото на один день — это нормально.'}
          </p>

          {upload.isError && (
            <p role="alert" className="text-sm font-medium text-amber">
              {errorText(upload.error)}
            </p>
          )}
          {upload.isSuccess && (
            <p role="status" className="text-sm font-medium text-accent">
              Фото добавлено в галерею ✓
            </p>
          )}

          <button
            type="button"
            onClick={() => upload.mutate()}
            disabled={!file || upload.isPending}
            className="self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {upload.isPending ? 'Загружаем…' : 'Загрузить'}
          </button>
        </div>
      </div>

      {/* Галерея */}
      <div className="flex flex-col gap-4">
        <h2 className="text-display">Галерея</h2>
        {photos.isPending ? (
          <p className="text-muted">Загрузка…</p>
        ) : photos.error ? (
          <p role="alert" className="text-sm font-medium text-amber">
            Не удалось загрузить галерею. Проверьте, что сервер запущен.
          </p>
        ) : !photos.data || photos.data.length === 0 ? (
          <p className="text-muted">
            Пока пусто. Первое фото — точка отсчёта: загрузите его, чтобы было с чем сравнивать.
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {photos.data.map((p) => (
              <li key={p.id} className="flex flex-col gap-2">
                <img
                  src={bodyPhotoUrl(p.id, p.uploaded_at)}
                  alt={`Фото прогресса за ${dateFmt.format(parseLocalDate(p.date))}`}
                  loading="lazy"
                  className="aspect-[3/4] w-full rounded-xl border border-line object-cover"
                />
                <span className="text-xs text-muted">{dateFmt.format(parseLocalDate(p.date))}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
