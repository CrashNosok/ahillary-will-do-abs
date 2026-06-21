/** Классификация качества дня (S2.9): хороший / плохой / неполный.
 *
 *  Хороший день = дефицит достигнут И лог полный. «Лог полный» — за день есть и
 *  приход, и расход калорий, поэтому в /progress/energy у дня есть точка `deficit`
 *  (бэкенд кладёт её только для полных дней). «Дефицит достигнут» — знак как на
 *  графике дефицита (S2.8): значение > 0 значит «потрачено больше съеденного».
 *  Иначе день — плохой (лог полный, но дефицита нет) или неполный (нет одного из
 *  источников за день). */

import type { EnergyProgress, SeriesPoint } from './api';

export type DayQuality = 'good' | 'bad' | 'incomplete';

export type DayClass = {
  date: string; // ISO YYYY-MM-DD
  quality: DayQuality;
  deficit: number | null; // ккал/день; null — лог неполный (точки дефицита нет)
};

function toMap(points: SeriesPoint[]): Map<string, number> {
  return new Map(points.map((p) => [p.date, p.value]));
}

/** Классифицировать каждый залогированный день периода (есть приход ИЛИ расход).
 *  День с точкой дефицита — полный: > 0 → хороший, иначе → плохой; без точки —
 *  неполный. Дни без единой записи не попадают в список (нечего подсвечивать). */
export function classifyDays(energy: EnergyProgress): DayClass[] {
  const deficit = toMap(energy.deficit);
  const loggedDates = new Set<string>([
    ...energy.kcal_in.map((p) => p.date),
    ...energy.kcal_out.map((p) => p.date),
  ]);

  return [...loggedDates].sort().map((date) => {
    const value = deficit.get(date);
    if (value === undefined) return { date, quality: 'incomplete', deficit: null };
    return { date, quality: value > 0 ? 'good' : 'bad', deficit: value };
  });
}

/** Счётчики по категориям — для легенды и aria-описания. */
export function countByQuality(days: DayClass[]): Record<DayQuality, number> {
  const acc: Record<DayQuality, number> = { good: 0, bad: 0, incomplete: 0 };
  for (const d of days) acc[d.quality] += 1;
  return acc;
}
