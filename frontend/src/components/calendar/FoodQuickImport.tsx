/** Лёгкий импорт еды в попапе дня: выбрал CSV FatSecret → «Сохранить» (без подробного
 *  разложения). Дата берётся из самого файла — поэтому итог показывает, за какой день записано.
 *  Минимум окошек: одна зона выбора + строка-итог. Обновление календаря — инвалидация dashboard. */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type DiaryPreview } from '../../lib/api';

const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const fmt = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
};

export function FoodQuickImport({ date, onSaved }: { date: string; onSaved?: () => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Еда — это CSV-импорт без редактируемых полей: «предзаполнение» = показать, что за день уже
  // импортировано и на сколько ккал (kcal_in за [date;date]). Новый CSV заменит день (идемпотентно).
  const existing = useQuery({
    queryKey: ['day-food', date],
    queryFn: () => api.getEnergyProgress(date, date),
    enabled: !!date,
  });
  const kcalPts = existing.data?.kcal_in ?? [];
  const existingKcal = kcalPts.length > 0 ? kcalPts[kcalPts.length - 1].value : null;

  const save = useMutation<DiaryPreview, unknown, File>({
    mutationFn: (f) => api.saveImport(f, date), // записываем на выбранный день
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['day-food', date] });
      onSaved?.();
    },
  });

  const choose = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    save.reset();
  };

  return (
    <div className="flex flex-col gap-2">
      {existingKcal != null && !save.isSuccess && (
        <p className="text-xs text-accent">
          За этот день еда уже импортирована: {Math.round(existingKcal)} ккал. Новый CSV заменит её.
        </p>
      )}
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
