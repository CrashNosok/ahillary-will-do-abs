/** Экран каталога дисциплин (S3.3): список видов спорта, создание нового и
 *  добавление упражнений в библиотеку каждого вида прямо из интерфейса.
 *  Бэкенд — CRUD из S3.1 (виды спорта) и S3.2 (упражнения). */

import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
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
  useCreateSuggestion,
  useExercises,
  useLinkSport,
  useMySports,
  useSportCategories,
  useSports,
  useSuggestions,
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

  // «Рекомендуем попробовать»: основные (is_global) виды, которые ещё НЕ привязаны. Берём весь
  // каталог (без фильтра категории) — фильтр ниже только для списка «Все дисциплины».
  const { data: allSports } = useSports();
  const recommended = useMemo(
    () => (allSports ?? []).filter((s) => s.is_global && !linkedIds.has(s.id)),
    [allSports, linkedIds],
  );

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
          Привязывайте дисциплины, пробуйте новое из рекомендаций, предлагайте недостающее.
        </p>
      </div>

      <RecommendedToTry sports={recommended} />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        <SuggestSportForm />

        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-display">Все дисциплины</h2>
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
                : 'Видов спорта пока нет — предложите первый слева.'}
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

const statusLabel = (s: string): string =>
  ({ pending: 'на ревью', approved: 'добавлен', rejected: 'отклонён' })[s] ?? s;

/** «Рекомендуем попробовать»: основные виды, которые юзер ещё не привязал — карточки с быстрым
 *  «Попробовать» (привязать). Пусто (всё привязано) → секцию не показываем. */
function RecommendedToTry({ sports }: { sports: Sport[] }) {
  if (sports.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-display">Рекомендуем попробовать</h2>
      <p className="text-muted">Основные дисциплины, которые вы ещё не привязали.</p>
      <ul className="flex flex-wrap gap-3">
        {sports.map((s) => (
          <li key={s.id}>
            <RecommendedCard sport={s} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecommendedCard({ sport }: { sport: Sport }) {
  const link = useLinkSport();
  return (
    <div className="flex max-w-xs flex-col gap-2 rounded-2xl border border-line bg-gradient-to-br from-panel to-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          to={`/sports/${sport.id}`}
          className="font-display font-semibold tracking-tight transition-colors duration-[var(--duration-fast)] hover:text-accent"
        >
          {sport.name}
        </Link>
        <span className="rounded-full bg-accent/15 px-2.5 py-0.5 text-xs font-medium text-accent">
          {sportCategoryLabel(sport.category)}
        </span>
      </div>
      {sport.description && <p className="text-sm text-muted">{sport.description}</p>}
      <button
        type="button"
        onClick={() => link.mutate({ sport_id: sport.id })}
        disabled={link.isPending}
        className="w-fit rounded-full border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:bg-accent/20 disabled:opacity-60"
      >
        {link.isPending ? '…' : 'Попробовать (привязать)'}
      </button>
    </div>
  );
}

/** «Предложить вид спорта» — заявка на ревью (если нужного нет в каталоге). Под формой — свои
 *  заявки со статусом. Заявка НЕ создаёт вид сразу (решение пользователя: очередь на ревью). */
function SuggestSportForm() {
  const suggest = useCreateSuggestion();
  const { data: suggestions } = useSuggestions();
  const [name, setName] = useState('');
  const [category, setCategory] = useState<SportCategory | ''>('');
  const [note, setNote] = useState('');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    suggest.mutate(
      { name: trimmed, category: category || null, note: note.trim() || null },
      {
        onSuccess: () => {
          setName('');
          setCategory('');
          setNote('');
        },
      },
    );
  }

  const error = errorMessage(suggest.error);

  return (
    <div className="flex h-fit flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <form
        onSubmit={onSubmit}
        noValidate
        aria-label="Предложить вид спорта"
        className="flex flex-col gap-5"
      >
        <div>
          <h2 className="text-display">Предложить вид спорта</h2>
          <p className="mt-2 text-sm text-muted">
            Нет нужного? Отправьте заявку — добавим после проверки.
          </p>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Название</span>
          <input
            name="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Сквош, гребля, скалолазание…"
            className={inputCls}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Категория (если знаете)</span>
          <select
            name="category"
            value={category}
            onChange={(e) => setCategory(e.target.value as SportCategory | '')}
            className={`${inputCls} [color-scheme:dark]`}
          >
            <option value="">Не уверен</option>
            {SPORT_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Комментарий</span>
          <textarea
            name="note"
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Необязательно — что за вид, почему нужен."
            className={`${inputCls} resize-y`}
          />
        </label>

        {error && (
          <p role="alert" className="text-sm font-medium text-amber">
            {error}
          </p>
        )}
        {suggest.isSuccess && (
          <p role="status" className="text-sm font-medium text-accent">
            Заявка отправлена — спасибо!
          </p>
        )}

        <button
          type="submit"
          disabled={suggest.isPending}
          className="mt-1 rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {suggest.isPending ? 'Отправляем…' : 'Предложить'}
        </button>
      </form>

      {suggestions && suggestions.length > 0 && (
        <div className="border-t border-line pt-4">
          <p className="text-sm font-medium text-muted">Мои заявки</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {suggestions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="font-medium">{s.name}</span>
                {s.category && (
                  <span className="text-muted">· {sportCategoryLabel(s.category)}</span>
                )}
                <span className="ml-auto rounded-full border border-line px-2 py-0.5 text-xs text-muted">
                  {statusLabel(s.status)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
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
        <h3 className="font-display text-xl font-semibold tracking-tight">
          <Link
            to={`/sports/${sport.id}`}
            className="transition-colors duration-[var(--duration-fast)] hover:text-accent"
          >
            {sport.name}
          </Link>
        </h3>
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
