/** Хаб «Ввод данных»: один пункт меню, вкладки на каждый тип данных. Сверху — «Заряд дня»
 *  (анимация заполнения за сегодня). Активная вкладка хранится в URL (?tab=) — это даёт
 *  deep-link, сохранение при рефреше и переход по тапу из «Заряда». Формы не дублируем —
 *  каждая вкладка рендерит существующую самодостаточную страницу. */

import { type ComponentType } from 'react';
import { useSearchParams } from 'react-router-dom';
import ActivityImportPage from './ActivityImportPage';
import BodyMeasurementsPage from './BodyMeasurementsPage';
import BodyPhotosPage from './BodyPhotosPage';
import DayChargeProgress from './DayChargeProgress';
import ImportPage from './ImportPage';
import InbodyImportPage from './InbodyImportPage';
import SportsPage from './SportsPage';
import WeightEntryPage from './WeightEntryPage';
import WorkoutLoggerPage from './WorkoutLoggerPage';

type TabId =
  | 'food'
  | 'activity'
  | 'training'
  | 'measurements'
  | 'weight'
  | 'inbody'
  | 'photos'
  | 'sports';

// Дату выбранного дня (из календаря, ?date=) формы-вкладки берут как стартовую (если умеют).
type EntryTabProps = { initialDate?: string };

// id вкладок «еда/активность/тренировки/замеры» совпадают с CATS в DayChargeProgress —
// так чип «Заряда» уводит ровно на свою вкладку.
const TABS: { id: TabId; label: string; Component: ComponentType<EntryTabProps> }[] = [
  { id: 'food', label: 'Еда', Component: ImportPage },
  { id: 'activity', label: 'Активность', Component: ActivityImportPage },
  { id: 'training', label: 'Тренировки', Component: WorkoutLoggerPage },
  { id: 'measurements', label: 'Замеры', Component: BodyMeasurementsPage },
  { id: 'weight', label: 'Вес', Component: WeightEntryPage },
  { id: 'inbody', label: 'InBody', Component: InbodyImportPage },
  { id: 'photos', label: 'Фото', Component: BodyPhotosPage },
  { id: 'sports', label: 'Виды спорта', Component: SportsPage },
];

const DEFAULT_TAB: TabId = 'food';

function isTabId(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value);
}

const dateBannerFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const ISO_RE = /^\d{4}-\d{2}-\d{2}$/;

export default function DataEntryPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab: TabId = isTabId(raw) ? raw : DEFAULT_TAB;
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];
  const Active = active.Component;

  const dateParam = params.get('date');
  const date = dateParam && ISO_RE.test(dateParam) ? dateParam : undefined;

  // Сохраняем дату при переключении вкладок (чтобы остаться на выбранном дне).
  function pick(id: string) {
    setParams(date ? { tab: id, date } : { tab: id });
  }

  function clearDate() {
    setParams({ tab });
  }

  return (
    <section
      aria-labelledby="data-entry-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Ввод данных
        </p>
        <h1 id="data-entry-heading" className="mt-3 text-display">
          Дневник данных
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Всё в одном месте: еда, активность, тренировки, замеры, вес и фото. Заполняйте день по
          вкладкам — «Заряд дня» подсветит, чего ещё не хватает.
        </p>
      </div>

      <DayChargeProgress onPick={pick} />

      <div
        role="tablist"
        aria-label="Тип данных"
        className="flex flex-wrap gap-1 self-start rounded-2xl border border-line bg-surface/60 p-1 sm:rounded-full"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === tab}
            onClick={() => pick(t.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
              t.id === tab ? 'bg-accent text-accent-ink' : 'text-muted hover:bg-panel hover:text-fg'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {date && (
        <div className="flex flex-wrap items-center gap-3 self-start rounded-full border border-accent/40 bg-accent/10 px-4 py-2 text-sm">
          <span className="font-medium text-fg">
            День: {cap(dateBannerFmt.format(new Date(date + 'T00:00:00')))}
          </span>
          <button
            type="button"
            onClick={clearDate}
            className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted transition-colors duration-[var(--duration-fast)] hover:text-fg"
          >
            Сбросить на сегодня
          </button>
        </div>
      )}

      {/* key=tab+date — пересоздаём активную страницу при смене вкладки/дня (сброс её состояния). */}
      <div key={`${tab}:${date ?? ''}`}>
        <Active initialDate={date} />
      </div>
    </section>
  );
}
