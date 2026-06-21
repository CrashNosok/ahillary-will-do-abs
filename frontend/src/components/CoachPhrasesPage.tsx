/** Редактор фраз коуча (S5.10): просмотр и правка реплик по категориям прямо из UI.
 *
 *  Источник — эффективный набор фраз (дефолты + правки в localStorage, см. lib/coach).
 *  Правишь черновик → «Сохранить» пишет его в localStorage → дашбордный коуч и превью
 *  ниже читают тот же набор, поэтому правка сразу применяется. Превью показывает, что
 *  коуч скажет в каждом состоянии ИМЕННО по сохранённому набору (не по черновику) —
 *  это и есть честная проверка «правка применилась». */

import { useState } from 'react';
import {
  daySeed,
  loadPhrases,
  MOOD_HINTS,
  MOOD_LABELS,
  MOODS,
  pickPhrase,
  savePhrases,
  type CoachMood,
  type PhraseMap,
} from '../lib/coach';

const inputCls =
  'w-full rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

// Без библиотеки сравнения: набор маленький, JSON-строка — достаточный детектор грязи.
const isEqual = (a: PhraseMap, b: PhraseMap): boolean => JSON.stringify(a) === JSON.stringify(b);

export default function CoachPhrasesPage() {
  // Ленивая инициализация: читаем localStorage один раз при монтировании.
  const [draft, setDraft] = useState<PhraseMap>(loadPhrases);
  const [saved, setSaved] = useState<PhraseMap>(draft);

  const dirty = !isEqual(draft, saved);
  const seed = daySeed();

  function setPhrase(mood: CoachMood, idx: number, value: string) {
    setDraft((d) => ({ ...d, [mood]: d[mood].map((p, i) => (i === idx ? value : p)) }));
  }

  function addPhrase(mood: CoachMood) {
    setDraft((d) => ({ ...d, [mood]: [...d[mood], ''] }));
  }

  function removePhrase(mood: CoachMood, idx: number) {
    setDraft((d) => ({ ...d, [mood]: d[mood].filter((_, i) => i !== idx) }));
  }

  function onSave() {
    const persisted = savePhrases(draft);
    setSaved(persisted);
    setDraft(persisted); // отразить санацию: пустые строки выброшены
  }

  return (
    <section
      aria-labelledby="coach-phrases-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Коуч
        </p>
        <h1 id="coach-phrases-heading" className="mt-3 text-display">
          Фразы коуча
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Реплики совы на дашборде — по категориям состояния дня. Меняйте текст, добавляйте и
          удаляйте фразы; после «Сохранить» коуч заговорит по-новому.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {MOODS.map((mood) => (
          <CategoryCard
            key={mood}
            mood={mood}
            phrases={draft[mood]}
            preview={pickPhrase(mood, seed, saved)}
            onChange={(idx, value) => setPhrase(mood, idx, value)}
            onAdd={() => addPhrase(mood)}
            onRemove={(idx) => removePhrase(mood, idx)}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty}
          data-testid="save-phrases"
          className="rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Сохранить
        </button>
        <span aria-live="polite" className="text-sm text-muted">
          {dirty ? 'Есть несохранённые правки' : 'Всё сохранено'}
        </span>
      </div>
    </section>
  );
}

function CategoryCard({
  mood,
  phrases,
  preview,
  onChange,
  onAdd,
  onRemove,
}: {
  mood: CoachMood;
  phrases: string[];
  preview: string;
  onChange: (idx: number, value: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
}) {
  const label = MOOD_LABELS[mood];
  const canRemove = phrases.length > 1;

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-display text-xl font-semibold tracking-tight">{label}</h2>
          <span className="rounded-full bg-panel px-3 py-1 text-sm text-muted">
            {phrases.length} фраз
          </span>
        </div>
        <p className="mt-1 text-sm text-muted">{MOOD_HINTS[mood]}</p>
      </div>

      <ul className="flex flex-col gap-2.5">
        {phrases.map((phrase, idx) => (
          <li key={idx} className="flex items-start gap-2">
            <input
              value={phrase}
              onChange={(e) => onChange(idx, e.target.value)}
              aria-label={`${label} — фраза ${idx + 1}`}
              placeholder="Текст фразы"
              className={inputCls}
            />
            <button
              type="button"
              onClick={() => onRemove(idx)}
              disabled={!canRemove}
              aria-label={`Удалить фразу ${idx + 1} — ${label}`}
              title={canRemove ? 'Удалить фразу' : 'Нужна хотя бы одна фраза'}
              className="shrink-0 rounded-xl border border-line px-3 py-2.5 text-sm font-medium text-muted transition-colors duration-[var(--duration-fast)] hover:border-amber/60 hover:text-amber disabled:cursor-not-allowed disabled:opacity-40"
            >
              Удалить
            </button>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={onAdd}
        className="w-fit rounded-xl border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50"
      >
        + Добавить фразу
      </button>

      <p className="border-t border-line pt-4 text-sm text-muted">
        Сейчас коуч скажет:{' '}
        <span data-testid={`preview-${mood}`} className="text-fg">
          «{preview}»
        </span>
      </p>
    </div>
  );
}
