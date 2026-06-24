/** Мелкие общие куски минимальных форм попапа (поля/кнопка/хелперы) — чтобы недельные и
 *  дневная формы выглядели одинаково и не дублировали код. */

import { ApiError } from '../../lib/api';

export const inputCls =
  'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent [color-scheme:dark]';

export function SaveButton({
  pending,
  success,
  disabled,
}: {
  pending: boolean;
  success: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className="mt-1 self-start rounded-full bg-accent px-5 py-2 text-sm font-semibold text-accent-ink transition-opacity duration-[var(--duration-fast)] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? 'Сохраняем…' : success ? 'Сохранено ✓' : 'Сохранить'}
    </button>
  );
}

export const errText = (e: unknown): string =>
  e instanceof ApiError ? `Не удалось сохранить (${e.status}).` : 'Не удалось сохранить.';

/** Строка → положительное число или null (пусто/мусор → null). */
export const numOrNull = (s: string | undefined): number | null => {
  const n = Number((s ?? '').trim());
  return s && Number.isFinite(n) && n > 0 ? n : null;
};
