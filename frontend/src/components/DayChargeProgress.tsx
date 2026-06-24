/** «Заряд дня» (Ввод данных): мотивирующая анимация заполнения за сегодня.
 *
 *  Сегментное кольцо — по дуге на каждый из 4 дневных источников (еда/активность/тренировки/
 *  замеры, флаги из GET /dashboard). Заполненные дуги «вкатываются» свипом (transition по
 *  stroke-dasharray), пустые мягко пульсируют-приглашают (.charge-invite). В центре — процент,
 *  считающийся count-up'ом от 0. Под кольцом — мотивирующая фраза по уровню и чипы категорий:
 *  тап по чипу уводит на нужную вкладку (один шаг от «чего не хватает» к «вношу»). На 100% —
 *  празднич. свечение кольца. Всё на transform/opacity/filter; reduced-motion гасит сверху. */

import { useEffect, useState } from 'react';
import { type DayFlags } from '../lib/api';
import { useDashboard } from '../lib/dashboard';

/** 4 дневные категории = 4 дуги. Флаг и цвет — те же, что у кольца дашборда; tab — id вкладки. */
const CATS = [
  { flag: 'has_food', label: 'Еда', color: 'var(--color-cat-food)', tab: 'food' },
  {
    flag: 'has_activity',
    label: 'Активность',
    color: 'var(--color-cat-activity)',
    tab: 'activity',
  },
  {
    flag: 'has_training',
    label: 'Тренировки',
    color: 'var(--color-cat-training)',
    tab: 'training',
  },
  {
    flag: 'has_measurement',
    label: 'Замеры',
    color: 'var(--color-cat-measurement)',
    tab: 'measurements',
  },
] as const satisfies ReadonlyArray<{
  flag: keyof DayFlags;
  label: string;
  color: string;
  tab: string;
}>;

const TOTAL = CATS.length;

// — Геометрия кольца —
const SIZE = 168;
const STROKE = 16;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;
const SEG = C / TOTAL; // длина четверти окружности
const GAP = 20; // зазор между дугами (px по окружности) — с запасом под круглые торцы
const ARC = SEG - GAP; // видимая длина дуги одного сегмента
const STAGGER_MS = 120; // задержка свипа между сегментами

/** Мотивирующая фраза + признак празднования по доле заполненных источников.
 *  Чистая функция (бакетинг по %): 0% → пусто, 1–49% → начало, 50–99% → почти, 100% → праздник.
 *  Экспортируется для проверки границ (в проекте нет тест-раннера — гейт = tsc+prettier). */
export function completionPhrase(
  filled: number,
  total: number,
): { phrase: string; celebrate: boolean } {
  const pct = total > 0 ? (filled / total) * 100 : 0;
  if (pct >= 100) return { phrase: 'Идеальный день! Все данные на месте 🔥', celebrate: true };
  if (pct >= 50) return { phrase: 'Почти идеально — осталось чуть-чуть.', celebrate: false };
  if (pct > 0)
    return { phrase: 'Хорошее начало. Ещё пара шагов до полного дня.', celebrate: false };
  return {
    phrase: 'Пустой день. Внеси хотя бы один приём пищи — и лёд тронется.',
    celebrate: false,
  };
}

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  );
}

/** Анимированный счётчик 0→target (ease-out) на requestAnimationFrame. reduced-motion → сразу финал. */
function useCountUp(target: number, durationMs = 700): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const tick = (ts: number) => {
      if (start === null) start = ts;
      const t = Math.min(1, (ts - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);
  return value;
}

interface DayChargeProgressProps {
  /** Переход на вкладку по тапу на чип категории. */
  onPick: (tab: string) => void;
}

export default function DayChargeProgress({ onPick }: DayChargeProgressProps) {
  const today = todayIso();
  const { data, error } = useDashboard(today, today);
  const flags = data?.days[0];

  const filled = CATS.filter((c) => Boolean(flags?.[c.flag])).length;
  const pct = Math.round((filled / TOTAL) * 100);
  const shown = useCountUp(pct);
  const { phrase, celebrate } = completionPhrase(filled, TOTAL);

  // Свип заполненных дуг: на маунте флипаем mounted → stroke-dasharray анимируется 0 → ARC.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div className="flex flex-col items-center gap-6 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6 sm:flex-row sm:gap-8">
      <div
        className="relative grid shrink-0 place-items-center"
        style={{ width: SIZE, height: SIZE }}
      >
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label={`Заполнено источников за сегодня: ${filled} из ${TOTAL}`}
          className={celebrate ? 'charge-celebrate' : undefined}
        >
          {/* Трек: тусклые дуги-«места». Пустые пульсируют-приглашают. */}
          {CATS.map((c, i) => {
            const on = Boolean(flags?.[c.flag]);
            return (
              <circle
                key={`track-${c.flag}`}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={R}
                fill="none"
                stroke="var(--color-line)"
                strokeWidth={STROKE}
                strokeLinecap="round"
                strokeDasharray={`${ARC} ${C - ARC}`}
                strokeDashoffset={-i * SEG}
                transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
                className={on ? undefined : 'charge-invite'}
                style={on ? undefined : { animationDelay: `${i * STAGGER_MS}ms` }}
              />
            );
          })}
          {/* Заполнение: цветные дуги поверх трека, вкатываются свипом по stroke-dasharray. */}
          {CATS.map((c, i) => {
            if (!Boolean(flags?.[c.flag])) return null;
            return (
              <circle
                key={`fill-${c.flag}`}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={R}
                fill="none"
                stroke={c.color}
                strokeWidth={STROKE}
                strokeLinecap="round"
                strokeDasharray={mounted ? `${ARC} ${C - ARC}` : `0 ${C}`}
                strokeDashoffset={-i * SEG}
                transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
                style={{
                  transition: 'stroke-dasharray var(--duration-normal) var(--ease-out-expo)',
                  transitionDelay: `${i * STAGGER_MS}ms`,
                }}
              />
            );
          })}
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="font-display text-4xl font-semibold leading-none tabular-nums">
            {shown}
            <span className="text-2xl text-muted">%</span>
          </span>
          <span className="mt-1 text-xs uppercase tracking-wide text-muted">данные за сегодня</span>
        </div>
      </div>

      <div className="flex w-full flex-col items-center gap-4 text-center sm:flex-1 sm:items-start sm:text-left">
        <div>
          <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
            Заряд дня
          </p>
          <p className="mt-2 text-lg leading-relaxed text-fg">{phrase}</p>
          {error && (
            <p className="mt-1 text-sm text-muted">
              Не удалось обновить статус дня — проверьте, что сервер запущен.
            </p>
          )}
        </div>

        <ul className="flex flex-wrap justify-center gap-2 sm:justify-start">
          {CATS.map((c) => {
            const on = Boolean(flags?.[c.flag]);
            return (
              <li key={c.flag}>
                <button
                  type="button"
                  onClick={() => onPick(c.tab)}
                  aria-label={
                    on
                      ? `${c.label}: внесено, открыть`
                      : `${c.label}: не внесено, открыть и заполнить`
                  }
                  className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
                    on
                      ? 'border-line bg-panel text-fg hover:border-accent/50'
                      : 'border-dashed border-line text-muted hover:border-accent/50 hover:text-fg'
                  }`}
                >
                  <span
                    className="size-2.5 rounded-full"
                    style={{ backgroundColor: on ? c.color : 'var(--color-line)' }}
                    aria-hidden="true"
                  />
                  {c.label}
                  <span aria-hidden="true" className="text-muted">
                    {on ? '✓' : '+'}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
