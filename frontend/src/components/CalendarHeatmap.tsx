/** Календарь-«стаканы» (S1.14, переработка): каждый день — стакан, наполняемый 3 ежедневными
 *  категориями (еда/активность/тренировки). Под каждой неделей — «общая чаша» (вес/замеры/фото
 *  + слияние дневных стаканов), а 8-я колонка «Итог» держит медаль недели. «Получить отчёт»
 *  сливает стаканы в чашу, раскрывает медаль (mystery-ball при идеальной неделе) и открывает
 *  отчёт с планом. Данные — GET /dashboard. */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { type DayFlags } from '../lib/api';
import { glowColor, mediaRingShadow } from '../lib/liquid';
import { useDashboard } from '../lib/dashboard';
import { DAILY, WEEKLY, chunkWeeks, weekFill, type MonthCell } from '../lib/weekly';
import { DaySquare } from './calendar/DaySquare';
import { WeeklyCell } from './calendar/WeeklyCell';
import { DayEditorPanel, type EditorRows } from './calendar/DayEditorPanel';
import { WeekMedal } from './calendar/WeekMedal';
import { WeeklyReportPanel, type ReportTarget } from './WeeklyReportPanel';

type EditDay = { iso: string; flags: DayFlags | undefined; title?: string; rows?: EditorRows };

const weekRangeFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const fmtShort = (iso: string) => weekRangeFmt.format(new Date(iso + 'T00:00:00'));

// Неделя с понедельника (ru) + «Нед.» (вес/замеры/фото) + «Итог» (медаль) → сетка из 9 колонок.
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'] as const;

const pad = (n: number) => String(n).padStart(2, '0');
const ISO_RE = /^\d{4}-\d{2}-\d{2}$/;

// Локальный ISO (без UTC-сдвига): new Date(iso) трактует строку как UTC и теряет день.
const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

const firstOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1);

const monthTitleFmt = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Ячейки месяца: ведущие null под смещение первого дня (Пн=0), затем 1..N. */
export function buildMonthCells(monthStart: Date): MonthCell[] {
  const year = monthStart.getFullYear();
  const month = monthStart.getMonth();
  const offset = (new Date(year, month, 1).getDay() + 6) % 7; // Вс(0)→6, Пн(1)→0
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: MonthCell[] = Array(offset).fill(null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ day, iso: toISO(new Date(year, month, day)) });
  }
  return cells;
}

