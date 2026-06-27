/** Минимальный ввод тренировки для попапа дня: тип · длительность · усилие · заметка · фото/видео
 *  → POST /workouts/simple (пишет на дату дня). Под формой — «Расширенный ввод», уводящий на
 *  детальный логгер (/workouts) за тот же день: подходы с весами, дистанция/темп, попытки. */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  api,
  ApiError,
  type SimpleWorkout,
  type SportCategory,
  type WorkoutKind,
  type WorkoutMetrics,
} from '../../lib/api';
import { useMySports } from '../../lib/sports';
import { inputCls, SaveButton, errText, numOrNull } from './formKit';
import { MediaThumb, useFilePreviews } from './mediaKit';
import { MediaLightbox } from './MediaLightbox';

// Бэкенд /workouts/simple всё ещё требует kind — выводим его из категории выбранного вида спорта
// (тип/категорию руками больше не выбираем). KIND_LABEL — для сводки ранее внесённых логов.
const CATEGORY_KIND: Record<SportCategory, WorkoutKind> = {
  strength: 'strength',
  endurance: 'cardio',
  combat: 'other',
  team: 'other',
  racket: 'other',
  action: 'skill',
  precision: 'skill',
  artistic: 'skill',
  other: 'other',
};
const KIND_LABEL: Record<string, string> = {
  strength: 'Сила',
  cardio: 'Кардио',
  skill: 'Скилл',
  other: 'Другое',
};

// Метрики Welltory «Анализ тренировки» (ядро 9671): ключ = поле бэкенда (snake_case), label —
// подпись. Заполняются вручную или распознаванием со скрина (api.previewWorkout). duration_min
// распознаётся отдельно и кладётся в поле «Длительность».
const M_FIELDS = [
  { key: 'total_kcal', label: 'Всего ккал' },
  { key: 'active_kcal', label: 'Актив. ккал' },
  { key: 'total_met', label: 'Всего МЕТ' },
  { key: 'useful_met', label: 'Полезные МЕТ' },
  { key: 'hr_avg', label: 'Пульс сред.' },
  { key: 'hr_max', label: 'Пульс макс.' },
  { key: 'load_pct', label: 'Нагрузка, %' },
  { key: 'score', label: 'Оценка' },
] as const;

