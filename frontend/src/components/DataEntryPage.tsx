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
import GoalPage from './GoalPage';
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
  | 'sports'
  | 'goal';

// id вкладок «еда/активность/тренировки/замеры» совпадают с CATS в DayChargeProgress —
// так чип «Заряда» уводит ровно на свою вкладку.
const TABS: { id: TabId; label: string; Component: ComponentType }[] = [
  { id: 'food', label: 'Еда', Component: ImportPage },
  { id: 'activity', label: 'Активность', Component: ActivityImportPage },
  { id: 'training', label: 'Тренировки', Component: WorkoutLoggerPage },
  { id: 'measurements', label: 'Замеры', Component: BodyMeasurementsPage },
  { id: 'weight', label: 'Вес', Component: WeightEntryPage },
  { id: 'inbody', label: 'InBody', Component: InbodyImportPage },
  { id: 'photos', label: 'Фото', Component: BodyPhotosPage },
  { id: 'sports', label: 'Виды спорта', Component: SportsPage },
  { id: 'goal', label: 'Цель', Component: GoalPage },
];

const DEFAULT_TAB: TabId = 'food';

function isTabId(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value);
}

export default function DataEntryPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab: TabId = isTabId(raw) ? raw : DEFAULT_TAB;
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];
  const Active = active.Component;

  function pick(id: string) {
    setParams({ tab: id });
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

      {/* key=tab — пересоздаём активную страницу при смене вкладки (сброс её локального состояния). */}
      <div key={tab}>
        <Active />
      </div>
    </section>
  );
}
