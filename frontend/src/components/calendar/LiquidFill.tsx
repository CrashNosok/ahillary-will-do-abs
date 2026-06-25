/** Анимированная «жидкость» внутри ячейки (квадрата/чаши). Заполняет снизу до `level`:
 *  - тело: премиум-градиент из спектров активных категорий (смешиваются плавно);
 *  - iridescence + sheen: два анимированных слоя-перелива (mix-blend) → «премиум, переливается»;
 *  - поверхность: две волны-пены (SMIL-сдвиг) → сразу видно, что жидкость живая.
 *  Уровень меняется через clip-path (плавный налив/слияние). Родитель clip'ает форму
 *  (overflow-hidden + border-radius). reduced-motion: волны не рендерим, CSS-анимации гасит глобал. */

import { useEffect, useState } from 'react';
import { liquidGradient } from '../../lib/liquid';

const REDUCED =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Волна тайлится каждые 25 ед.; строим -25..125, сдвиг на -25 бесшовен. Закрытая (с заливкой).
function wave(baseline: number, amp: number): string {
  const half = 12.5;
  let d = `M -25 ${baseline}`;
  let x = -25;
  let up = true;
  while (x < 125) {
    d += ` q ${half / 2} ${(up ? -1 : 1) * amp} ${half} 0`;
    x += half;
    up = !up;
  }
  return `${d} L ${x} 8 L -25 8 Z`;
}
// Та же кривая, но открытая — для тонкого блика-мениска по гребню.
function waveLine(baseline: number, amp: number): string {
  const half = 12.5;
  let d = `M -25 ${baseline}`;
  let x = -25;
  let up = true;
  while (x < 125) {
    d += ` q ${half / 2} ${(up ? -1 : 1) * amp} ${half} 0`;
    x += half;
    up = !up;
  }
  return d;
}

const WAVE_FRONT = wave(4, 2.2);
const WAVE_BACK = wave(3.1, 1.5);
const WAVE_LINE = waveLine(4, 2.2);

function Shift({ dur }: { dur: string }) {
  if (REDUCED) return null;
  return (
    <animateTransform
      attributeName="transform"
      type="translate"
      from="0 0"
      to="-25 0"
      dur={dur}
      repeatCount="indefinite"
    />
  );
}

export function LiquidFill({
  level,
  activeKeys,
  mystery = false,
  fillColor,
}: {
  level: number;
  activeKeys: readonly string[];
  mystery?: boolean;
  /** Готовая заливка (напр. единый премиум-градиент полного дня) — заменяет смешение категорий. */
  fillColor?: string;
}) {
  const clamped = level < 0 ? 0 : level > 1 ? 1 : level;
  // Маунт-флип: стартуем с пустого и на следующем кадре наливаем до уровня —
  // clip-path с переходом даёт «налив» (и при появлении данных, и при загрузке).
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const shown = mounted ? clamped : 0;
  const gradient = fillColor ?? liquidGradient(activeKeys, mystery);
  const inset = `inset(${(1 - shown) * 100}% 0 0 0)`;

  return (
    <div className="liquid-wrap" aria-hidden="true">
      <div
        className={`liquid-body ${mystery ? 'liquid-mystery' : ''}`}
        style={{ background: gradient, clipPath: inset }}
      />
      <div className="liquid-irid" style={{ clipPath: inset }} />
      <div className="liquid-sheen" style={{ clipPath: inset }} />
      <svg
        className="liquid-surface"
        viewBox="0 0 100 8"
        preserveAspectRatio="none"
        style={{ top: `calc(${(1 - shown) * 100}% - 6px)` }}
      >
        <path className="wave-back" d={WAVE_BACK}>
          <Shift dur="4.6s" />
        </path>
        <path className="wave-front" d={WAVE_FRONT}>
          <Shift dur="3s" />
        </path>
        <path className="wave-line" d={WAVE_LINE}>
          <Shift dur="3s" />
        </path>
      </svg>
    </div>
  );
}
