/** Логгер силовой тренировки (S3.7): таблица подходов (упражнение, вес×повторы,
 *  отдых, RPE) с добавлением и копированием строк. Вся сессия (шапка + все подходы)
 *  уходит одним POST /workouts (S3.4) — сохраняется целиком.
 *
 *  «Быстрый ввод серии»: новая строка наследует упражнение предыдущей, а кнопка
 *  «Копировать» дублирует строку целиком — пять одинаковых подходов в пару кликов. */

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, type Exercise, type StrengthSetInput, type Workout } from '../lib/api';
import { useExercises, useSports } from '../lib/sports';
import { inputCls, optNum, todayIso } from '../lib/workoutForm';

type SetRow = {
  key: string;
  exerciseId: string; // value <select>: id строкой или '' (не выбрано)
  weight: string;
  reps: string;
  rest: string;
  rpe: string;
};

let rowSeq = 0;
const emptyRow = (init: Partial<SetRow> = {}): SetRow => ({
  key: `row-${rowSeq++}`,
  exerciseId: '',
  weight: '',
  reps: '',
  rest: '',
  rpe: '',
  ...init,
});

/** Собрать payload подходов или вернуть текст первой ошибки валидации. */
function buildSets(rows: SetRow[]): { sets?: StrengthSetInput[]; error?: string } {
  if (rows.length === 0) return { error: 'Добавьте хотя бы один подход.' };
  const sets: StrengthSetInput[] = [];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const n = i + 1;
    if (!r.exerciseId) return { error: `Подход ${n}: выберите упражнение.` };
    const weight = optNum(r.weight);
    const reps = optNum(r.reps);
    const rest = optNum(r.rest);
    const rpe = optNum(r.rpe, 10);
    if (weight === 'invalid') return { error: `Подход ${n}: вес — неотрицательное число.` };
    if (reps === 'invalid') return { error: `Подход ${n}: повторы — неотрицательное число.` };
    if (rest === 'invalid') return { error: `Подход ${n}: отдых — неотрицательное число.` };
    if (rpe === 'invalid') return { error: `Подход ${n}: RPE — число от 0 до 10.` };
    sets.push({
      exercise_id: Number(r.exerciseId),
      set_index: n,
      weight_kg: weight,
      reps: reps === null ? null : Math.round(reps),
      rest_sec: rest,
      rpe,
    });
  }
  return { sets };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Не удалось сохранить (${error.status}). ${error.message}`;
  return 'Не удалось сохранить. Проверьте, что сервер запущен.';
}

export default function StrengthLoggerForm({ initialDate }: { initialDate?: string }) {
  const { data: sports } = useSports();
  const { data: exercises } = useExercises();

  const [date, setDate] = useState<string>(initialDate ?? todayIso());
  const [title, setTitle] = useState('');
  const [sportId, setSportId] = useState<string>('');
  const [rows, setRows] = useState<SetRow[]>([emptyRow()]);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Упражнения выбранного вида спорта — варианты для строк подходов.
  const sportExercises = useMemo<Exercise[]>(
    () => (exercises ?? []).filter((ex) => String(ex.sport_id) === sportId),
    [exercises, sportId],
  );

  // Дефолт вида спорта при загрузке: первый силовой, у которого есть упражнения.
  useEffect(() => {
    if (sportId || !sports || !exercises) return;
    const hasEx = (id: number) => exercises.some((ex) => ex.sport_id === id);
    const strength = sports.find((s) => s.type === 'strength' && hasEx(s.id));
    const anyWithEx = sports.find((s) => hasEx(s.id));
    const pick = strength ?? anyWithEx ?? sports[0];
    if (pick) setSportId(String(pick.id));
  }, [sports, exercises, sportId]);

  const save = useMutation<Workout, unknown, void>({
    mutationFn: () => {
      const { sets } = buildSets(rows);
      return api.createWorkout({
        date,
        sport_id: sportId ? Number(sportId) : null,
        title: title.trim() || null,
        sets: sets!,
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

  function setRowField(key: string, field: keyof Omit<SetRow, 'key'>, value: string) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
    touched();
  }

  function addRow() {
    // Наследуем упражнение последней строки — серия по одному упражнению вводится быстрее.
    const last = rows[rows.length - 1];
    setRows((prev) => [...prev, emptyRow({ exerciseId: last?.exerciseId ?? '' })]);
    touched();
  }

  function copyRow(key: string) {
    setRows((prev) => {
      const idx = prev.findIndex((r) => r.key === key);
      if (idx === -1) return prev;
      const src = prev[idx];
      // Свежий key из emptyRow(), переносим только данные — иначе дубль ключа в React.
      const clone = emptyRow({
        exerciseId: src.exerciseId,
        weight: src.weight,
        reps: src.reps,
        rest: src.rest,
        rpe: src.rpe,
      });
      return [...prev.slice(0, idx + 1), clone, ...prev.slice(idx + 1)];
    });
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
    const { error } = buildSets(rows);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    save.mutate();
  }

  const noExercises = sportId !== '' && sportExercises.length === 0;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Силовая тренировка"
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
            {(sports ?? []).map((s) => (
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
            placeholder="Напр. День груди"
            className={inputCls}
          />
        </label>
      </div>

      {noExercises ? (
        <p role="alert" className="text-sm font-medium text-amber">
          У выбранного вида спорта нет упражнений. Добавьте их на странице «Виды спорта».
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="w-10 px-2 font-medium">#</th>
                <th className="px-2 font-medium">Упражнение</th>
                <th className="w-24 px-2 font-medium">Вес, кг</th>
                <th className="w-24 px-2 font-medium">Повторы</th>
                <th className="w-24 px-2 font-medium">Отдых, с</th>
                <th className="w-20 px-2 font-medium">RPE</th>
                <th className="w-28 px-2 font-medium">Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.key}>
                  <td className="px-2 text-muted tabular-nums">{i + 1}</td>
                  <td className="px-2">
                    <select
                      aria-label={`Упражнение, подход ${i + 1}`}
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
                      inputMode="decimal"
                      step="any"
                      min="0"
                      aria-label={`Вес, кг — подход ${i + 1}`}
                      value={row.weight}
                      onChange={(e) => setRowField(row.key, 'weight', e.target.value)}
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
                      aria-label={`Повторы — подход ${i + 1}`}
                      value={row.reps}
                      onChange={(e) => setRowField(row.key, 'reps', e.target.value)}
                      placeholder="—"
                      className={`${inputCls} tabular-nums`}
                    />
                  </td>
                  <td className="px-2">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      min="0"
                      aria-label={`Отдых, с — подход ${i + 1}`}
                      value={row.rest}
                      onChange={(e) => setRowField(row.key, 'rest', e.target.value)}
                      placeholder="—"
                      className={`${inputCls} tabular-nums`}
                    />
                  </td>
                  <td className="px-2">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      min="0"
                      max="10"
                      aria-label={`RPE — подход ${i + 1}`}
                      value={row.rpe}
                      onChange={(e) => setRowField(row.key, 'rpe', e.target.value)}
                      placeholder="—"
                      className={`${inputCls} tabular-nums`}
                    />
                  </td>
                  <td className="px-2">
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => copyRow(row.key)}
                        aria-label={`Копировать подход ${i + 1}`}
                        className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50"
                      >
                        Копировать
                      </button>
                      <button
                        type="button"
                        onClick={() => removeRow(row.key)}
                        disabled={rows.length <= 1}
                        aria-label={`Удалить подход ${i + 1}`}
                        className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-amber/60 hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        ✕
                      </button>
                    </div>
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
          disabled={noExercises}
          className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          + Добавить подход
        </button>
        <span className="text-sm text-muted">
          Подходов: <span className="tabular-nums">{rows.length}</span>
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
          Сохранено: {save.data.sets.length}{' '}
          {save.data.sets.length === 1 ? 'подход' : 'подхода(ов)'} за {save.data.date}
        </p>
      )}

      <button
        type="submit"
        disabled={save.isPending || save.isSuccess || noExercises}
        className="mt-1 self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить сессию'}
      </button>
    </form>
  );
}