export function WorkoutForm({ date, onSaved }: { date: string; onSaved?: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [sportId, setSportId] = useState<number | null>(null);
  const [duration, setDuration] = useState('');
  const [rpe, setRpe] = useState<number | null>(null);
  const [surpassedSelf, setSurpassedSelf] = useState(false);
  const [note, setNote] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [lightboxAt, setLightboxAt] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false); // дроп-зона фото/видео
  const [metrics, setMetrics] = useState<Record<string, string>>({}); // метрики Welltory (9671)
  const [screenDrag, setScreenDrag] = useState(false); // дроп-зона скрина «Распознать»
  // id редактируемого лога: null → создаём новый, иначе PATCH этого лога («Изменить» из сводки).
  const [editingId, setEditingId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Превью медиа (objectURL + fallback HEIC/HEVC) — общий хук из mediaKit (M2·F10).
  const previews = useFilePreviews(files);

  // Привязанные дисциплины (M2·B19): из них выбираем вид ПРЯМО (плоский список, без шага категории).
  const { data: mySports, isPending: sportsPending } = useMySports();
  // Auto-select первого привязанного; если выбранный вид отвязали — встаём на первый доступный.
  useEffect(() => {
    setSportId((prev) => {
      if (!mySports || mySports.length === 0) return null;
      return mySports.some((s) => s.sport_id === prev) ? prev : mySports[0].sport_id;
    });
  }, [mySports]);
  const selectedSport = mySports?.find((s) => s.sport_id === sportId) ?? null;
  // kind бэкенду всё ещё нужен — выводим из категории выбранного вида (нет вида → other).
  const kind: WorkoutKind = selectedSport ? CATEGORY_KIND[selectedSport.category] : 'other';

  // Ранее внесённые тренировки дня (предзаполнение «Изменить»): простые логи append-only и
  // их может быть несколько за день, поэтому показываем их сводкой над формой ввода нового лога.
  const dayWorkouts = useQuery({
    queryKey: ['day-simple-workouts', date],
    queryFn: () => api.listDaySimpleWorkouts(date),
    enabled: !!date,
  });
  const logged = dayWorkouts.data ?? [];

  const buildMetrics = (): WorkoutMetrics => ({
    totalKcal: numOrNull(metrics.total_kcal),
    activeKcal: numOrNull(metrics.active_kcal),
    totalMet: numOrNull(metrics.total_met),
    usefulMet: numOrNull(metrics.useful_met),
    hrAvg: numOrNull(metrics.hr_avg),
    hrMax: numOrNull(metrics.hr_max),
    loadPct: numOrNull(metrics.load_pct),
    score: numOrNull(metrics.score),
  });

  const save = useMutation({
    mutationFn: () => {
      // Общие скалярные поля формы. При редактировании уходят PATCH-ем (без медиа), при создании
      // — multipart-ом вместе с файлами.
      const common = {
        kind,
        sportId,
        durationMin: duration.trim() ? Number(duration) : null,
        rpe,
        note: note.trim() || null,
        surpassedSelf,
        metrics: buildMetrics(),
      };
      return editingId != null
        ? api.updateSimpleWorkout(editingId, common)
        : api.createSimpleWorkout({ date, ...common, files });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      // Сохранение могло добавить медиа → освежаем полосу медиа дня (M3·F12).
      qc.invalidateQueries({ queryKey: ['workout-media'] });
      // …и сводку ранее внесённых тренировок дня (новый/изменённый лог появляется сразу).
      qc.invalidateQueries({ queryKey: ['day-simple-workouts', date] });
      // После правки выходим из режима редактирования и чистим форму; при создании оставляем
      // поля как было (append-only — можно сразу добавить ещё лог).
      if (editingId != null) {
        setEditingId(null);
        clearForm();
      }
      onSaved?.();
    },
  });

  function reset() {
    setErr(null);
    save.reset();
  }

  // Очистить поля ввода (без вида спорта — он остаётся выбранным).
  function clearForm() {
    setDuration('');
    setRpe(null);
    setSurpassedSelf(false);
    setNote('');
    setMetrics({});
    setFiles([]);
  }

  // Загрузить прежние значения лога в форму («Изменить» из сводки) → дальше сохранение идёт PATCH-ем.
  // Медиа не подставляем (file-input не предзаполнить); существующее медиа лога не трогается.
  function startEdit(w: SimpleWorkout) {
    setEditingId(w.id);
    setSportId(w.sport_id);
    setDuration(w.duration_min != null ? String(w.duration_min) : '');
    setRpe(w.rpe);
    setSurpassedSelf(w.surpassed_self);
    setNote(w.notes ?? '');
    setFiles([]);
    setMetrics({
      total_kcal: w.total_kcal != null ? String(w.total_kcal) : '',
      active_kcal: w.active_kcal != null ? String(w.active_kcal) : '',
      total_met: w.total_met != null ? String(w.total_met) : '',
      useful_met: w.useful_met != null ? String(w.useful_met) : '',
      hr_avg: w.hr_avg != null ? String(w.hr_avg) : '',
      hr_max: w.hr_max != null ? String(w.hr_max) : '',
      load_pct: w.load_pct != null ? String(w.load_pct) : '',
      score: w.score != null ? String(w.score) : '',
    });
    reset();
  }

  // Выйти из режима правки без сохранения — вернуться к добавлению нового лога.
  function exitEdit() {
    setEditingId(null);
    clearForm();
    reset();
  }

  // Распознать метрики со скрина Welltory «Анализ тренировки» (vision) → заполнить поля + длит.
  const recognize = useMutation({
    mutationFn: (file: File) => api.previewWorkout(file),
    onSuccess: (p) => {
      const got = p as Record<string, number | null>;
      setMetrics(() => {
        const next: Record<string, string> = {};
        for (const f of M_FIELDS) next[f.key] = got[f.key] != null ? String(got[f.key]) : '';
        return next;
      });
      if (p.duration_min != null) setDuration(String(p.duration_min));
      reset();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Длительность опциональна, но если вписана — должна быть положительным числом.
    const hasDuration = duration.trim() !== '';
    const n = Number(duration);
    if (hasDuration && (!Number.isFinite(n) || n <= 0)) {
      setErr('Длительность — число минут больше нуля.');
      return;
    }
    // Тип сам по себе ничего не фиксирует — нужна хоть какая-то начинка (вкл. метрики Welltory).
    const hasMetrics = M_FIELDS.some((f) => metrics[f.key]?.trim());
    if (!hasDuration && !note.trim() && files.length === 0 && !hasMetrics) {
      setErr('Заполните хотя бы одно: длительность, заметку, метрики или фото/видео.');
      return;
    }
    setErr(null);
    save.mutate();
  };

  const kindLabel = (k: string) => KIND_LABEL[k] ?? k;

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {/* Ранее внесённые тренировки за день — сводка (тип · время · усилие · заметка · медиа).
          Медиа этих логов открывается из «Медиа дня» над формой (DayWorkoutMediaStrip). */}
      {logged.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">Тренировки за этот день</span>
          <ul className="flex flex-col gap-1">
            {logged.map((w) => (
              <li
                key={w.id}
                className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border bg-ink/30 px-2.5 py-1.5 text-xs text-fg ${
                  editingId === w.id ? 'border-accent' : 'border-line'
                }`}
              >
                <span className="font-medium">{kindLabel(w.kind)}</span>
                {w.duration_min != null && (
                  <span className="text-muted">· {w.duration_min} мин</span>
                )}
                {w.rpe != null && <span className="text-muted">· усилие {w.rpe}/10</span>}
                {w.notes && <span className="text-muted">· {w.notes}</span>}
                {w.surpassed_self && <span title="Личный рекорд">· 🏆</span>}
                {w.media.length > 0 && <span className="text-muted">· 📎 {w.media.length}</span>}
                {/* «Изменить» — подставляет значения лога в форму ниже (дальше PATCH этого лога). */}
                <button
                  type="button"
                  onClick={() => startEdit(w)}
                  className="ml-auto shrink-0 rounded-full border border-line px-2.5 py-0.5 text-[0.7rem] font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:border-accent/60"
                >
                  {editingId === w.id ? 'Редактируется' : 'Изменить'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Баннер режима правки: видно, что сохранение обновит существующий лог, а не создаст новый. */}
      {editingId != null && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs">
          <span className="font-medium text-accent">Изменение записи — сохранение обновит её</span>
          <button
            type="button"
            onClick={exitEdit}
            className="shrink-0 font-medium text-muted underline-offset-2 transition-colors duration-[var(--duration-fast)] hover:text-accent hover:underline"
          >
            Отменить
          </button>
        </div>
      )}

      {/* Вид спорта — выбираем ПРЯМО из привязанных дисциплин (плоский список). Нет привязок —
          кнопка увести в каталог; «Добавить спорт» рядом — привязать/предложить новый. Тип/kind
          выводится из категории выбранного вида (см. CATEGORY_KIND). */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">Вид спорта</span>
        {sportsPending ? (
          <span className="text-xs text-muted">Загрузка…</span>
        ) : !mySports || mySports.length === 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">Нет привязанных видов спорта.</span>
            <button
              type="button"
              onClick={() => navigate('/sports')}
              className="rounded-full border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:bg-accent/20"
            >
              + Добавить спорт
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Вид спорта"
              value={sportId == null ? '' : String(sportId)}
              onChange={(e) => {
                setSportId(e.target.value ? Number(e.target.value) : null);
                reset();
              }}
              className={inputCls}
            >
              {mySports.map((s) => (
                <option key={s.sport_id} value={String(s.sport_id)}>
                  {s.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => navigate('/sports')}
              className="shrink-0 rounded-full border border-line px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:border-accent/60"
            >
              + Добавить спорт
            </button>
          </div>
        )}
      </div>

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

      {/* Welltory «Анализ тренировки» (ядро 9671): распознать со скрина (drag-and-drop, как в
          активности) ИЛИ вписать вручную. Распознавание заполняет поля + длительность. */}
      <div className="flex flex-col gap-2">
        <span className="text-xs text-muted">Метрики со скрина Welltory (необязательно)</span>
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setScreenDrag(true);
          }}
          onDragLeave={() => setScreenDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setScreenDrag(false);
            const f = e.dataTransfer.files[0];
            if (f) recognize.mutate(f);
          }}
          className={`flex cursor-pointer items-center justify-center rounded-xl border border-dashed px-3 py-3 text-center text-sm transition-colors duration-[var(--duration-fast)] ${
            screenDrag ? 'border-accent bg-accent/5' : 'border-line hover:border-accent/50'
          }`}
        >
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) recognize.mutate(f);
            }}
          />
          <span className="truncate text-muted">
            {recognize.isPending
              ? 'Распознаём…'
              : 'Перетащите скрин «Анализ тренировки» или нажмите'}
          </span>
        </label>
        {recognize.isError && (
          <p className="text-xs font-medium text-amber">
            {recognize.error instanceof ApiError
              ? recognize.error.message
              : 'Не удалось распознать скрин.'}{' '}
            Заполните вручную.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {M_FIELDS.map((f) => (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-xs text-muted">{f.label}</span>
              <input
                className={`${inputCls} tabular-nums`}
                type="number"
                inputMode="numeric"
                value={metrics[f.key] ?? ''}
                onChange={(e) => {
                  setMetrics((v) => ({ ...v, [f.key]: e.target.value }));
                  reset();
                }}
                placeholder="—"
              />
            </label>
          ))}
        </div>
      </div>

      {/* Усилие — ползунок 1–10 (M2·F8), опционально. Трек-градиент зелёный→красный = шкала
          «легко→до отказа»; пока не двигали — «Не указано» (полупрозрачный), «Сбросить» возвращает
          в это состояние. aria-valuetext озвучивает выбор для скринридера. */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted">
            Усилие (необязательно, 1 — легко, 10 — до отказа)
          </span>
          <span className="text-xs font-semibold tabular-nums text-fg">
            {rpe == null ? 'Не указано' : `${rpe} / 10`}
          </span>
        </div>
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={rpe ?? 5}
          aria-label="Усилие"
          aria-valuetext={rpe == null ? 'Не указано' : `${rpe} из 10`}
          onChange={(e) => {
            setRpe(Number(e.target.value));
            reset();
          }}
          className={`effort-slider ${rpe == null ? 'opacity-50' : ''}`}
        />
        {rpe != null && (
          <button
            type="button"
            onClick={() => {
              setRpe(null);
              reset();
            }}
            className="self-start text-xs font-medium text-muted underline-offset-2 transition-colors duration-[var(--duration-fast)] hover:text-accent hover:underline"
          >
            Сбросить
          </button>
        )}
      </div>

      {/* «Превзошёл сам себя» — необязательная отметка личного рекорда сессии (M2·F9). В payload
          createSimpleWorkout уходит surpassed_self; по умолчанию снят (бэкенд default False). */}
      <label className="flex cursor-pointer items-center gap-2 self-start text-sm text-fg">
        <input
          type="checkbox"
          checked={surpassedSelf}
          onChange={(e) => {
            setSurpassedSelf(e.target.checked);
            reset();
          }}
          className="size-4 accent-accent"
        />
        <span>
          Превзошёл сам себя 🏆 <span className="text-muted">(личный рекорд, необязательно)</span>
        </span>
      </label>

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

      {/* Фото/видео — только при создании нового лога. В режиме правки скрыто: PATCH медиа не
          пишет, поэтому не даём добавить файлы, которые молча потерялись бы (медиа лога видно в
          сводке выше как 📎N). Инпут — sr-only, клик через ref (Safari). */}
      {editingId == null && (
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
          {/* Добавить медиа · Просмотреть. «Просмотреть» (M3·F13) — явный вход в лайтбокс добавленных
            media[], доступен и после сохранения (превью не сбрасываются). Открывает первый кадр;
            листание ‹/› внутри лайтбокса. Дублирует клик по миниатюре (F11), но даёт подписанный
            контрол, как требует карточка. */}
          {/* Drag-and-drop фото/видео (как в еде): перетащить ИЛИ нажать (клик через ref — Safari). */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const list = e.dataTransfer.files;
              if (list && list.length) {
                setFiles((prev) => [...prev, ...Array.from(list)]);
                reset();
              }
            }}
            className={`flex cursor-pointer items-center justify-center rounded-xl border border-dashed px-3 py-3 text-center text-sm transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
              dragOver ? 'border-accent bg-accent/5' : 'border-line hover:border-accent/50'
            }`}
          >
            <span className="truncate text-muted">Перетащите фото / видео или нажмите</span>
          </div>
          {previews.length > 0 && (
            <button
              type="button"
              onClick={() => setLightboxAt(0)}
              className="self-start rounded-full border border-line px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:border-accent/60"
            >
              Просмотреть ({previews.length})
            </button>
          )}
          {previews.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {previews.map((p, i) => (
                <MediaThumb
                  key={`${p.file.name}-${i}`}
                  file={p.file}
                  url={p.url}
                  isVideo={p.isVideo}
                  onOpen={() => setLightboxAt(i)}
                  onRemove={() => {
                    setFiles((prev) => prev.filter((_, j) => j !== i));
                    reset();
                  }}
                />
              ))}
            </ul>
          )}
        </div>
      )}

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

      {lightboxAt !== null && previews[lightboxAt] && (
        <MediaLightbox
          items={previews.map((p) => ({ src: p.url, isVideo: p.isVideo, name: p.file.name }))}
          index={lightboxAt}
          onIndexChange={setLightboxAt}
          onClose={() => setLightboxAt(null)}
        />
      )}
    </form>
  );
}
