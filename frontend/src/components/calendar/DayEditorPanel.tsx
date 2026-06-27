/** Редактор дня (модалка): открывается по клику на ячейку календаря. Показывает статус каждой
 *  категории (внесено/осталось) и позволяет внести/изменить данные ПРЯМО ЗДЕСЬ — форма каждой
 *  категории раскрывается инлайн (аккордеон), без перехода на другие страницы. Еда — лёгкий
 *  импорт CSV без подробного разложения. При закрытии инвалидируем dashboard → календарь
 *  обновляется. Формы переиспользуем как есть (initialDate = выбранный день). */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, type DayFlags } from '../../lib/api';
import { useScrollLock } from '../../lib/useScrollLock';
import { FoodQuickImport } from './FoodQuickImport';
import { ActivityForm } from './ActivityForm';
import { WeekWeightForm, WeekMeasurementsForm, WeekPhotoForm, WeekInbodyForm } from './WeeklyForms';
import { WorkoutForm } from './WorkoutForm';
import { DayWorkoutMediaStrip } from './DayWorkoutMediaStrip';

const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export type EditorRows = 'all' | 'daily' | 'weekly';

type Row = { key: keyof DayFlags; label: string; tab: string; hint?: string; noClear?: boolean };

const DAILY_ROWS: Row[] = [
  { key: 'has_food', label: 'Еда', tab: 'food', hint: 'CSV FatSecret' },
  { key: 'has_activity', label: 'Активность', tab: 'activity', hint: 'ручной ввод / скрин' },
  { key: 'has_training', label: 'Тренировки', tab: 'training' },
];
const WEEKLY_ROWS: Row[] = [
  { key: 'has_weight', label: 'Вес', tab: 'weight' },
  { key: 'has_body', label: 'Замеры', tab: 'measurements' },
  { key: 'has_photo', label: 'Фото', tab: 'photos' },
  // InBody — 4-й пункт: загрузка скрина анализа. Данные в той же записи, что и «Вес»
  // (inbody_measurement), поэтому отдельной очистки нет (noClear) — чистится через «Вес».
  { key: 'has_inbody', label: 'InBody', tab: 'inbody', hint: 'скрин анализа', noClear: true },
];

