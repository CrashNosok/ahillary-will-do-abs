/** Недельная ячейка (8-я колонка перед медалью): «раз в неделю» — Вес/Замеры/Фото.
 *  Наполняется премиум-жидкостью по 3 недельным категориям (как день, но за неделю); пунктирная
 *  рамка отличает её от дней. В углу — статус В·З·Ф (внесено/осталось). Клик открывает редактор
 *  недельных данных. `draining` сливает её в общую чашу при «Получить отчёт». */

import type { DayFlags } from '../../lib/api';
import { WEEKLY } from '../../lib/weekly';
import { glowColor } from '../../lib/liquid';
import { LiquidFill } from './LiquidFill';

type WeeklyFlags = Pick<DayFlags, 'has_weight' | 'has_body' | 'has_photo'>;

// Искры полной недели (все 3 категории) — вспыхивают и разлетаются.
const SPARKS = [
  { x: 24, y: 30, dx: -11, dy: -12, dur: 1300, delay: 0 },
  { x: 62, y: 24, dx: 12, dy: -8, dur: 1100, delay: 240 },
  { x: 44, y: 50, dx: 3, dy: 14, dur: 1500, delay: 480 },
  { x: 76, y: 46, dx: 13, dy: 6, dur: 1150, delay: 140 },
  { x: 30, y: 68, dx: -12, dy: 10, dur: 1450, delay: 660 },
  { x: 60, y: 70, dx: 9, dy: 12, dur: 1250, delay: 360 },
];

export function WeeklyCell({
  weeklyFlags,
  draining = false,
  isCurrentWeek = false,
  onSelect,
}: {
  weeklyFlags: WeeklyFlags;
  draining?: boolean;
  isCurrentWeek?: boolean;
  onSelect?: () => void;
}) {
  const active = WEEKLY.filter((c) => weeklyFlags[c.key]);
  const activeKeys = active.map((c) => c.key);
  const count = active.length;
  const isFull = count === WEEKLY.length;
  const level = draining ? 0 : count / WEEKLY.length;
  const summary = active.length
    ? active.map((c) => c.label.toLowerCase()).join(', ')
    : 'нет недельных данных';

  return (
    <div
      role="gridcell"
      aria-label={`Неделя: ${summary}. Нажмите, чтобы внести или изменить`}
      title={`Вес · Замеры · Фото — ${summary}`}
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
      className={`relative aspect-square overflow-hidden rounded-xl border border-dashed transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset focus-visible:outline-none ${
        onSelect ? 'cursor-pointer hover:border-accent/60' : ''
      } ${isCurrentWeek ? 'border-accent/70' : count > 0 ? 'border-line' : 'border-line/50'}`}
      style={isFull ? { boxShadow: `0 0 12px -2px ${glowColor(false)}` } : undefined}
    >
      {count > 0 && <LiquidFill level={level} activeKeys={activeKeys} />}

      <span className="pointer-events-none absolute top-0.5 left-1 z-10 text-[0.5rem] font-semibold uppercase tracking-wide text-muted sm:text-[0.55rem]">
        нед
      </span>

      <span className="pointer-events-none absolute right-1 bottom-0.5 z-10 flex gap-0.5">
        {WEEKLY.map((c) => {
          const on = weeklyFlags[c.key];
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

      {isFull && (
        <span className="sparkles" aria-hidden="true">
          {SPARKS.map((s, i) => (
            <span
              key={i}
              className="sparkle"
              style={
                {
                  left: `${s.x}%`,
                  top: `${s.y}%`,
                  '--dx': `${s.dx}px`,
                  '--dy': `${s.dy}px`,
                  '--dur': `${s.dur}ms`,
                  '--delay': `${s.delay}ms`,
                } as React.CSSProperties
              }
            />
          ))}
        </span>
      )}
    </div>
  );
}
