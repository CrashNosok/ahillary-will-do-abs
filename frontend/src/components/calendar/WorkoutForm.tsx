/** Минимальный ввод тренировки для попапа дня: тип · длительность · усилие · заметка · фото/видео
 *  → POST /workouts/simple (пишет на дату дня). Под формой — «Расширенный ввод», уводящий на
 *  детальный логгер (/workouts) за тот же день: подходы с весами, дистанция/темп, попытки. */

import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, SPORT_CATEGORIES, type SportCategory, type WorkoutKind } from '../../lib/api';
import { useMySports } from '../../lib/sports';
import { inputCls, SaveButton, errText } from './formKit';

const KINDS: { id: WorkoutKind; label: string }[] = [
  { id: 'strength', label: 'Сила' },
  { id: 'cardio', label: 'Кардио' },
  { id: 'skill', label: 'Скилл' },
  { id: 'other', label: 'Другое' },
];
const RPE_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

const chip =
  'rounded-full px-3 py-1 text-xs font-medium transition-colors duration-[var(--duration-fast)]';

/** Превью одного медиа. Если миниатюра не строится (HEIC/HEVC браузер не рисует) — показываем
 *  иконку и имя файла, чтобы было видно, что файл прикреплён, а не «ничего не загрузилось». */
function MediaThumb({
  file,
  url,
  isVideo,
  onRemove,
}: {
  file: File;
  url: string;
  isVideo: boolean;
  onRemove: () => void;
}) {
  const [broken, setBroken] = useState(false);
  return (
    <li className="relative size-16 overflow-hidden rounded-lg border border-line bg-panel">
      {broken ? (
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

export function WorkoutForm({ date, onSaved }: { date: string; onSaved?: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [kind, setKind] = useState<WorkoutKind>('strength');
  const [category, setCategory] = useState<SportCategory | null>(null);
  const [sportId, setSportId] = useState<number | null>(null);
  const [duration, setDuration] = useState('');
  const [rpe, setRpe] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Превью медиа (objectURL): пересоздаём при смене files, старые URL чистим. Видео — по MIME или
  // расширению (телефонные .mov иногда без корректного type).
  const previews = useMemo(
    () =>
      files.map((f) => ({
        file: f,
        url: URL.createObjectURL(f),
        isVideo:
          f.type.startsWith('video/') || /\.(mp4|mov|m4v|webm|avi|mkv|3gp|hevc)$/i.test(f.name),
      })),
    [files],
  );
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  // Категории — только у привязанных дисциплин (M2·F6). Берём из /me/sports, оставляем уникальные
  // и упорядочиваем по канону SPORT_CATEGORIES (стабильный порядок чипов, без дублей).
  const { data: mySports, isPending: sportsPending } = useMySports();
  const myCategories = useMemo(() => {
    const have = new Set((mySports ?? []).map((s) => s.category));
    return SPORT_CATEGORIES.filter((c) => have.has(c.value));
  }, [mySports]);
  // Виды спорта выбранной категории (M2·F7): фильтруем привязанные дисциплины по категории —
  // в дропдауне можно выбрать конкретный вид, а не только первый.
  const categorySports = useMemo(
    () => (category ? (mySports ?? []).filter((s) => s.category === category) : []),
    [mySports, category],
  );
  // Auto-select первого вида (паттерн CardioLoggerForm): нет привязок категории → сброс в null;
  // выбранный вид выпал из списка (сменили/сняли категорию) → встаём на первый доступный.
  useEffect(() => {
    setSportId((prev) => {
      if (categorySports.length === 0) return null;
      return categorySports.some((s) => s.sport_id === prev) ? prev : categorySports[0].sport_id;
    });
  }, [categorySports]);

  const save = useMutation({
    mutationFn: () =>
      api.createSimpleWorkout({
        date,
        kind,
        sportId,
        durationMin: duration.trim() ? Number(duration) : null,
        rpe,
        note: note.trim() || null,
        files,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      onSaved?.();
    },
  });

  function reset() {
    setErr(null);
    save.reset();
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Длительность опциональна, но если вписана — должна быть положительным числом.
    const hasDuration = duration.trim() !== '';
    const n = Number(duration);
    if (hasDuration && (!Number.isFinite(n) || n <= 0)) {
      setErr('Длительность — число минут больше нуля.');
      return;
    }
    // Тип сам по себе ничего не фиксирует — нужна хоть какая-то начинка.
    if (!hasDuration && !note.trim() && files.length === 0) {
      setErr('Заполните хотя бы одно: длительность, заметку или фото/видео.');
      return;
    }
    setErr(null);
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {/* Тип */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">Тип</span>
        <div role="radiogroup" aria-label="Тип тренировки" className="flex flex-wrap gap-1.5">
          {KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              role="radio"
              aria-checked={k.id === kind}
              onClick={() => {
                setKind(k.id);
                reset();
              }}
              className={`${chip} ${
                k.id === kind
                  ? 'bg-accent text-accent-ink'
                  : 'border border-line text-muted hover:border-accent/50 hover:text-fg'
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>
      </div>

      {/* Категория — только дисциплины, привязанные к себе (M2·F6). Нет привязок → подсказка
          увести в каталог; привязки есть → чипы их категорий (необязательный выбор-тоггл). */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">Категория (необязательно)</span>
        {sportsPending ? (
          <span className="text-xs text-muted">Загрузка…</span>
        ) : myCategories.length === 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">
              Привяжите вид спорта, чтобы выбрать категорию.
            </span>
            <button
              type="button"
              onClick={() => navigate('/data-entry?tab=sports')}
              className="rounded-full border border-line px-3 py-1 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:border-accent/60"
            >
              Виды спорта →
            </button>
          </div>
        ) : (
          <div
            role="radiogroup"
            aria-label="Категория дисциплины"
            className="flex flex-wrap gap-1.5"
          >
            {myCategories.map((c) => (
              <button
                key={c.value}
                type="button"
                role="radio"
                aria-checked={c.value === category}
                onClick={() => {
                  setCategory((p) => (p === c.value ? null : c.value));
                  reset();
                }}
                className={`${chip} ${
                  c.value === category
                    ? 'bg-accent text-accent-ink'
                    : 'border border-line text-muted hover:border-accent/50 hover:text-fg'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Вид спорта — конкретная дисциплина выбранной категории (M2·F7). Виден только при выбранной
          категории с привязками; первый вид авто-выбран (паттерн CardioLoggerForm). */}
      {category && categorySports.length > 0 && (
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Вид спорта</span>
          <select
            aria-label="Вид спорта"
            value={sportId == null ? '' : String(sportId)}
            onChange={(e) => {
              setSportId(e.target.value ? Number(e.target.value) : null);
              reset();
            }}
            className={inputCls}
          >
            {categorySports.map((s) => (
              <option key={s.sport_id} value={String(s.sport_id)}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="flex max-w-[10rem] flex-col gap-1">
        <span className="text-xs text-muted">Длительность, мин</span>
        <input
          className={`${inputCls} tabular-nums`}
          type="number"
          inputMode="numeric"
          step="1"
          min="0"
          value={duration}
          onChange={(e) => {
            setDuration(e.target.value);
            reset();
          }}
          placeholder="—"
        />
      </label>

      {/* Усилие — RPE тапом, опционально */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">
          Усилие (необязательно, 1 — легко, 10 — до отказа)
        </span>
        <div className="flex flex-wrap gap-1">
          {RPE_VALUES.map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={rpe === v}
              onClick={() => {
                setRpe((p) => (p === v ? null : v));
                reset();
              }}
              className={`size-7 rounded-md text-xs font-semibold tabular-nums transition-colors duration-[var(--duration-fast)] ${
                rpe === v
                  ? 'bg-accent text-accent-ink'
                  : 'border border-line text-muted hover:border-accent/50 hover:text-fg'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Заметка (необязательно)</span>
        <input
          className={inputCls}
          value={note}
          onChange={(e) => {
            setNote(e.target.value);
            reset();
          }}
          placeholder="Напр. День ног · прогон трюка"
        />
      </label>

      {/* Фото/видео. Инпут — sr-only (не display:none), клик через ref: надёжно во всех браузерах,
          включая Safari, где label+display:none иногда не открывает выбор файла. */}
      <div className="flex flex-col gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="image/*,video/*"
          multiple
          className="sr-only"
          onChange={(e) => {
            const list = e.target.files;
            if (list && list.length) {
              setFiles((prev) => [...prev, ...Array.from(list)]);
              reset();
            }
            e.target.value = '';
          }}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="self-start rounded-full border border-line px-3 py-1.5 text-xs font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50"
        >
          Добавить фото / видео
        </button>
        {previews.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {previews.map((p, i) => (
              <MediaThumb
                key={`${p.file.name}-${i}`}
                file={p.file}
                url={p.url}
                isVideo={p.isVideo}
                onRemove={() => {
                  setFiles((prev) => prev.filter((_, j) => j !== i));
                  reset();
                }}
              />
            ))}
          </ul>
        )}
      </div>

      {err && <p className="text-xs font-medium text-amber">{err}</p>}
      {save.isError && <p className="text-xs font-medium text-amber">{errText(save.error)}</p>}
      <SaveButton pending={save.isPending} success={save.isSuccess} />

      {/* Точные данные — на отдельной странице детального логгера за тот же день. */}
      <button
        type="button"
        onClick={() => navigate(`/workouts?day=${date}`)}
        className="mt-1 self-start rounded-full border border-line px-4 py-2 text-xs font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/60 hover:text-accent"
      >
        Расширенный ввод →
      </button>
    </form>
  );
}
