/** Ячейка дня — квадрат, наполняемый премиум-жидкостью по 3 ежедневным категориям
 *  (еда/активность/тренировки), цвета смешиваются и переливаются (см. LiquidFill).
 *  В углах — число дня и текстовый статус «что внесено / что осталось» (Е·А·Т: яркая
 *  буква = внесено, тусклая = осталось). Полный день (3/3) светится и искрится.
 *  `draining` (слияние «Получить отчёт») сливает жидкость вниз. */

import type { DayFlags } from '../../lib/api';
import { DAILY } from '../../lib/weekly';
import { glowColor } from '../../lib/liquid';
import { LiquidFill } from './LiquidFill';
import { Sparks } from './Sparks';

const dayLabelFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function DaySquare({
  day,
  iso,
  flags,
  isToday,
  draining = false,
  onSelect,
}: {
  day: number;
  iso: string;
  flags: DayFlags | undefined;
  isToday: boolean;
  draining?: boolean;
  onSelect?: () => void;
}) {
  const active = flags ? DAILY.filter((c) => flags[c.key]) : [];
  const activeKeys = active.map((c) => c.key);
  const count = active.length;
  const isComplete = count === DAILY.length;
  const level = draining ? 0 : count / DAILY.length;

  const summary = active.length
    ? active.map((c) => c.label.toLowerCase()).join(', ')
    : 'нет данных';
  const dateLabel = cap(dayLabelFmt.format(new Date(iso + 'T00:00:00')));

  return (
    <div
      role="gridcell"
      data-testid={`day-${iso}`}
      aria-label={`${dateLabel}: ${summary}. Нажмите, чтобы внести или изменить`}
      aria-current={isToday ? 'date' : undefined}
      title={`${dateLabel} — ${summary}`}
      tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect}
      onKeyDown={
        onSelect
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
      className={`relative aspect-square overflow-hidden rounded-xl border transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset focus-visible:outline-none ${
        onSelect ? 'cursor-pointer hover:border-accent/60' : ''
      } ${isToday ? 'border-accent' : count > 0 ? 'border-line' : 'border-line/50'}`}
      style={isComplete ? { boxShadow: `0 0 12px -2px ${glowColor(false)}` } : undefined}
    >
      {count > 0 && <LiquidFill level={level} activeKeys={activeKeys} />}

      <span
        className={`pointer-events-none absolute top-0.5 left-1 z-10 text-[0.62rem] font-semibold tabular-nums sm:text-xs ${
          isToday ? 'text-accent' : count > 0 ? 'text-white' : 'text-muted'
        }`}
        style={count > 0 && !isToday ? { textShadow: '0 1px 2px rgb(0 0 0 / 0.55)' } : undefined}
      >
        {day}
      </span>

      {/* Текстовый статус: что внесено (яркая буква) / что осталось (тусклая) */}
      <span className="pointer-events-none absolute right-1 bottom-0.5 z-10 flex gap-0.5">
        {DAILY.map((c) => {
          const on = !!flags?.[c.key];
          return (
            <span
              key={c.key}
              title={`${c.label}: ${on ? 'внесено' : 'осталось'}`}
              className={`text-[0.5rem] leading-none font-bold sm:text-[0.6rem] ${
                on ? 'text-white' : 'text-muted/40'
              }`}
              style={on ? { textShadow: '0 1px 2px rgb(0 0 0 / 0.6)' } : undefined}
            >
              {c.label[0]}
            </span>
          );
        })}
      </span>

      {isComplete && <Sparks count={8} spread={14} baseDur={1300} />}
    </div>
  );
}
