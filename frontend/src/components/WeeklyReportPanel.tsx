/** Отчёт за неделю (модалка): открывается по «Получить отчёт». Показывает сводку недели
 *  (что заполнено по дням и недельным категориям, итог %) и формирует план на следующую
 *  неделю переиспользуя существующую генерацию /recommendations (POST). Ошибку LLM (502)
 *  показываем аккуратно — в этом окружении ключ невалиден, генерация ожидаемо падает. */

import { useEffect, useState } from 'react';
import { ApiError, api, type DayFlags, type Recommendation } from '../lib/api';
import { DAILY, WEEKLY, type WeekFill } from '../lib/weekly';
import { useScrollLock } from '../lib/useScrollLock';

const rangeFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const fmt = (iso: string) => rangeFmt.format(new Date(iso + 'T00:00:00'));
const weekdayFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric' });

type GenState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; rec: Recommendation }
  | { status: 'error'; message: string };

export type ReportTarget = {
  weekStart: string;
  weekEnd: string;
  days: DayFlags[];
  fill: WeekFill;
};

export function WeeklyReportPanel({
  target,
  onClose,
}: {
  target: ReportTarget;
  onClose: () => void;
}) {
  const { weekStart, weekEnd, days, fill } = target;
  const [gen, setGen] = useState<GenState>({ status: 'idle' });
  useScrollLock();

  // Esc закрывает модалку.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const weeklyPresent = WEEKLY.map((c) => ({ ...c, present: days.some((d) => d[c.key]) }));

  const generate = async () => {
    setGen({ status: 'loading' });
    try {
      const rec = await api.generateRecommendation();
      setGen({ status: 'done', rec });
    } catch (e) {
      const message =
        e instanceof ApiError
          ? `Модель недоступна (${e.status}). Попробуйте позже.`
          : 'Не удалось сформировать план.';
      setGen({ status: 'error', message });
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="weekly-report-title"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-[var(--radius-card)] border border-line bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id="weekly-report-title" className="font-display text-xl font-semibold">
              Отчёт за неделю
            </h3>
            <p className="mt-1 text-sm text-muted">
              {fmt(weekStart)} — {fmt(weekEnd)} · итог {Math.round(fill.overall * 100)}%
              {fill.overall >= 1 ? ' · идеально ✦' : ''}
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

        {/* Недельные категории */}
        <div className="mt-5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-fg">За неделю</h4>
          <div className="mt-2 flex flex-wrap gap-2">
            {weeklyPresent.map((c) => (
              <span
                key={c.key}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                  c.present ? 'border-line text-fg' : 'border-line/50 text-muted line-through'
                }`}
              >
                <span
                  className="size-2 rounded-full"
                  style={{ background: c.color, opacity: c.present ? 1 : 0.3 }}
                  aria-hidden="true"
                />
                {c.label}
              </span>
            ))}
          </div>
        </div>

        {/* Дни недели: что заполнено */}
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-fg">По дням</h4>
          <ul className="mt-2 space-y-1.5">
            {days.map((d) => {
              const filled = DAILY.filter((c) => d[c.key]);
              return (
                <li key={d.date} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-muted">
                    {weekdayFmt.format(new Date(d.date + 'T00:00:00'))}
                  </span>
                  <span className="flex items-center gap-1.5">
                    {DAILY.map((c) => (
                      <span
                        key={c.key}
                        className="size-2.5 rounded-full"
                        style={{ background: c.color, opacity: d[c.key] ? 1 : 0.18 }}
                        aria-hidden="true"
                        title={c.label}
                      />
                    ))}
                    <span className="ml-1 w-8 text-right text-xs text-muted">
                      {filled.length}/3
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        {/* План на следующую неделю — переиспользуем генерацию рекомендаций */}
        <div className="mt-6 border-t border-line pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-fg">
            План на следующую неделю
          </h4>

          {gen.status === 'done' && gen.rec.output_json ? (
            <div className="mt-2 space-y-1 text-sm">
              <p className="text-fg">
                Тренировок в неделю: {gen.rec.output_json.workout_plan.days_per_week}
              </p>
              <p className="text-muted">{gen.rec.output_json.sync_note}</p>
              <p className="text-xs text-muted">Полный план — в разделе «Рекомендации».</p>
            </div>
          ) : gen.status === 'error' ? (
            <p role="alert" className="mt-2 text-sm font-medium text-amber">
              {gen.message}
            </p>
          ) : (
            <button
              type="button"
              onClick={generate}
              disabled={gen.status === 'loading'}
              className="mt-2 rounded-full border border-accent/50 bg-accent/10 px-4 py-2 text-sm font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:bg-accent/20 disabled:opacity-60"
            >
              {gen.status === 'loading' ? 'Формируем…' : 'Сформировать план'}
            </button>
          )}
        </div>

        {/* TODO(batch: voice-weekly-questions): здесь встанет блок вопросов недели
            («почему не вносил данные / не тренировался») с записью ответов голосом
            (MediaRecorder) и корректировкой плана по ответам. Спецификация:
            docs/batch-voice-weekly-questions.md. */}
        <p className="mt-4 rounded-lg border border-dashed border-line/60 px-3 py-2 text-xs text-muted">
          Скоро: вопросы недели и голосовые ответы — скорректируем план под ваши причины.
        </p>
      </div>
    </div>
  );
}
