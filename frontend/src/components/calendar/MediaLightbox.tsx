/** Лайтбокс просмотра прикреплённых медиа (фото/видео) поверх формы. Открывается кликом по превью
 *  (MediaThumb). Видео — controls + playsInline, БЕЗ autoplay (телефон не должен орать при открытии).
 *  prev/next листают коллекцию (клавиши ←/→), Escape закрывает, фон заблокирован useScrollLock.
 *  Нерисуемые форматы (HEIC/HEVC) → fallback-иконка + «Скачать» оригинала. z выше попапа дня (z-50). */

import { useEffect, useRef, useState } from 'react';
import { useScrollLock } from '../../lib/useScrollLock';

export interface LightboxItem {
  src: string; // objectURL превью или URL медиа на бэкенде
  isVideo: boolean;
  name: string; // для alt, имени скачивания и подписи fallback
}

export function MediaLightbox({
  items,
  index,
  onIndexChange,
  onClose,
}: {
  items: LightboxItem[];
  index: number;
  onIndexChange: (i: number) => void;
  onClose: () => void;
}) {
  const [broken, setBroken] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  useScrollLock();

  const item = items[index];
  const hasPrev = index > 0;
  const hasNext = index < items.length - 1;
  const many = items.length > 1;

  // Сброс fallback при смене кадра: новый src должен попытаться отрисоваться заново.
  useEffect(() => setBroken(false), [index]);

  // Фокус в модалку — чтобы Escape/стрелки ловились и контекст ушёл с фона.
  useEffect(() => closeRef.current?.focus(), []);

  useEffect(() => {
    // capture-фаза: ловим раньше слушателей-предков (попап дня тоже слушает Escape на window).
    // stopPropagation на обработанных клавишах — чтобы один Escape не закрыл заодно попап под нами
    // (иначе оба размонтируются разом и useScrollLock протечёт: overflow застрянет в hidden).
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      // Стрелки отдаём встроенным контролам видео (перемотка), когда фокус на нём.
      if (document.activeElement?.tagName === 'VIDEO') return;
      if (e.key === 'ArrowLeft' && index > 0) {
        e.stopPropagation();
        onIndexChange(index - 1);
      } else if (e.key === 'ArrowRight' && index < items.length - 1) {
        e.stopPropagation();
        onIndexChange(index + 1);
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [index, items.length, onClose, onIndexChange]);

  if (!item) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col bg-ink/90 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Просмотр медиа: ${item.name}`}
      onClick={onClose}
    >
      {/* Тулбар: имя · счётчик · скачать · закрыть. */}
      <div
        className="flex items-center justify-between gap-3 text-sm text-white"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="min-w-0 truncate" title={item.name}>
          {item.name}
        </span>
        <div className="flex shrink-0 items-center gap-3">
          {many && (
            <span className="tabular-nums text-white/70" aria-label="Позиция в коллекции">
              {index + 1} / {items.length}
            </span>
          )}
          <a
            href={item.src}
            download={item.name}
            className="rounded-full border border-white/40 px-3 py-1 text-xs font-medium transition-colors duration-[var(--duration-fast)] hover:border-accent hover:text-accent"
          >
            Скачать
          </a>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="grid size-8 place-items-center rounded-full border border-white/40 text-white transition-colors duration-[var(--duration-fast)] hover:text-accent"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Сцена: медиа по центру, prev/next по краям. */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center">
        {many && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onIndexChange(index - 1);
            }}
            disabled={!hasPrev}
            aria-label="Предыдущее"
            className="absolute left-0 z-10 grid size-11 place-items-center rounded-full bg-white/10 text-2xl text-white transition-colors duration-[var(--duration-fast)] hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
          >
            ‹
          </button>
        )}

        <div className="max-h-full max-w-full" onClick={(e) => e.stopPropagation()}>
          {broken ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-white/20 bg-panel px-8 py-10 text-center">
              <span className="text-5xl" aria-hidden="true">
                {item.isVideo ? '🎬' : '🖼️'}
              </span>
              <p className="max-w-xs truncate text-sm text-fg" title={item.name}>
                {item.name}
              </p>
              <p className="text-xs text-muted">
                Формат не отображается в браузере — скачайте оригинал.
              </p>
              <a
                href={item.src}
                download={item.name}
                className="rounded-full bg-accent px-4 py-1.5 text-xs font-semibold text-accent-ink"
              >
                Скачать
              </a>
            </div>
          ) : item.isVideo ? (
            <video
              key={item.src}
              src={item.src}
              controls
              playsInline
              className="max-h-[80vh] max-w-full rounded-lg"
              onError={() => setBroken(true)}
            />
          ) : (
            <img
              key={item.src}
              src={item.src}
              alt={item.name}
              className="max-h-[80vh] max-w-full rounded-lg object-contain"
              onError={() => setBroken(true)}
            />
          )}
        </div>

        {many && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onIndexChange(index + 1);
            }}
            disabled={!hasNext}
            aria-label="Следующее"
            className="absolute right-0 z-10 grid size-11 place-items-center rounded-full bg-white/10 text-2xl text-white transition-colors duration-[var(--duration-fast)] hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
          >
            ›
          </button>
        )}
      </div>
    </div>
  );
}
