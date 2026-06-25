/** Видео-пруф: drag-drop / выбор видеофайла с состояниями (загрузка / загружено / заменить).
 *  Извлечён из AchievementsPage (M6·F27), переиспользуется в челленджах. Презентационный:
 *  загрузку и текст ошибки держит родитель, сюда отдаёт готовые флаги и сообщение. */

interface VideoProofUploaderProps {
  /** Вызывается только с реальным файлом (undefined из событий отфильтрован внутри). */
  onPick: (file: File) => void;
  isPending: boolean;
  hasProof: boolean;
  /** Готовый текст ошибки от родителя; null/undefined — ошибки нет. */
  error?: string | null;
}

export default function VideoProofUploader({
  onPick,
  isPending,
  hasProof,
  error,
}: VideoProofUploaderProps) {
  // input/drop отдают File | undefined — наружу пропускаем только реальный файл.
  const pick = (file: File | undefined) => {
    if (file) onPick(file);
  };

  return (
    <>
      <label
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          pick(e.dataTransfer.files[0]);
        }}
        className="cursor-pointer rounded-lg border border-dashed border-line bg-surface px-3 py-2 text-center text-sm font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
      >
        <input
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
        {isPending
          ? 'Загружаем видео…'
          : hasProof
            ? 'Видео загружено ✓ — заменить'
            : 'Загрузить видео'}
      </label>

      {error && (
        <p role="alert" className="text-xs font-medium text-amber">
          {error}
        </p>
      )}
    </>
  );
}
