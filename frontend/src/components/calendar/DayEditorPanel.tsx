/** Редактор дня (модалка): открывается по клику на ячейку календаря. Показывает статус каждой
 *  категории (внесено/осталось) и позволяет внести/изменить данные ПРЯМО ЗДЕСЬ — форма каждой
 *  категории раскрывается инлайн (аккордеон), без перехода на другие страницы. Еда — лёгкий
 *  импорт CSV без подробного разложения. При закрытии инвалидируем dashboard → календарь
 *  обновляется. Формы переиспользуем как есть (initialDate = выбранный день). */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DayFlags } from '../../lib/api';
import { useScrollLock } from '../../lib/useScrollLock';
import { FoodQuickImport } from './FoodQuickImport';
import { ActivityForm } from './ActivityForm';
import { WeekWeightForm, WeekMeasurementsForm, WeekPhotoForm } from './WeeklyForms';
import { WorkoutForm } from './WorkoutForm';
import { DayWorkoutMediaStrip } from './DayWorkoutMediaStrip';

const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export type EditorRows = 'all' | 'daily' | 'weekly';

type Row = { key: keyof DayFlags; label: string; tab: string; hint?: string };

const DAILY_ROWS: Row[] = [
  { key: 'has_food', label: 'Еда', tab: 'food', hint: 'CSV FatSecret' },
  { key: 'has_activity', label: 'Активность', tab: 'activity', hint: 'ручной ввод / скрин' },
  { key: 'has_training', label: 'Тренировки', tab: 'training' },
];
const WEEKLY_ROWS: Row[] = [
  { key: 'has_weight', label: 'Вес', tab: 'weight' },
  { key: 'has_body', label: 'Замеры', tab: 'measurements' },
  { key: 'has_photo', label: 'Фото', tab: 'photos' },
];

// Инлайн-форма категории. Дневные (еда/активность/тренировки) — существующие страницы;
// недельные (вес/замеры/фото) — минимальные формы без даты (пишут на дату недели).
function renderForm(tab: string, iso: string, onSaved: () => void) {
  switch (tab) {
    case 'food':
      return <FoodQuickImport date={iso} onSaved={onSaved} />;
    case 'activity':
      return <ActivityForm date={iso} onSaved={onSaved} />;
    case 'training':
      return <WorkoutForm date={iso} onSaved={onSaved} />;
    case 'weight':
      return <WeekWeightForm date={iso} onSaved={onSaved} />;
    case 'measurements':
      return <WeekMeasurementsForm date={iso} onSaved={onSaved} />;
    case 'photos':
      return <WeekPhotoForm date={iso} onSaved={onSaved} />;
    default:
      return null;
  }
}

export function DayEditorPanel({
  iso,
  flags,
  onClose,
  title,
  rows = 'all',
}: {
  iso: string;
  flags: DayFlags | undefined;
  onClose: () => void;
  title?: string;
  rows?: EditorRows;
}) {
  const qc = useQueryClient();
  const dateLabel = cap(dateFmt.format(new Date(iso + 'T00:00:00')));
  const showDaily = rows !== 'weekly';
  const showWeekly = rows !== 'daily';
  const [open, setOpen] = useState<string | null>(null);
  // Категории, сохранённые прямо в попапе — чтобы строка сразу стала «Изменить».
  const [saved, setSaved] = useState<ReadonlySet<string>>(new Set());
  useScrollLock();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Календарь обновляется при закрытии: после инлайн-сохранений перечитываем dashboard.
  useEffect(
    () => () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['progress'] });
      qc.invalidateQueries({ queryKey: ['body-photos'] });
    },
    [qc],
  );

  const renderRow = (r: Row) => {
    const done = !!flags?.[r.key] || saved.has(r.tab);
    const isOpen = open === r.tab;
    return (
      <li key={r.key} className="border-b border-line/60 last:border-0">
        <div className="flex items-center justify-between gap-3 py-2">
          <span className="flex min-w-0 items-center gap-2">
            <span
              aria-hidden="true"
              className={`grid size-5 shrink-0 place-items-center rounded-full text-[0.7rem] ${
                done ? 'bg-accent/20 text-accent' : 'border border-line text-muted'
              }`}
            >
              {done ? '✓' : '·'}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-fg">{r.label}</span>
              <span className="block truncate text-xs text-muted">
                {done ? 'внесено' : 'осталось'}
                {r.hint ? ` · ${r.hint}` : ''}
              </span>
            </span>
          </span>
          <button
            type="button"
            aria-expanded={isOpen}
            onClick={() => setOpen(isOpen ? null : r.tab)}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-[var(--duration-fast)] ${
              isOpen
                ? 'border-accent bg-accent/15 text-accent'
                : done
                  ? 'border-line text-muted hover:border-accent/50 hover:text-fg'
                  : 'border-accent/50 bg-accent/10 text-accent hover:bg-accent/20'
            }`}
          >
            {isOpen ? 'Свернуть' : done ? 'Изменить' : 'Внести'}
          </button>
        </div>
        {/* Полоса медиа дня — только в строке тренировок (M3·F12), видна и без раскрытия формы. */}
        {r.tab === 'training' && <DayWorkoutMediaStrip date={iso} />}
        {isOpen && (
          <div className="entry-embed mb-3 rounded-xl border border-line bg-ink/40 p-3">
            {renderForm(r.tab, iso, () => setSaved((s) => new Set(s).add(r.tab)))}
          </div>
        )}
      </li>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="day-editor-title"
      onClick={onClose}
    >
      {/* Фиксированная высота: раскрытие строки НЕ меняет размер попапа (контент скроллится внутри). */}
      <div
        className="flex h-[min(86vh,600px)] w-full max-w-2xl flex-col rounded-[var(--radius-card)] border border-line bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id="day-editor-title" className="font-display text-xl font-semibold">
              {title ?? dateLabel}
            </h3>
            <p className="mt-1 text-sm text-muted">
              {rows === 'weekly'
                ? 'Данные раз в неделю — внесите прямо здесь'
                : 'Внесите или измените данные прямо здесь'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="grid size-8 shrink-0 place-items-center rounded-full border border-line text-muted transition-colors duration-[var(--duration-fast)] hover:text-fg"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 flex-1 overflow-y-auto pr-1">
          {showDaily && (
            <>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-fg">Каждый день</h4>
              <ul className="mt-1">{DAILY_ROWS.map(renderRow)}</ul>
            </>
          )}

          {showWeekly && (
            <>
              <h4 className="mt-5 text-xs font-semibold uppercase tracking-wide text-fg">
                Раз в неделю
              </h4>
              <ul className="mt-1">{WEEKLY_ROWS.map(renderRow)}</ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
