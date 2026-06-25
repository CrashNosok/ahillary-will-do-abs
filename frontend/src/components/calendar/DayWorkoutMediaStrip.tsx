/** Полоса медиа дня (M3·F12): миниатюры всех медиа тренировок за выбранный день из
 *  useDayWorkoutMedia. Клик по миниатюре открывает MediaLightbox с полной коллекцией дня.
 *  Байты медиа auth'd — сессионная cookie уходит cross-origin (5173→8000), Lax/same-site.
 *  Нерисуемые форматы (HEIC/HEVC) → fallback-иконка, как в превью формы (mediaKit). */

import { useState } from 'react';
import { workoutMediaUrl } from '../../lib/api';
import { useDayWorkoutMedia } from '../../lib/workouts';
import { MediaLightbox, type LightboxItem } from './MediaLightbox';

/** Одна миниатюра серверного медиа: пытается отрисоваться, при ошибке (HEIC/HEVC) — иконка. */
function Thumb({ src, isVideo, name, onOpen }: LightboxItem & { onOpen: () => void }) {
  const [broken, setBroken] = useState(false);
  const inner = broken ? (
    <span className="grid size-full place-items-center text-lg" title={name}>
      {isVideo ? '🎬' : '🖼️'}
    </span>
  ) : isVideo ? (
    <video src={src} className="size-full object-cover" muted onError={() => setBroken(true)} />
  ) : (
    <img src={src} alt={name} className="size-full object-cover" onError={() => setBroken(true)} />
  );
  return (
    <li className="size-16 overflow-hidden rounded-lg border border-line bg-panel">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Открыть ${name}`}
        className="block size-full cursor-zoom-in focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset focus-visible:outline-none"
      >
        {inner}
      </button>
    </li>
  );
}

export function DayWorkoutMediaStrip({ date }: { date: string }) {
  const { data } = useDayWorkoutMedia(date);
  const [at, setAt] = useState<number | null>(null);

  // Нет медиа за день — полосы нет вовсе (никакого пустого блока в строке).
  if (!data || data.length === 0) return null;

  const items: LightboxItem[] = data.map((m) => ({
    src: workoutMediaUrl(m.id),
    isVideo: m.media_type === 'video',
    name: `Медиа ${m.id}`,
  }));

  return (
    <div className="mb-3">
      <p className="mb-1 text-xs text-muted">Медиа дня</p>
      <ul className="flex flex-wrap gap-2">
        {items.map((it, i) => (
          <Thumb key={data[i].id} {...it} onOpen={() => setAt(i)} />
        ))}
      </ul>
      {at !== null && items[at] && (
        <MediaLightbox items={items} index={at} onIndexChange={setAt} onClose={() => setAt(null)} />
      )}
    </div>
  );
}
