/** Лестница уровней дисциплины (M5·F22): рейтинг-ступени как восходящая лестница гекс-медалей
 *  «в духе WeekMedal». Высший ранг — сверху. Текущий уровень владельца (UserSport.current_level_id)
 *  подсвечен акцентным кольцом, свечением, пилюлей «Текущий уровень» и искрами (Sparks). Ступени
 *  ниже текущей считаются пройденными (полная медаль), выше — предстоящими (пунктирный гекс).
 *  Без текущего уровня (дисциплина не привязана) — каталог: все медали в цвете, без подсветки. */

import { Sparks } from './calendar/Sparks';
import type { SportLevel } from '../lib/api';

const HEX = 'M28 6 L72 6 L96 50 L72 94 L28 94 L4 50 Z';

type Tier = { from: string; to: string; mid?: string; ring: string };

// Палитра ступеней: от скромной к космической (как медали недели). Индекс — позиция ранга.
const TIERS: Tier[] = [
  { from: 'oklch(64% 0.02 256)', to: 'oklch(44% 0.02 256)', ring: 'oklch(72% 0.02 256)' },
  { from: 'oklch(82% 0.13 195)', to: 'oklch(60% 0.13 200)', ring: 'oklch(88% 0.10 195)' },
  { from: 'oklch(86% 0.18 150)', to: 'oklch(64% 0.18 150)', ring: 'oklch(90% 0.14 150)' },
  { from: 'oklch(80% 0.15 250)', to: 'oklch(58% 0.17 265)', ring: 'oklch(86% 0.12 245)' },
  { from: 'oklch(76% 0.20 350)', to: 'oklch(58% 0.20 350)', ring: 'oklch(84% 0.16 350)' },
  {
    from: 'oklch(78% 0.24 345)',
    mid: 'oklch(72% 0.22 20)',
    to: 'oklch(88% 0.14 75)',
    ring: 'oklch(92% 0.12 80)',
  },
];

/** Гекс-медаль ступени: либо залитый градиентом тира (пройдена/текущая), либо пунктирный
 *  контур (предстоящая, ещё не достигнута). Внутри — номер ранга. */
function LevelHex({ rank, tier, locked }: { rank: number; tier: Tier; locked: boolean }) {
  const gid = `lvl-${rank}-${tier.ring}`;
  if (locked) {
    return (
      <svg viewBox="0 0 100 100" className="h-full w-full opacity-45" aria-hidden="true">
        <path
          d={HEX}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth="3"
          strokeLinejoin="round"
          strokeDasharray="5 5"
        />
        <text
          x="50"
          y="50"
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="34"
          fontWeight="700"
          fill="var(--color-muted)"
        >
          {rank}
        </text>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 100 100" className="h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0%" stopColor={tier.from} />
          {tier.mid && <stop offset="50%" stopColor={tier.mid} />}
          <stop offset="100%" stopColor={tier.to} />
        </linearGradient>
      </defs>
      <path
        d={HEX}
        fill={`url(#${gid})`}
        stroke={tier.ring}
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      <path d="M30 8 L70 8 L60 30 L40 30 Z" fill="#fff" fillOpacity="0.16" />
      <text
        x="50"
        y="50"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="34"
        fontWeight="700"
        fill="#fff"
        fillOpacity="0.96"
        style={{ paintOrder: 'stroke' }}
        stroke="rgb(0 0 0 / 0.18)"
        strokeWidth="0.6"
      >
        {rank}
      </text>
    </svg>
  );
}

export default function LevelLadder({
  levels,
  currentLevelId,
}: {
  levels: SportLevel[];
  currentLevelId: number | null;
}) {
  // Сверху — высший ранг (лестница, на которую взбираешься). Копия массива, исходный не трогаем.
  const ordered = [...levels].sort((a, b) => b.rank - a.rank);
  const maxRank = ordered.length ? ordered[0].rank : 1;
  const current = levels.find((l) => l.id === currentLevelId) ?? null;
  const currentRank = current?.rank ?? null;

  // Возвращаем сами ступени-<li> — рендерятся внутри <ul> секции «Ступени» (SportDetailPage),
  // поэтому свой список-обёртку тут не заводим (минимальный диф, без вложенных списков).
  return (
    <>
      {ordered.map((lvl) => {
        const isCurrent = lvl.id === currentLevelId;
        // Предстоящая ступень: текущий уровень известен и этот ранг выше него (ещё не достигнут).
        const upcoming = currentRank != null && lvl.rank > currentRank;
        const pos = maxRank > 1 ? (lvl.rank - 1) / (maxRank - 1) : 1;
        const tier = TIERS[Math.round(pos * (TIERS.length - 1))];

        return (
          <li
            key={lvl.id}
            aria-current={isCurrent ? 'step' : undefined}
            className={`relative flex items-start gap-4 rounded-2xl border p-3 transition-colors ${
              isCurrent
                ? 'border-accent bg-accent/10 shadow-[0_0_24px_-6px_var(--color-accent)]'
                : 'border-transparent'
            }`}
          >
            <div className="relative h-11 w-11 shrink-0">
              <LevelHex rank={lvl.rank} tier={tier} locked={upcoming} />
              {isCurrent && <Sparks count={8} spread={16} baseDur={1000} size={5} />}
            </div>

            <div className="flex min-w-0 flex-col gap-0.5 pt-0.5">
              <span className="flex flex-wrap items-center gap-2">
                <span className={`font-medium ${upcoming ? 'text-muted' : ''}`}>{lvl.label}</span>
                <span className="text-sm text-muted">· {lvl.code}</span>
                {isCurrent && (
                  <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-accent-ink">
                    Текущий уровень
                  </span>
                )}
              </span>
              {lvl.description && <span className="text-sm text-muted">{lvl.description}</span>}
            </div>
          </li>
        );
      })}
    </>
  );
}
