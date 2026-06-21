/** Персонаж-коуч на дашборде (S5.9): сова со спич-баблом, как у Duolingo.
 *
 *  Реплика выбирается по состоянию дня из данных GET /dashboard (та же query, что
 *  у панели «Сегодня» — общий кэш, без второго запроса). Пока данные грузятся,
 *  показываем нейтральную фразу «в процессе», чтобы блок не прыгал (без CLS) и
 *  коуч всегда был на месте. Анимация — только transform/opacity (compositor-
 *  friendly); глобальный сброс prefers-reduced-motion в index.css её гасит. */

import { daySeed, deriveMood, pickPhrase, type CoachMood } from '../lib/coach';
import { useDashboard } from '../lib/dashboard';

const pad = (n: number) => String(n).padStart(2, '0');
const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export default function Coach() {
  const todayIso = toISO(new Date());
  const { data } = useDashboard(todayIso, todayIso);

  // Нейтральная фраза «в процессе» как фолбэк на время загрузки — блок не прыгает.
  const mood: CoachMood = data ? deriveMood(data) : 'progress';
  const phrase = pickPhrase(mood, daySeed());

  return (
    <section
      aria-label="Коуч"
      data-testid="coach"
      data-mood={mood}
      className="flex items-center gap-4"
    >
      <span
        aria-hidden="true"
        className="coach-bob grid size-14 shrink-0 place-items-center rounded-full border border-accent/40 bg-panel text-3xl shadow-[0_8px_24px_-12px] shadow-accent/50"
      >
        🦉
      </span>
      <div
        key={phrase}
        className="coach-pop relative max-w-md rounded-2xl border border-line bg-surface px-4 py-3 text-fg"
      >
        {/* Хвостик бабла к сове — поворот квадрата, чисто декоративный. */}
        <span
          aria-hidden="true"
          className="absolute -left-1.5 top-1/2 size-3 -translate-y-1/2 rotate-45 border-b border-l border-line bg-surface"
        />
        <p className="relative text-sm leading-snug sm:text-base">{phrase}</p>
      </div>
    </section>
  );
}
