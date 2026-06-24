/** Страница «Тренировки» (S3.8): три логгера под одной шапкой — силовая (S3.7),
 *  кардио и скилловые. Вкладки переключают активную форму; каждая форма сама шлёт
 *  свою сессию на бэкенд (POST /workouts, /workouts/cardio, /workouts/skill). */

import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import CardioLoggerForm from './CardioLoggerForm';
import SkillLoggerForm from './SkillLoggerForm';
import StrengthLoggerForm from './StrengthLoggerForm';

const ISO_RE = /^\d{4}-\d{2}-\d{2}$/;

type Tab = 'strength' | 'cardio' | 'skill';

const TABS: { id: Tab; label: string; title: string; intro: string }[] = [
  {
    id: 'strength',
    label: 'Силовая',
    title: 'Логгер силовой',
    intro:
      'Заполняйте подходы построчно: вес, повторы, отдых и RPE. Копируйте строку для серии ' +
      'одинаковых подходов — и сохраняйте всю сессию целиком одной кнопкой.',
  },
  {
    id: 'cardio',
    label: 'Кардио',
    title: 'Логгер кардио',
    intro:
      'Запишите дистанцию, время и пульс пробежки или заезда — средний темп посчитается ' +
      'автоматически из дистанции и времени.',
  },
  {
    id: 'skill',
    label: 'Скилл',
    title: 'Логгер скилловых',
    intro:
      'Отметьте отработанные элементы: число попыток, удачных приземлений и заметку по ' +
      'каждому — вся сессия сохраняется одной кнопкой.',
  },
];

export default function WorkoutLoggerPage({ initialDate }: { initialDate?: string }) {
  const [tab, setTab] = useState<Tab>('strength');
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];
  const navigate = useNavigate();

  // День берём из ?day= (его прокидывает «Расширенный ввод» из попапа календаря), с запасным
  // initialDate-пропом (когда страница встроена во вкладку «Ввод данных»). Если пришли из попапа —
  // показываем «Готово, вернуться ко дню»: /?day=ISO переоткроет попап с уже внесённой тренировкой.
  const [params] = useSearchParams();
  const dayParam = params.get('day');
  const fromDay = dayParam && ISO_RE.test(dayParam) ? dayParam : null;
  const date = initialDate ?? fromDay ?? undefined;

  return (
    <section aria-labelledby="workout-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Тренировки
        </p>
        <h1 id="workout-heading" className="mt-3 text-display">
          {active.title}
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">{active.intro}</p>
      </div>

      <div
        role="tablist"
        aria-label="Тип тренировки"
        className="flex flex-wrap gap-1 self-start rounded-full border border-line bg-surface/60 p-1"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === tab}
            onClick={() => setTab(t.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
              t.id === tab ? 'bg-accent text-accent-ink' : 'text-muted hover:bg-panel hover:text-fg'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'strength' && <StrengthLoggerForm initialDate={date} />}
      {tab === 'cardio' && <CardioLoggerForm initialDate={date} />}
      {tab === 'skill' && <SkillLoggerForm initialDate={date} />}

      {/* Возврат в попап дня — рядом с «Сохранить» формы, чтобы после записи сессии сразу выйти. */}
      {fromDay && (
        <button
          type="button"
          onClick={() => navigate(`/?day=${fromDay}`)}
          className="self-start rounded-xl border border-line px-5 py-3 font-display font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/60 hover:text-accent"
        >
          ← Готово, вернуться ко дню
        </button>
      )}
    </section>
  );
}
