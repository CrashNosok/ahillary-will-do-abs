/** Дневная «Активность»: ручной ввод метрик дня (как на скрине Welltory), без даты —
 *  пишется на выбранный день. Обязательны: Всего ккал, Акт. ккал, Шаги; остальное по желанию,
 *  но в форме. Дополнительно: «Распознать со скрина» — vision заполнит поля (если ключ valid),
 *  затем правишь и «Сохранить» (ручной upsert, без файла). */

import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type ActivityFields } from '../../lib/api';
import { inputCls, SaveButton, errText, numOrNull } from './formKit';

const A_FIELDS: { key: keyof ActivityFields; label: string; req?: boolean }[] = [
  { key: 'total_kcal', label: 'Всего ккал', req: true },
  { key: 'active_kcal', label: 'Акт. ккал', req: true },
  { key: 'steps', label: 'Шаги', req: true },
  { key: 'moving_min', label: 'В движении, мин' },
  { key: 'idle_min', label: 'Без движ., мин' },
  { key: 'warmup_min', label: 'Разминка, мин' },
  { key: 'active_met', label: 'Акт. МЕТ' },
  { key: 'intense_met', label: 'Инт. МЕТ' },
];
const REQUIRED: (keyof ActivityFields)[] = ['total_kcal', 'active_kcal', 'steps'];

export function ActivityForm({ date }: { date: string }) {
  const qc = useQueryClient();
  const [vals, setVals] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  const fields = (): ActivityFields => ({
    total_kcal: numOrNull(vals.total_kcal),
    active_kcal: numOrNull(vals.active_kcal),
    steps: numOrNull(vals.steps),
    moving_min: numOrNull(vals.moving_min),
    idle_min: numOrNull(vals.idle_min),
    warmup_min: numOrNull(vals.warmup_min),
    active_met: numOrNull(vals.active_met),
    intense_met: numOrNull(vals.intense_met),
  });

  const recognize = useMutation({
    mutationFn: (file: File) => api.previewActivity(file, date),
    onSuccess: (p) => {
      const next: Record<string, string> = {};
      for (const f of A_FIELDS) next[f.key] = p[f.key] != null ? String(p[f.key]) : '';
      setVals(next);
      setErr(null);
    },
  });

  const save = useMutation({
    mutationFn: () => api.saveActivityManual(date, fields()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const f = fields();
    const missing = REQUIRED.filter((k) => f[k] == null);
    if (missing.length) {
      const labels = A_FIELDS.filter((x) => missing.includes(x.key)).map((x) => x.label);
      setErr(`Обязательные поля: ${labels.join(', ')}.`);
      return;
    }
    setErr(null);
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="cursor-pointer self-start rounded-full border border-line px-3 py-1.5 text-xs font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50">
        {recognize.isPending ? 'Распознаём…' : 'Распознать со скрина'}
        <input
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) recognize.mutate(file);
          }}
        />
      </label>
      {recognize.isError && (
        <p className="text-xs font-medium text-amber">
          {recognize.error instanceof ApiError
            ? recognize.error.message
            : 'Не удалось распознать скрин.'}{' '}
          Заполните вручную.
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {A_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            <span className="text-xs text-muted">
              {f.label}
              {f.req && <span className="text-accent"> *</span>}
            </span>
            <input
              className={`${inputCls} tabular-nums`}
              type="number"
              inputMode="numeric"
              value={vals[f.key] ?? ''}
              onChange={(e) => {
                setVals((v) => ({ ...v, [f.key]: e.target.value }));
                setErr(null);
                save.reset();
              }}
              placeholder="—"
            />
          </label>
        ))}
      </div>

      <p className="text-xs text-muted">
        <span className="text-accent">*</span> — обязательно
      </p>
      {err && <p className="text-xs font-medium text-amber">{err}</p>}
      {save.isError && <p className="text-xs font-medium text-amber">{errText(save.error)}</p>}
      <SaveButton pending={save.isPending} success={save.isSuccess} />
    </form>
  );
}
