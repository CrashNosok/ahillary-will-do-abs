/** Общие хелперы форм-логгеров тренировок (S3.7/S3.8): стиль поля, дата, парсинг чисел.
 *  Вынесены из логгера силовой, чтобы кардио/скилл не дублировали те же мелочи. */

export const inputCls =
  'w-full rounded-lg border border-line bg-surface px-3 py-2 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

/** Сегодня в ISO `YYYY-MM-DD` (локальная зона) — дефолт и максимум для поля даты. */
export function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Опциональное неотрицательное число из поля: '' → null, мусор/<0/(>max) → 'invalid'. */
export function optNum(raw: string, max?: number): number | null | 'invalid' {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || (max !== undefined && n > max)) return 'invalid';
  return n;
}