// Per-tab ключ запроса формы за день — чтобы при очистке/возврате обновить именно её данные
// (иначе форма осталась бы со старыми значениями и «обнуления» не было видно).
const DAY_QUERY_KEY: Record<string, string> = {
  food: 'day-food',
  activity: 'day-activity',
  training: 'day-simple-workouts',
  weight: 'day-weight',
  measurements: 'day-measurements',
  photos: 'day-photos',
};

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
    case 'inbody':
      return <WeekInbodyForm date={iso} onSaved={onSaved} />;
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
  // Очищенные прямо в попапе — строка сразу становится «Внести» (флаги-проп ещё старые).
  const [cleared, setCleared] = useState<ReadonlySet<string>>(new Set());
  const [clearing, setClearing] = useState<string | null>(null); // таб в процессе очистки
  const [confirming, setConfirming] = useState<string | null>(null); // таб с инлайн-подтверждением
  const [clearError, setClearError] = useState<string | null>(null); // таб, где очистка не удалась
  // Только что очищенное — для «Отменить» (id архивных записей); пропадает через несколько секунд.
  const [undo, setUndo] = useState<{ tab: string; ids: number[] } | null>(null);
  const [restoring, setRestoring] = useState(false);
  useScrollLock();

  // «Отменить» живёт несколько секунд после очистки, потом пропадает (данные остаются в архиве).
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 8000);
    return () => clearTimeout(t);
  }, [undo]);

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

  // Очистить данные категории за этот день/неделю (с архивацией на бэке). Подтверждение —
  // инлайн (см. рендер), без браузерного confirm. Строка сразу становится «Внести».
  const doClear = async (tab: string) => {
    setClearing(tab);
    setClearError(null);
    try {
      const res = await api.clearDayData(tab, iso);
      setCleared((s) => new Set(s).add(tab));
      setSaved((s) => {
        const n = new Set(s);
        n.delete(tab);
        return n;
      });
      setConfirming(null);
      // Форму НЕ прячем: поля просто обнуляются (см. рендер), «Отменить» — отдельным футером.
      setUndo({ tab, ids: res.archived_ids });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['workout-media'] });
      qc.invalidateQueries({ queryKey: ['body-photos'] });
      qc.invalidateQueries({ queryKey: ['progress'] });
      // …и данные самой формы за этот день — чтобы поля стали пустыми сразу.
      if (DAY_QUERY_KEY[tab]) qc.invalidateQueries({ queryKey: [DAY_QUERY_KEY[tab], iso] });
    } catch {
      setClearError(tab);
    } finally {
      setClearing(null);
    }
  };

  // «Отменить»: вернуть только что очищенное из архива (по id) и снова показать данные.
  const onUndo = async () => {
    if (!undo) return;
    setRestoring(true);
    try {
      await api.restoreDayData(undo.ids);
      const tab = undo.tab;
      setCleared((s) => {
        const n = new Set(s);
        n.delete(tab);
        return n;
      });
      setUndo(null);
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['workout-media'] });
      qc.invalidateQueries({ queryKey: ['body-photos'] });
      qc.invalidateQueries({ queryKey: ['progress'] });
      // …и данные формы за день — чтобы вернувшиеся значения снова показались в полях.
      if (DAY_QUERY_KEY[tab]) qc.invalidateQueries({ queryKey: [DAY_QUERY_KEY[tab], iso] });
    } catch {
      setClearError(undo.tab);
    } finally {
      setRestoring(false);
    }
  };

  const renderRow = (r: Row) => {
    const done = (!!flags?.[r.key] || saved.has(r.tab)) && !cleared.has(r.tab);
    const isOpen = open === r.tab;
    return (
      <li key={r.key} className="border-b border-line/60 last:border-0">
        {/* Вся строка — кнопка-раскрытие (клик где угодно по строке открывает форму). «Внести/
            Изменить» теперь визуальный бейдж (span), реагирует на hover всей строки (group). */}
        <button
          type="button"
          aria-expanded={isOpen}
          onClick={() => {
            setOpen(isOpen ? null : r.tab);
            setConfirming(null);
            setClearError(null);
          }}
          className="group flex w-full cursor-pointer items-center justify-between gap-3 py-2 text-left focus-visible:rounded-lg focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset focus-visible:outline-none"
        >
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
          <span
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-[var(--duration-fast)] ${
              isOpen
                ? 'border-accent bg-accent/15 text-accent'
                : done
                  ? 'border-line text-muted group-hover:border-accent/50 group-hover:text-fg'
                  : 'border-accent/50 bg-accent/10 text-accent group-hover:bg-accent/20'
            }`}
          >
            {isOpen ? 'Свернуть' : done ? 'Изменить' : 'Внести'}
          </span>
        </button>
        {/* Полоса медиа дня — только в строке тренировок (M3·F12), видна и без раскрытия формы. */}
        {r.tab === 'training' && <DayWorkoutMediaStrip date={iso} />}
        {isOpen && (
          <div className="entry-embed mb-3 rounded-xl border border-line bg-ink/40 p-3">
            {/* Форма категории — всегда видна. После очистки её поля просто становятся пустыми
                (данные удалены + инвалидация day-* запроса), форма НЕ исчезает. «Отменить» и
                «Очистить» показываем отдельным футером ниже, не подменяя форму. */}
            {renderForm(r.tab, iso, () => {
              setSaved((s) => new Set(s).add(r.tab));
              // Повторный ввод после очистки: снимаем «очищено» и прячем «Отменить».
              setCleared((s) => {
                const n = new Set(s);
                n.delete(r.tab);
                return n;
              });
              setUndo((u) => (u?.tab === r.tab ? null : u));
            })}

            {undo?.tab === r.tab ? (
              // Несколько секунд после очистки: вернуть из архива. Поля формы выше уже пусты.
              <div className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-line/60 pt-3">
                <span className="mr-auto text-xs text-muted">Очищено.</span>
                <button
                  type="button"
                  onClick={onUndo}
                  disabled={restoring}
                  className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/40 hover:text-fg disabled:opacity-50"
                >
                  {restoring ? 'Возврат…' : 'Отменить'}
                </button>
              </div>
            ) : done && !r.noClear ? (
              // «Очистить» — когда есть что чистить (кроме строк noClear, напр. InBody — чистится
              // через «Вес», одна запись). Инлайн-подтверждение без браузерного confirm.
              <div className="mt-3 border-t border-line/60 pt-3">
                {clearError === r.tab && (
                  <p className="mb-2 text-xs text-red-400">
                    Не удалось очистить. Попробуйте ещё раз.
                  </p>
                )}
                {confirming === r.tab ? (
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <span className="mr-auto text-xs text-muted">Очистить эти данные?</span>
                    <button
                      type="button"
                      onClick={() => doClear(r.tab)}
                      disabled={clearing === r.tab}
                      className="rounded-full border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors duration-[var(--duration-fast)] hover:bg-red-500/20 disabled:opacity-50"
                    >
                      {clearing === r.tab ? 'Очистка…' : 'Да, очистить'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(null)}
                      disabled={clearing === r.tab}
                      className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:text-fg disabled:opacity-50"
                    >
                      Отмена
                    </button>
                  </div>
                ) : (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setConfirming(r.tab);
                        setClearError(null);
                      }}
                      className="rounded-full border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors duration-[var(--duration-fast)] hover:bg-red-500/10"
                    >
                      Очистить данные
                    </button>
                  </div>
                )}
              </div>
            ) : null}
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