export default function CalendarHeatmap() {
  const [monthStart, setMonthStart] = useState(() => firstOfMonth(new Date()));
  const todayIso = toISO(new Date());

  const start = toISO(monthStart);
  const end = toISO(new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0));
  const { data, isPending, error } = useDashboard(start, end);

  const flagsByDate = useMemo(() => {
    const map = new Map<string, DayFlags>();
    for (const d of data?.days ?? []) map.set(d.date, d);
    return map;
  }, [data]);

  const weeks = useMemo(
    () => chunkWeeks<MonthCell>(buildMonthCells(monthStart), null),
    [monthStart],
  );

  const [report, setReport] = useState<ReportTarget | null>(null);
  const [editDay, setEditDay] = useState<EditDay | null>(null);

  // Возврат из «Расширенного ввода» (S3.11): /?day=ISO переоткрывает попап этого дня. Параметр
  // «съедаем» один раз — как только данные нужного месяца загрузились (флаги уже свежие).
  const [params, setParams] = useSearchParams();
  const [pendingDay, setPendingDay] = useState<string | null>(() => {
    const d = params.get('day');
    return d && ISO_RE.test(d) ? d : null;
  });
  useEffect(() => {
    if (pendingDay) setMonthStart(firstOfMonth(new Date(pendingDay + 'T00:00:00')));
  }, [pendingDay]);
  useEffect(() => {
    if (!pendingDay || isPending) return;
    if (pendingDay < start || pendingDay > end) return; // ждём данных нужного месяца
    setEditDay({ iso: pendingDay, flags: flagsByDate.get(pendingDay), rows: 'daily' });
    setPendingDay(null);
    if (params.get('day')) setParams({}, { replace: true });
  }, [pendingDay, isPending, start, end, flagsByDate, params, setParams]);

  const shiftMonth = (delta: number) =>
    setMonthStart((d) => new Date(d.getFullYear(), d.getMonth() + delta, 1));

  const isCurrentMonth = toISO(monthStart) === toISO(firstOfMonth(new Date()));

  return (
    <section
      aria-labelledby="heatmap-heading"
      className="rounded-[var(--radius-card)] border border-line bg-surface p-4 sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 id="heatmap-heading" className="text-display">
            Календарь
          </h2>
          <p className="mt-1 text-sm text-muted">Жидкости дней · недельная медаль</p>
        </div>

        <div className="flex items-center gap-2">
          {!isCurrentMonth && (
            <button
              type="button"
              onClick={() => setMonthStart(firstOfMonth(new Date()))}
              className="rounded-full border border-line px-3 py-1.5 text-sm font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
            >
              Сегодня
            </button>
          )}
          <button
            type="button"
            aria-label="Предыдущий месяц"
            onClick={() => shiftMonth(-1)}
            className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
          >
            ‹
          </button>
          <span
            data-testid="heatmap-month"
            className="min-w-40 text-center font-display text-lg font-semibold tracking-tight"
            aria-live="polite"
          >
            {cap(monthTitleFmt.format(monthStart))}
          </span>
          <button
            type="button"
            aria-label="Следующий месяц"
            onClick={() => shiftMonth(1)}
            className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors duration-[var(--duration-fast)] hover:border-accent/50 hover:text-fg"
          >
            ›
          </button>
        </div>
      </div>

      <div
        className="mt-6 grid grid-cols-[repeat(8,minmax(0,1fr))_1.7fr] items-start gap-1 sm:gap-1.5"
        role="grid"
        aria-label="Дни месяца"
      >
        {WEEKDAYS.map((w) => (
          <div key={w} className="pb-1 text-center text-xs font-medium uppercase text-muted">
            {w}
          </div>
        ))}
        <div
          className="pb-1 text-center text-[0.6rem] font-medium uppercase text-muted sm:text-xs"
          title="Вес · Замеры · Фото"
        >
          Нед.
        </div>
        <div className="pb-1 text-center text-[0.6rem] font-medium uppercase text-accent sm:text-xs">
          Итог
        </div>

        {weeks.map((week, wi) => (
          <WeekRow
            key={week.find((c) => c)?.iso ?? `w-${wi}`}
            week={week}
            flagsByDate={flagsByDate}
            todayIso={todayIso}
            onOpenReport={setReport}
            onOpenDay={setEditDay}
          />
        ))}
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm font-medium text-amber">
          Не удалось загрузить данные. Проверьте, что сервер запущен.
        </p>
      )}
      {isPending && !error && <p className="mt-4 text-sm text-muted">Загрузка…</p>}

      <Legend />

      {report && <WeeklyReportPanel target={report} onClose={() => setReport(null)} />}
      {editDay && (
        <DayEditorPanel
          iso={editDay.iso}
          flags={editDay.flags}
          title={editDay.title}
          rows={editDay.rows}
          onClose={() => setEditDay(null)}
        />
      )}
    </section>
  );
}

/** Строка одной недели: 7 дневных ячеек-жидкостей + недельная ячейка (вес/замеры/фото) +
 *  колонка «Итог» с медалью и кнопкой «Получить отчёт». Медаль завершившейся недели крутится;
 *  клик по ней или по кнопке открывает отчёт. Возвращает фрагмент grid-детей. */
