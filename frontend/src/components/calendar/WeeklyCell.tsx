/** Недельная ячейка (8-я колонка перед медалью): «раз в неделю» — Вес/Замеры/Фото.
 *  Наполняется премиум-жидкостью по 3 недельным категориям (как день, но за неделю); пунктирная
 *  рамка отличает её от дней. В углу — статус В·З·Ф (внесено/осталось). Клик открывает редактор
 *  недельных данных. `draining` сливает её в общую чашу при «Получить отчёт».
 *
 *  Бонус за полные замеры (Вес И Замеры за неделю — Фото опционально): усиленный залп искр +
 *  доп. фуксиево-аметистовая подсветка (measureGlow), которая складывается с зелёным glow полной
 *  недели. Так замеры поощряются отдельно от Фото; полная неделя 3/3 всегда содержит полные
 *  замеры, поэтому получает и зелёный glow, и бонус-подсветку. */

import type { DayFlags } from '../../lib/api';
import { WEEKLY } from '../../lib/weekly';
import { fullGradient, glowColor, measureGlow, WEEK_FULL_FILL } from '../../lib/liquid';
import { LiquidFill } from './LiquidFill';
import { Sparks } from './Sparks';

type WeeklyFlags = Pick<DayFlags, 'has_weight' | 'has_body' | 'has_photo'>;

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
  // Полные замеры за неделю = есть и Вес, и Замеры (Фото опционально). Это бонус-условие.
  const hasMeasurements = weeklyFlags.has_weight && weeklyFlags.has_body;
  const level = draining ? 0 : count / WEEKLY.length;

  // Складываем тени: зелёный glow полной недели (3/3) + бонус-подсветка за полные замеры. Обе опц.
  const boxShadow = [
    isFull ? `0 0 12px -2px ${glowColor(false)}` : '',
    hasMeasurements ? measureGlow() : '',
  ]
    .filter(Boolean)
    .join(', ');
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
      style={boxShadow ? { boxShadow } : undefined}
    >
      {count > 0 && (
        <LiquidFill
          level={level}
          activeKeys={activeKeys}
          fillColor={isFull ? WEEK_FULL_FILL : fullGradient(activeKeys)}
        />
      )}

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

      {/* Искры — ТОЛЬКО на полной неделе (3/3). Частичная (1/3, 2/3) остаётся раздельными цветами
          без искр. Reduced-motion гасит все .sparkle глобально (см. index.css). */}
      {isFull && <Sparks count={10} spread={16} baseDur={900} size={6} />}
    </div>
  );
}
