/** Логгер кардио (S3.8): дистанция, время (мин:сек) и пульс одной сессией →
 *  POST /workouts/cardio (S3.5). Темп бэкенд считает сам из дистанции и времени и
 *  возвращает его в ответе — поэтому показываем рассчитанный темп после сохранения. */

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, type CardioInput, type CardioLog, type Sport } from '../lib/api';
import { useSports } from '../lib/sports';
import { inputCls, optNum, todayIso } from '../lib/workoutForm';

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Не удалось сохранить (${error.status}). ${error.message}`;
  return 'Не удалось сохранить. Проверьте, что сервер запущен.';
}

/** Секунды → «M:SS» для строки успеха (бэкенд хранит длительность в секундах). */
function fmtDuration(totalSec: number): string {
  const sec = Math.round(totalSec);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

export default function CardioLoggerForm() {
  const { data: sports } = useSports();
  const cardioSports = useMemo<Sport[]>(
    () => (sports ?? []).filter((s) => s.type === 'cardio'),
    [sports],
  );

  const [date, setDate] = useState<string>(todayIso());
  const [sportId, setSportId] = useState<string>('');
  const [title, setTitle] = useState('');
  const [distance, setDistance] = useState('');
  const [min, setMin] = useState('');
  const [sec, setSec] = useState('');
  const [avgHr, setAvgHr] = useState('');
  const [maxHr, setMaxHr] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  // Дефолт вида спорта: первый кардио-вид (если такие заведены).
  useEffect(() => {
    if (sportId || cardioSports.length === 0) return;
    setSportId(String(cardioSports[0].id));
  }, [cardioSports, sportId]);

  const save = useMutation<CardioLog, unknown, CardioInput>({
    mutationFn: (input) => api.createCardio(input),
  });

  // Любая правка после сохранения снова разблокирует кнопку и снимает ошибку валидации.
  function touched() {
    setValidationError(null);
    save.reset();
  }

  function bind(setter: (v: string) => void) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setter(e.target.value);
      touched();
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!date) {
      setValidationError('Укажите дату тренировки.');
      return;
    }
    const dist = optNum(distance);
    if (dist === 'invalid' || dist === null || dist <= 0) {
      setValidationError('Дистанция — положительное число километров.');
      return;
    }
    const m = optNum(min);
    const s = optNum(sec, 59);
    if (m === 'invalid') {
      setValidationError('Минуты — неотрицательное число.');
      return;
    }
    if (s === 'invalid') {
      setValidationError('Секунды — число от 0 до 59.');
      return;
    }
    const durationSec = (m ?? 0) * 60 + (s ?? 0);
    if (durationSec <= 0) {
      setValidationError('Укажите время тренировки больше нуля.');
      return;
    }
    const avg = optNum(avgHr);
    const max = optNum(maxHr);
    if (avg === 'invalid') {
      setValidationError('Средний пульс — неотрицательное число.');
      return;
    }
    if (max === 'invalid') {
      setValidationError('Макс. пульс — неотрицательное число.');
      return;
    }
    setValidationError(null);
    save.mutate({
      date,
      sport_id: sportId ? Number(sportId) : null,
      title: title.trim() || null,
      distance_km: dist,
      duration_sec: durationSec,
      avg_hr: avg === null ? null : Math.round(avg),
      max_hr: max === null ? null : Math.round(max),
    });
  }

  const noCardioSports = (sports ?? []).length > 0 && cardioSports.length === 0;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Кардио тренировка"
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
            onChange={bind(setDate)}
            className={`${inputCls} [color-scheme:dark]`}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Вид спорта (необязательно)</span>
          <select
            name="sport"
            value={sportId}
            onChange={bind(setSportId)}
            className={`${inputCls} [color-scheme:dark]`}
          >
            <option value="">— не выбран —</option>
            {cardioSports.map((s) => (
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
            onChange={bind(setTitle)}
            placeholder="Напр. Утренняя пробежка"
            className={inputCls}
          />
        </label>
      </div>

      {noCardioSports && (
        <p className="text-sm text-muted">
          Кардио-видов спорта пока нет — можно сохранить без привязки или завести вид на странице
          «Виды спорта».
        </p>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Дистанция, км</span>
          <input
            type="number"
            inputMode="decimal"
            step="any"
            min="0"
            name="distance"
            aria-label="Дистанция, км"
            value={distance}
            onChange={bind(setDistance)}
            placeholder="Напр. 5"
            className={`${inputCls} tabular-nums`}
          />
        </label>

        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Время (мин : сек)</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              inputMode="numeric"
              step="1"
              min="0"
              aria-label="Время — минуты"
              value={min}
              onChange={bind(setMin)}
              placeholder="мин"
              className={`${inputCls} tabular-nums`}
            />
            <span className="text-muted">:</span>
            <input
              type="number"
              inputMode="numeric"
              step="1"
              min="0"
              max="59"
              aria-label="Время — секунды"
              value={sec}
              onChange={bind(setSec)}
              placeholder="сек"
              className={`${inputCls} tabular-nums`}
            />
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Средний пульс (необязательно)</span>
          <input
            type="number"
            inputMode="numeric"
            step="1"
            min="0"
            aria-label="Средний пульс"
            value={avgHr}
            onChange={bind(setAvgHr)}
            placeholder="уд/мин"
            className={`${inputCls} tabular-nums`}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Макс. пульс (необязательно)</span>
          <input
            type="number"
            inputMode="numeric"
            step="1"
            min="0"
            aria-label="Макс. пульс"
            value={maxHr}
            onChange={bind(setMaxHr)}
            placeholder="уд/мин"
            className={`${inputCls} tabular-nums`}
          />
        </label>
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
          Сохранено: {save.data.distance_km} км за {fmtDuration(save.data.duration_sec ?? 0)}
          {save.data.avg_pace ? ` · темп ${save.data.avg_pace}` : ''} за {save.data.date}
        </p>
      )}

      <button
        type="submit"
        disabled={save.isPending || save.isSuccess}
        className="mt-1 self-start rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {save.isPending ? 'Сохраняем…' : save.isSuccess ? 'Сохранено ✓' : 'Сохранить кардио'}
      </button>
    </form>
  );
}