function WeekRow({
  week,
  flagsByDate,
  todayIso,
  onOpenReport,
  onOpenDay,
}: {
  week: MonthCell[];
  flagsByDate: Map<string, DayFlags>;
  todayIso: string;
  onOpenReport: (t: ReportTarget) => void;
  onOpenDay: (d: EditDay) => void;
}) {
  const realCells = week.filter((c): c is { day: number; iso: string } => c !== null);
  const flagsList = realCells
    .map((c) => flagsByDate.get(c.iso))
    .filter((f): f is DayFlags => f !== undefined);

  const fill = weekFill(flagsList);
  const weekStart = realCells[0]?.iso ?? '';
  const weekEnd = realCells[realCells.length - 1]?.iso ?? '';
  const weekEnded = weekEnd !== '' && weekEnd < todayIso; // неделя завершилась → медаль крутится

  // Недельная ячейка «раз в неделю»: есть ли за неделю вес/замеры/фото.
  const weeklyFlags = {
    has_weight: flagsList.some((d) => d.has_weight),
    has_body: flagsList.some((d) => d.has_body),
    has_photo: flagsList.some((d) => d.has_photo),
  };
  const isCurrentWeek = weekStart !== '' && weekStart <= todayIso && todayIso <= weekEnd;
  const weeklyDate = weekStart === '' ? todayIso : weekEnd <= todayIso ? weekEnd : todayIso;
  const weekRangeLabel =
    weekStart && weekEnd ? `Неделя ${fmtShort(weekStart)} – ${fmtShort(weekEnd)}` : 'Неделя';
  const weekShort = weekStart && weekEnd ? `${fmtShort(weekStart)}–${fmtShort(weekEnd)}` : '';

  const openReport = () => onOpenReport({ weekStart, weekEnd, days: flagsList, fill });
  const openWeekly = () =>
    onOpenDay({
      iso: weeklyDate,
      title: weekRangeLabel,
      rows: 'weekly',
      flags: {
        date: weeklyDate,
        has_food: false,
        has_activity: false,
        has_training: false,
        has_measurement: weeklyFlags.has_weight || weeklyFlags.has_body,
        has_weight: weeklyFlags.has_weight,
        has_body: weeklyFlags.has_body,
        has_photo: weeklyFlags.has_photo,
        has_surpassed_self: false,
        has_workout_media: false,
        has_full_measurements: weeklyFlags.has_weight && weeklyFlags.has_body,
      },
    });

  return (
    <>
      {week.map((cell, i) =>
        cell === null ? (
          <div key={`pad-${weekStart}-${i}`} aria-hidden="true" />
        ) : (
          <DaySquare
            key={cell.iso}
            day={cell.day}
            iso={cell.iso}
            flags={flagsByDate.get(cell.iso)}
            isToday={cell.iso === todayIso}
            onSelect={() =>
              onOpenDay({ iso: cell.iso, flags: flagsByDate.get(cell.iso), rows: 'daily' })
            }
          />
        ),
      )}
      <WeeklyCell
        weeklyFlags={weeklyFlags}
        isCurrentWeek={isCurrentWeek}
        onSelect={realCells.length > 0 ? openWeekly : undefined}
      />
      <WeekMedal
        overall={fill.overall}
        ended={weekEnded}
        short={weekShort}
        id={weekStart || `w-${weekEnd}`}
        onOpenReport={openReport}
      />
    </>
  );
}

function Legend() {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-4 text-sm text-muted">
      <span className="text-xs font-semibold uppercase tracking-wide text-fg">День:</span>
      {DAILY.map((c) => (
        <span key={c.key} className="flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-full"
            style={{ background: c.color }}
            aria-hidden="true"
          />
          {c.label}
        </span>
      ))}
      <span className="ml-2 text-xs font-semibold uppercase tracking-wide text-fg">Неделя:</span>
      {WEEKLY.map((c) => (
        <span key={c.key} className="flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-full"
            style={{ background: c.color }}
            aria-hidden="true"
          />
          {c.label}
        </span>
      ))}
      {/* Бонус-визуалы дня: ярче+искры = личный рекорд (F16), золотое кольцо = медиа (F17).
          Свотчи берут те же helpers, что и сама ячейка, — цвета совпадают побуквенно. */}
      <span className="ml-2 text-xs font-semibold uppercase tracking-wide text-fg">Бонус:</span>
      <span className="flex items-center gap-1.5">
        <span
          className="size-2.5 rounded-full"
          style={{ background: glowColor(false), boxShadow: `0 0 6px 1px ${glowColor(false)}` }}
          aria-hidden="true"
        />
        ярче — превзошёл себя
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className="size-2.5 rounded-full bg-surface"
          style={{ boxShadow: mediaRingShadow() }}
          aria-hidden="true"
        />
        кольцо — медиа тренировки
      </span>
    </div>
  );
}
