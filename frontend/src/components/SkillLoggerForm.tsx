/** Логгер скилловых (S3.8): таблица отработанных элементов (упражнение, попытки,
 *  удачные приземления, заметка). Вся сессия (шапка + все элементы) уходит одним
 *  POST /workouts/skill (S3.6). landed не может превышать attempts — проверяем на клиенте. */

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, type Exercise, type SkillEntryInput, type SkillSession } from '../lib/api';
import { useExercises, useSports } from '../lib/sports';
import { inputCls, optNum, todayIso } from '../lib/workoutForm';

type EntryRow = {
  key: string;
  exerciseId: string; // value <select>: id строкой или '' (не выбрано)
  attempts: string;
  landed: string;
  notes: string;
};

let rowSeq = 0;
const emptyRow = (init: Partial<EntryRow> = {}): EntryRow => ({
  key: `skill-${rowSeq++}`,
  exerciseId: '',
  attempts: '',
  landed: '',
  notes: '',
  ...init,
});

/** Собрать payload элементов или вернуть текст первой ошибки валидации. */
function buildEntries(rows: EntryRow[]): { entries?: SkillEntryInput[]; error?: string } {
  if (rows.length === 0) return { error: 'Добавьте хотя бы один элемент.' };
  const entries: SkillEntryInput[] = [];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const n = i + 1;
    if (!r.exerciseId) return { error: `Элемент ${n}: выберите упражнение.` };
    const attempts = optNum(r.attempts);
    const landed = optNum(r.landed);
    if (attempts === 'invalid' || attempts === null || attempts < 1)
      return { error: `Элемент ${n}: попытки — целое число не меньше 1.` };
    if (landed === 'invalid' || landed === null)
      return { error: `Элемент ${n}: приземления — целое число не меньше 0.` };
    if (landed > attempts) return { error: `Элемент ${n}: приземлений не больше попыток.` };
    entries.push({
      exercise_id: Number(r.exerciseId),
      attempts: Math.round(attempts),
      landed: Math.round(landed),
      notes: r.notes.trim() || null,
    });
  }
  return { entries };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Не удалось сохранить (${error.status}). ${error.message}`;
  return 'Не удалось сохранить. Проверьте, что сервер запущен.';
}

export default function SkillLoggerForm({ initialDate }: { initialDate?: string }) {
  const { data: sports } = useSports();
  const { data: exercises } = useExercises();

  const [date, setDate] = useState<string>(initialDate ?? todayIso());
  const [title, setTitle] = useState('');
  const [sportId, setSportId] = useState<string>('');
  const [rows, setRows] = useState<EntryRow[]>([emptyRow()]);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Только навыковые виды спорта — кардио/силовая тут не логируются.
  const skillSports = useMemo(() => (sports ?? []).filter((s) => s.type === 'skill'), [sports]);

  // Упражнения выбранного вида спорта — варианты для строк элементов.
  const sportExercises = useMemo<Exercise[]>(
    () => (exercises ?? []).filter((ex) => String(ex.sport_id) === sportId),
    [exercises, sportId],
  );

  // Дефолт вида спорта: первый навыковый, у которого есть упражнения; иначе первый навыковый.
  useEffect(() => {
    if (sportId || skillSports.length === 0 || !exercises) return;
    const hasEx = (id: number) => exercises.some((ex) => ex.sport_id === id);
    const pick = skillSports.find((s) => hasEx(s.id)) ?? skillSports[0];
    setSportId(String(pick.id));
  }, [skillSports, exercises, sportId]);

  const save = useMutation<SkillSession, unknown, void>({
    mutationFn: () => {
      const { entries } = buildEntries(rows);
      return api.createSkill({
        date,
        sport_id: sportId ? Number(sportId) : null,
        title: title.trim() || null,
        entries: entries!,
      });
    },
  });

  // Любая правка после сохранения снова разблокирует кнопку и снимает ошибку валидации.
  function touched() {
    setValidationError(null);
    save.reset();
  }

  function onSportChange(value: string) {
    setSportId(value);
    setRows([emptyRow()]); // упражнения сменились — старые ссылки больше не валидны
    touched();
  }

  function setRowField(key: string, field: keyof Omit<EntryRow, 'key'>, value: string) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
    touched();
  }

  function addRow() {
    const last = rows[rows.length - 1];
    setRows((prev) => [...prev, emptyRow({ exerciseId: last?.exerciseId ?? '' })]);
    touched();
  }

  function removeRow(key: string) {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.key !== key)));
    touched();
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!date) {
      setValidationError('Укажите дату тренировки.');
      return;
    }
    const { error } = buildEntries(rows);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    save.mutate();
  }

  const noSkillSports = (sports ?? []).length > 0 && skillSports.length === 0;
  const noExercises = sportId !== '' && sportExercises.length === 0;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Скилл тренировка"
      className="flex flex-col gap-6 rounded-[var(--radius-card)] border border-line bg-surface p-6"
    >
      <div className="grid gap-5 sm:grid-cols-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Дата</span>
          <input
            type="date"
            name="date"
            value={date}
            max={todayIso()}
            onChange={(e) => {
              setDate(e.target.value);
              touched();
            }}
            className={`${inputCls} [color-scheme:dark]`}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Вид спорта</span>
          <select
            name="sport"
            value={sportId}
            onChange={(e) => onSportChange(e.target.value)}
            className={`${inputCls} [color-scheme:dark]`}
          >
            <option value="">— не выбран —</option>
            {skillSports.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Название (необязательно)</span>
          <input
            name="title"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              touched();
            }}
            placeholder="Напр. Сессия на скалодроме"
            className={inputCls}
          />
        </label>
      </div>

      {noSkillSports ? (
        <p role="alert" className="text-sm font-medium text-amber">
          Навыковых видов спорта пока нет. Заведите их на странице «Виды спорта».
        </p>
      ) : noExercises ? (
        <p role="alert" className="text-sm font-medium text-amber">
          У выбранного вида спорта нет упражнений. Добавьте их на странице «Виды спорта».
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="w-10 px-2 font-medium">#</th>
                <th className="px-2 font-medium">Элемент</th>
                <th className="w-24 px-2 font-medium">Попытки</th>
                <th className="w-24 px-2 font-medium">Удачно</th>
                <th className="px-2 font-medium">Заметка</th>
                <th className="w-16 px-2 font-medium">Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.key}>
                  <td className="px-2 text-muted tabular-nums">{i + 1}</td>
                  <td className="px-2">
                    <select
                      aria-label={`Элемент, строка ${i + 1}`}
                      value={row.exerciseId}
                      onChange={(e) => setRowField(row.key, 'exerciseId', e.target.value)}
                      className={`${inputCls} [color-scheme:dark]`}
                    >
                      <option value="">— выберите —</option>
                      {sportExercises.map((ex) => (
                        <option key={ex.id} value={String(ex.id)}>
                          {ex.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      step="1"
                      min="1"
                      aria-label={`Попытки — элемент ${i + 1}`}
                      value={row.attempts}
                      onChange={(e) => setRowField(row.key, 'attempts', e.target.value)}
                      placeholder="—"
                      className={`${inputCls} tabular-nums`}
                    />
                  </td>
                  <td className="px-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      step="1"
                      min="0"
                      aria-label={`Удачных приземлений — элемент ${i + 1}`}
                      value={row.landed}
                      onChange={(e) => setRowField(row.key, 'landed', e.target.value)}
                      placeholder="—"
                      className={`${inputCls} tabular-nums`}
                    />
                  </td>
                  <td className="px-2">
                    <input
                      aria-label={`Заметка — элемент ${i + 1}`}
                      value={row.notes}
                      onChange={(e) => setRowField(row.key, 'notes', e.target.value)}
                      placeholder="необязательно"
                      className={inputCls}
                    />
                  </td>
                  <td className="px-2">
                    <button
                      type="button"
                      onClick={() => removeRow(row.key)}
                      disabled={rows.length <= 1}
                      aria-label={`Удалить элемент ${i + 1}`}
                      className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-amber/60 hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={addRow}
          disabled={noSkillSports || noExercises}
          className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          + Добавить элемент
        </button>
        <span className="text-sm text-muted">
          Элементов: <span className="tabular-nums">{rows.length}</span>
        </span>
      </div>

      {validationError && (
        <p role="alert" className="text-sm font-medium text-amber">
          {validationError}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-sm font-medium text-amber">
          {errorText(save.error)}
        </p>
      )}
      {save.isSuccess && (
        <p role="status" className="text-sm font-medium text-accent">
          Сохранено: {save.data.entries.length}{' '}
          {save.data.entries.length === 1 ? 'элемент' : 'элемента(ов)'} за {save.data.date}
        </p>
      )}

      <button
        type="submit"
        disabled={save.isPending || save.isSuccess || noSkillSports || noExercises}
        className="mt-1 self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить сессию'}
      </button>
    </form>
  );
}
