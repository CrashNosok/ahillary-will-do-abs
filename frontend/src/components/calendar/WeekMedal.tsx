/** Медаль недели (колонка «Итог»). Концепция — гексагональные награды (как в Apple Fitness),
 *  10 дизайнов-тиров по заполнению недели (`tierOf`). Медаль НЕ вращается сама — переворачивается
 *  на 180° при наведении мышки: лицо — бейдж, оборот — «за что» (диапазон + %). Клик по медали и
 *  кнопка «Получить отчёт» под ней открывают отчёт недели. */

import { Sparks } from './Sparks';

const HEX = 'M28 6 L72 6 L96 50 L72 94 L28 94 L4 50 Z';

type Design = { from: string; to: string; mid?: string; ring: string; glyph: string };

// 10 дизайнов: от скромного к космическому (100% — последний). Не копия Apple — своя палитра.
const MEDALS: Design[] = [
  {
    from: 'oklch(64% 0.02 256)',
    to: 'oklch(44% 0.02 256)',
    ring: 'oklch(72% 0.02 256)',
    glyph: '◦',
  },
  { from: 'oklch(74% 0.10 60)', to: 'oklch(52% 0.12 48)', ring: 'oklch(82% 0.10 70)', glyph: '✦' },
  {
    from: 'oklch(82% 0.13 195)',
    to: 'oklch(60% 0.13 200)',
    ring: 'oklch(88% 0.10 195)',
    glyph: '✧',
  },
  {
    from: 'oklch(86% 0.18 150)',
    to: 'oklch(64% 0.18 150)',
    ring: 'oklch(90% 0.14 150)',
    glyph: '★',
  },
  {
    from: 'oklch(80% 0.15 250)',
    to: 'oklch(58% 0.17 265)',
    ring: 'oklch(86% 0.12 245)',
    glyph: '✪',
  },
  { from: 'oklch(90% 0.15 95)', to: 'oklch(74% 0.16 80)', ring: 'oklch(92% 0.12 95)', glyph: '❂' },
  { from: 'oklch(82% 0.16 55)', to: 'oklch(64% 0.17 45)', ring: 'oklch(88% 0.13 55)', glyph: '✸' },
  {
    from: 'oklch(76% 0.20 350)',
    to: 'oklch(58% 0.20 350)',
    ring: 'oklch(84% 0.16 350)',
    glyph: '❉',
  },
  {
    from: 'oklch(70% 0.20 300)',
    to: 'oklch(52% 0.20 295)',
    ring: 'oklch(80% 0.16 300)',
    glyph: '✶',
  },
  {
    from: 'oklch(78% 0.24 345)',
    mid: 'oklch(72% 0.22 20)',
    to: 'oklch(88% 0.14 75)',
    ring: 'oklch(92% 0.12 80)',
    glyph: '✦',
  },
];

const tierOf = (overall: number) => (overall <= 0 ? -1 : Math.min(9, Math.floor(overall * 10)));

function MedalFront({ d, gid }: { d: Design; gid: string }) {
  return (
    <svg viewBox="0 0 100 100" className="medal-svg h-full w-full">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0%" stopColor={d.from} />
          {d.mid && <stop offset="50%" stopColor={d.mid} />}
          <stop offset="100%" stopColor={d.to} />
        </linearGradient>
        <linearGradient id={`${gid}-s`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.55" />
          <stop offset="45%" stopColor="#fff" stopOpacity="0.06" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={HEX}
        fill={`url(#${gid})`}
        stroke={d.ring}
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      <path d={HEX} fill={`url(#${gid}-s)`} />
      <path d="M30 8 L70 8 L60 30 L40 30 Z" fill="#fff" fillOpacity="0.16" />
      <text
        x="50"
        y="50"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="36"
        fontWeight="700"
        fill="#fff"
        fillOpacity="0.96"
        style={{ paintOrder: 'stroke' }}
        stroke="rgb(0 0 0 / 0.18)"
        strokeWidth="0.6"
      >
        {d.glyph}
      </text>
    </svg>
  );
}

function MedalBack({ short, pct, perfect }: { short: string; pct: number; perfect: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className="medal-svg h-full w-full">
      <path
        d={HEX}
        fill="oklch(26% 0.02 256)"
        stroke="oklch(46% 0.02 256)"
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      <text x="50" y="34" textAnchor="middle" fontSize="11" fill="var(--color-muted)">
        {short}
      </text>
      <text x="50" y="62" textAnchor="middle" fontSize="26" fontWeight="700" fill="var(--color-fg)">
        {pct}%
      </text>
      <text x="50" y="84" textAnchor="middle" fontSize="11" fill="oklch(85% 0.18 90)">
        {perfect ? 'идеально ✦' : 'итог'}
      </text>
    </svg>
  );
}

function LockedHex() {
  return (
    <svg viewBox="0 0 100 100" className="h-full w-full opacity-40">
      <path
        d={HEX}
        fill="none"
        stroke="var(--color-line)"
        strokeWidth="3"
        strokeLinejoin="round"
        strokeDasharray="5 5"
      />
    </svg>
  );
}

export function WeekMedal({
  overall,
  ended,
  short,
  id,
  onOpenReport,
}: {
  overall: number;
  ended: boolean;
  short: string;
  id: string;
  onOpenReport: () => void;
}) {
  const tier = tierOf(overall);
  const locked = tier < 0;
  const pct = Math.round(overall * 100);
  // Заработана (завершившаяся неделя с данными) — только для праздничных искр на высоком тире;
  // вращения больше нет, переворот — на ховере (см. .medal-flip:hover в index.css).
  const earned = ended && !locked;
  const gid = `med-${id}`;

  return (
    <div className="flex flex-col items-center gap-1 self-start pt-1">
      <button
        type="button"
        onClick={onOpenReport}
        aria-label={
          locked ? 'Нет данных за неделю' : `Медаль недели ${pct}%. Открыть отчёт за неделю`
        }
        className="medal-flip relative aspect-square w-full max-w-[58px] cursor-pointer rounded-xl focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
      >
        <span className="medal-spin">
          <span className="medal-face">
            {locked ? <LockedHex /> : <MedalFront d={MEDALS[tier]} gid={gid} />}
          </span>
          <span className="medal-face medal-back">
            <MedalBack short={short} pct={pct} perfect={overall >= 1} />
          </span>
        </span>
        {earned && tier >= 7 && <Sparks count={8} spread={18} baseDur={1000} size={6} />}
      </button>

      {!locked && (
        <button
          type="button"
          onClick={onOpenReport}
          className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-center text-[0.58rem] leading-tight font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:bg-accent/20"
        >
          Получить отчёт
        </button>
      )}
    </div>
  );
}
