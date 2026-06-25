/** Превью прикреплённых медиа (фото/видео) с fallback для форматов, которые браузер не рисует
 *  (HEIC/HEVC). Вынесено из WorkoutForm для переиспользования в других формах с вложениями. */

import { useEffect, useMemo, useState } from 'react';

/** Видео по MIME или расширению — телефонные .mov/.hevc иногда приходят без корректного type. */
export const isVideoFile = (f: File): boolean =>
  f.type.startsWith('video/') || /\.(mp4|mov|m4v|webm|avi|mkv|3gp|hevc)$/i.test(f.name);

export interface MediaPreview {
  file: File;
  url: string;
  isVideo: boolean;
}

/** objectURL-превью для списка файлов: пересоздаём при смене files, старые URL чистим, чтобы не
 *  течь памятью. Видео распознаём через isVideoFile (MIME или расширение). */
export function useFilePreviews(files: File[]): MediaPreview[] {
  const previews = useMemo(
    () => files.map((f) => ({ file: f, url: URL.createObjectURL(f), isVideo: isVideoFile(f) })),
    [files],
  );
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);
  return previews;
}

/** Превью одного медиа. Если миниатюра не строится (HEIC/HEVC браузер не рисует) — показываем
 *  иконку и имя файла, чтобы было видно, что файл прикреплён, а не «ничего не загрузилось».
 *  onOpen (если задан) делает область превью кнопкой — клик открывает лайтбокс на этом кадре. */
export function MediaThumb({
  file,
  url,
  isVideo,
  onRemove,
  onOpen,
}: {
  file: File;
  url: string;
  isVideo: boolean;
  onRemove: () => void;
  onOpen?: () => void;
}) {
  const [broken, setBroken] = useState(false);
  const media = broken ? (
    <span className="grid size-full place-items-center text-lg" title={file.name}>
      {isVideo ? '🎬' : '🖼️'}
    </span>
  ) : isVideo ? (
    <video src={url} className="size-full object-cover" muted onError={() => setBroken(true)} />
  ) : (
    <img
      src={url}
      alt={file.name}
      className="size-full object-cover"
      onError={() => setBroken(true)}
    />
  );
  return (
    <li className="relative size-16 overflow-hidden rounded-lg border border-line bg-panel">
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label={`Открыть ${file.name}`}
          className="block size-full cursor-zoom-in focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset focus-visible:outline-none"
        >
          {media}
        </button>
      ) : (
        media
      )}
      <span className="absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 text-[9px] text-white">
        {file.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Убрать ${file.name}`}
        className="absolute right-0.5 top-0.5 grid size-4 place-items-center rounded-full bg-black/60 text-[10px] text-white hover:bg-amber"
      >
        ✕
      </button>
    </li>
  );
}
