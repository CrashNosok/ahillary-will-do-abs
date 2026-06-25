/** Экран каталога дисциплин (S3.3): список видов спорта, создание нового и
 *  добавление упражнений в библиотеку каждого вида прямо из интерфейса.
 *  Бэкенд — CRUD из S3.1 (виды спорта) и S3.2 (упражнения). */

import { useMemo, useState, type FormEvent } from 'react';
import {
  ApiError,
  SPORT_CATEGORIES,
  sportCategoryLabel,
  type Exercise,
  type Sport,
  type SportCategory,
} from '../lib/api';
import {
  useCreateExercise,
  useCreateSport,
  useExercises,
  useLinkSport,
  useMySports,
  useSportCategories,
  useSports,
  useUnlinkSport,
} from '../lib/sports';

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

function errorMessage(err: unknown): string | null {
  if (err instanceof ApiError) return err.message;
  if (err) return 'Не удалось сохранить. Проверьте, что сервер запущен.';
  return null;
}

export default function SportsPage() {
  // '' = все категории; иначе фильтруем каталог через GET /sports?category= (M1·B15).
  const [filter, setFilter] = useState<SportCategory | ''>('');
  const { data: sports, isPending } = useSports(filter || undefined);
  const { data: categories } = useSportCategories();
  const { data: exercises } = useExercises();
  // Привязанные к себе дисциплины (M2·B19/F6): по ним карточка рисует «Привязать/Отвязать».
  const { data: mySports } = useMySports();
  const linkedIds = useMemo(() => new Set((mySports ?? []).map((s) => s.sport_id)), [mySports]);

  // Группируем упражнения по виду спорта один раз — карточки читают свою группу.
  const bySport = useMemo(() => {
    const map = new Map<number, Exercise[]>();
    for (const ex of exercises ?? []) {
      const list = map.get(ex.sport_id) ?? [];
      list.push(ex);
      map.set(ex.sport_id, list);
    }
    return map;
  }, [exercises]);

  return (
    <section aria-labelledby="sports-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Каталог
        </p>
        <h1 id="sports-heading" className="mt-3 text-display">
          Виды спорта
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Заводите дисциплины и наполняйте их библиотеку упражнений — всё из интерфейса.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        <CreateSportForm />

        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-display">Дисциплины</h2>
            <label className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted">Категория</span>
              <select
                name="category_filter"
                aria-label="Фильтр по категории"
                value={filter}
                onChange={(e) => setFilter(e.target.value as SportCategory | '')}
                className={`${inputCls} py-2 [color-scheme:dark]`}
              >
                <option value="">Все категории</option>
                {(categories ?? []).map((c) => (
                  <option key={c} value={c}>
                    {sportCategoryLabel(c)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {isPending ? (
            <p className="text-muted">Загрузка…</p>
          ) : !sports || sports.length === 0 ? (
            <p className="text-muted">
              {filter
                ? 'В этой категории видов спорта нет.'
                : 'Видов спорта пока нет — создайте первый слева.'}
            </p>
          ) : (
            <ul className="flex flex-col gap-5">
              {sports.map((sport) => (
                <li key={sport.id}>
                  <SportCard
                    sport={sport}
                    exercises={bySport.get(sport.id) ?? []}
                    linked={linkedIds.has(sport.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function CreateSportForm() {
  const create = useCreateSport();
  const [name, setName] = useState('');
  const [category, setCategory] = useState<SportCategory>('strength');
  const [description, setDescription] = useState('');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(
      { name: trimmed, category, description: description.trim() || null },
      {
        onSuccess: () => {
          setName('');
          setCategory('strength');
          setDescription('');
        },
      },
    );
  }

  const error = errorMessage(create.error);

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Новый вид спорта"
      className="flex h-fit flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6"
    >
      <h2 className="text-display">Новый вид спорта</h2>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-muted">Название</span>
        <input
          name="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Калистеника, Бег, Силовая…"
          className={inputCls}
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-muted">Категория</span>
        <select
          name="category"
          value={category}
          onChange={(e) => setCategory(e.target.value as SportCategory)}
          className={`${inputCls} [color-scheme:dark]`}
        >
          {SPORT_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-muted">Описание</span>
        <textarea
          name="description"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Необязательно — пара слов о дисциплине."
          className={`${inputCls} resize-y`}
        />
      </label>

      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={create.isPending}
        className="mt-1 rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {create.isPending ? 'Создаём…' : 'Создать вид спорта'}
      </button>
    </form>
  );
}

function SportCard({
  sport,
  exercises,
  linked,
}: {
  sport: Sport;
  exercises: Exercise[];
  linked: boolean;
}) {
  const link = useLinkSport();
  const unlink = useUnlinkSport();
  const pending = link.isPending || unlink.isPending;
  const toggle = () => (linked ? unlink.mutate(sport.id) : link.mutate({ sport_id: sport.id }));
  const linkError = errorMessage(link.error ?? unlink.error);

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-display text-xl font-semibold tracking-tight">{sport.name}</h3>
        <span className="rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-ink">
          {sportCategoryLabel(sport.category)}
        </span>
        <button
          type="button"
          onClick={toggle}
          disabled={pending}
          aria-pressed={linked}
          className={`ml-auto rounded-full border px-3 py-1 text-sm font-medium transition-colors duration-[var(--duration-fast)] disabled:cursor-not-allowed disabled:opacity-60 ${
            linked
              ? 'border-accent bg-accent/15 text-accent hover:bg-accent/25'
              : 'border-line text-muted hover:border-accent/50 hover:text-fg'
          }`}
        >
          {pending ? '…' : linked ? 'Отвязать' : 'Привязать'}
        </button>
      </div>

      {linkError && (
        <p role="alert" className="text-sm font-medium text-amber">
          {linkError}
        </p>
      )}

      {sport.description && <p className="text-muted">{sport.description}</p>}

      <div className="border-t border-line pt-4">
        <p className="text-sm font-medium text-muted">Упражнения</p>
        {exercises.length === 0 ? (
          <p className="mt-2 text-muted">Упражнений пока нет.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1.5">
            {exercises.map((ex) => (
              <li key={ex.id} className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{ex.name}</span>
                {ex.unit && <span className="text-sm text-muted">· {ex.unit}</span>}
                {ex.notes && <span className="text-sm text-muted">— {ex.notes}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <AddExerciseForm sportId={sport.id} sportName={sport.name} />
    </div>
  );
}

function AddExerciseForm({ sportId, sportName }: { sportId: number; sportName: string }) {
  const create = useCreateExercise();
  const [name, setName] = useState('');
  const [unit, setUnit] = useState('');
  const [notes, setNotes] = useState('');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(
      { sport_id: sportId, name: trimmed, unit: unit.trim() || null, notes: notes.trim() || null },
      {
        onSuccess: () => {
          setName('');
          setUnit('');
          setNotes('');
        },
      },
    );
  }

  const error = errorMessage(create.error);

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label={`Добавить упражнение — ${sportName}`}
      className="flex flex-col gap-3 border-t border-line pt-4"
    >
      <div className="grid gap-3 sm:grid-cols-[1.4fr_0.8fr]">
        <input
          name="exercise_name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Название упражнения"
          aria-label="Название упражнения"
          className={inputCls}
        />
        <input
          name="exercise_unit"
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          placeholder="Единица (кг, повторы…)"
          aria-label="Единица"
          className={inputCls}
        />
      </div>
      <input
        name="exercise_notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Заметка (необязательно)"
        aria-label="Заметка"
        className={inputCls}
      />

      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={create.isPending}
        className="w-fit rounded-xl border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {create.isPending ? 'Добавляем…' : 'Добавить упражнение'}
      </button>
    </form>
  );
}
