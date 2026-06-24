/** Лёгкий импорт еды в попапе дня: выбрал CSV FatSecret → «Сохранить» (без подробного
 *  разложения). Дата берётся из самого файла — поэтому итог показывает, за какой день записано.
 *  Минимум окошек: одна зона выбора + строка-итог. Обновление календаря — инвалидация dashboard. */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type DiaryPreview } from '../../lib/api';

const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const fmt = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
};

export function FoodQuickImport({ date }: { date: string }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const save = useMutation<DiaryPreview, unknown, File>({
    mutationFn: (f) => api.saveImport(f, date), // записываем на выбранный день
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });

  const choose = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    save.reset();
  };

  return (
    <div className="flex flex-col gap-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          choose(e.dataTransfer.files[0]);
        }}
        className={`flex cursor-pointer items-center justify-center rounded-xl border border-dashed px-3 py-3 text-center text-sm transition-colors duration-[var(--duration-fast)] ${
          dragOver ? 'border-accent bg-accent/5' : 'border-line hover:border-accent/50'
        }`}
      >
        <input
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => choose(e.target.files?.[0])}
        />
        <span className="truncate text-muted">
          {file ? file.name : 'Перетащите CSV FatSecret или нажмите'}
        </span>
      </label>

      {save.isSuccess ? (
        <p role="status" className="text-sm font-medium text-accent">
          Сохранено за {fmt(save.data.date)} · {save.data.product_count} прод. ·{' '}
          {Math.round(save.data.totals.kcal)} ккал
        </p>
      ) : file ? (
        <button
          type="button"
          onClick={() => save.mutate(file)}
          disabled={save.isPending}
          className="self-start rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-ink transition-opacity duration-[var(--duration-fast)] disabled:opacity-60"
        >
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </button>
      ) : (
        <span className="text-xs text-muted">Дата записи берётся из файла</span>
      )}

      {save.isError && (
        <p role="alert" className="text-sm font-medium text-amber">
          {save.error instanceof ApiError
            ? `Не удалось (${save.error.status}). ${save.error.message}`
            : 'Не удалось обработать файл.'}
        </p>
      )}
    </div>
  );
}
