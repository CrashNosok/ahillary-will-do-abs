/** Математика «недели стаканов» для календаря (чистые функции, без React).
 *
 *  Дневной стакан наполняют 3 ежедневные категории (еда/активность/тренировки).
 *  Недельную «общую чашу» — 3 недельные (вес/замеры/фото), достаточно одного раза за неделю.
 *  Медаль/итоговый цвет недели выводятся из доли заполнения `overall` (0..1):
 *  чем полнее — тем насыщеннее цвет, ярче свечение и больше искр; ровно 1.0 → mystery-ball.
 */

import type { DayFlags } from './api';
import { keyColor } from './liquid';

/** Ячейка месяца: день с ISO-датой либо `null` (паддинг под смещение/хвост недели). */
export type MonthCell = { day: number; iso: string } | null;

/** Ежедневные категории дневной ячейки: ключ флага → ярлык + представительный премиум-цвет
 *  (средний тон спектра из liquid.ts). Порядок задаёт слои снизу-вверх: еда→активность→тренировки. */
export const DAILY = [
  { key: 'has_food', label: 'Еда', color: keyColor('has_food') },
  { key: 'has_activity', label: 'Активность', color: keyColor('has_activity') },
  { key: 'has_training', label: 'Тренировки', color: keyColor('has_training') },
] as const satisfies ReadonlyArray<{ key: keyof DayFlags; label: string; color: string }>;

/** Недельные категории «общей чаши»: достаточно одной записи за неделю. */
export const WEEKLY = [
  { key: 'has_weight', label: 'Вес', color: keyColor('has_weight') },
  { key: 'has_body', label: 'Замеры', color: keyColor('has_body') },
  { key: 'has_photo', label: 'Фото', color: keyColor('has_photo') },
] as const satisfies ReadonlyArray<{ key: keyof DayFlags; label: string; color: string }>;

/** Доля заполнения одного дня: число внесённых ежедневных категорий / 3 (0..1). */
export function dayFill(flags: DayFlags | undefined): number {
  if (!flags) return 0;
  const n = DAILY.reduce((s, c) => s + (flags[c.key] ? 1 : 0), 0);
  return n / DAILY.length;
}

/** Режет плоский массив ячеек месяца на недели по 7; хвост добивает паддингом `pad`. */
export function chunkWeeks<T>(cells: T[], pad: T): T[][] {
  const weeks: T[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  const last = weeks[weeks.length - 1];
  if (last) while (last.length < 7) last.push(pad);
  return weeks;
}

export type WeekFill = {
  /** Доля заполненных ежедневных слотов (Σ категорий по дням / реальные_дни×3). */
  daily: number;
  /** Доля недельных категорий (вес/замеры/фото есть хоть раз за неделю) / 3. */
  weekly: number;
  /** Итог недели 0..1 — все слоты (дневные + недельные) вместе. */
  overall: number;
  /** Сколько реальных дней в неделе попало в этот месяц (для краевых недель < 7). */
  realDays: number;
};

/** Считает заполнение недели по флагам её реальных дней (null-ячейки не передавать).
 *  ponytail: знаменатель — по реальным дням месяца в неделе; краевые недели у границы
 *  месяца не видят дни соседнего месяца (их нет в выборке /dashboard). Если понадобится
 *  «честная» 7-дневная неделя на стыке — догружать соседние дни и считать по ним. */
export function weekFill(days: DayFlags[]): WeekFill {
  const realDays = days.length;
  const dailyFilled = days.reduce(
    (acc, d) => acc + DAILY.reduce((s, c) => s + (d[c.key] ? 1 : 0), 0),
    0,
  );
  const dailyTotal = Math.max(1, realDays) * DAILY.length;
  const weeklyFilled = WEEKLY.reduce((s, c) => s + (days.some((d) => d[c.key]) ? 1 : 0), 0);

  return {
    daily: dailyFilled / dailyTotal,
    weekly: weeklyFilled / WEEKLY.length,
    overall: (dailyFilled + weeklyFilled) / (dailyTotal + WEEKLY.length),
    realDays,
  };
}
