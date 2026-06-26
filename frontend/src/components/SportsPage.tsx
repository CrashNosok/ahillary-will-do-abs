/** Каталог дисциплин: единый список ВСЕХ видов спорта одинаковыми простыми карточками
 *  (название · категория · мини-описание · Привязать/Отвязать) + «Предложить вид спорта» снизу.
 *  Упражнения живут на странице вида (/sports/:id), а не в каталоге. */

import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  SPORT_CATEGORIES,
  sportCategoryLabel,
  type Sport,
  type SportCategory,
} from '../lib/api';
import {
  useCreateSuggestion,
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

const statusLabel = (s: string): string =>
  ({ pending: 'на ревью', approved: 'добавлен', rejected: 'отклонён' })[s] ?? s;

export default function SportsPage() {
  // '' = все категории; иначе фильтруем каталог через GET /sports?category= (M1·B15).
  const [filter, setFilter] = useState<SportCategory | ''>('');
  const { data: sports, isPending } = useSports(filter || undefined);
  const { data: categories } = useSportCategories();
  // Привязанные дисциплины (M2·B19): карточка по ним рисует Привязать/Отвязать.
  const { data: mySports } = useMySports();
  const linkedIds = useMemo(() => new Set((mySports ?? []).map((s) => s.sport_id)), [mySports]);

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
          Все дисциплины приложения. Привязывайте к себе те, что ведёте; нет нужной — предложите её
          внизу. Упражнения дисциплины — на её странице.
        </p>
      </div>

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
              : 'Видов спорта пока нет — предложите первый ниже.'}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sports.map((sport) => (
              <li key={sport.id}>
                <SportCard sport={sport} linked={linkedIds.has(sport.id)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <SuggestSportForm />
    </section>
  );
}

/** Простая карточка вида спорта (единый дизайн): имя (→ /sports/:id) · категория (нейтральный
 *  чип, цвет ≠ кнопки) · мини-описание · Привязать/Отвязать. */
function SportCard({ sport, linked }: { sport: Sport; linked: boolean }) {
  const link = useLinkSport();
  const unlink = useUnlinkSport();
  const pending = link.isPending || unlink.isPending;
  const toggle = () => (linked ? unlink.mutate(sport.id) : link.mutate({ sport_id: sport.id }));
  const error = errorMessage(link.error ?? unlink.error);

  return (
    <div className="flex h-full flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            to={`/sports/${sport.id}`}
            className="font-display text-lg font-semibold tracking-tight transition-colors duration-[var(--duration-fast)] hover:text-accent"
          >
            {sport.name}
          </Link>
          {/* Категория — нейтральный чип (НЕ акцентный, чтобы цвет не совпадал с кнопкой). */}
          <span className="w-fit rounded-full border border-line bg-ink/30 px-2.5 py-0.5 text-xs font-medium text-muted">
            {sportCategoryLabel(sport.category)}
          </span>
        </div>
        <button
          type="button"
          onClick={toggle}
          disabled={pending}
          aria-pressed={linked}
          className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-[var(--duration-fast)] disabled:cursor-not-allowed disabled:opacity-60 ${
            linked
              ? 'border-accent bg-accent/15 text-accent hover:bg-accent/25'
              : 'border-accent/50 bg-accent/10 text-accent hover:bg-accent/20'
          }`}
        >
          {pending ? '…' : linked ? 'Отвязать' : 'Привязать'}
        </button>
      </div>

      {sport.description && (
        <p className="text-sm leading-relaxed text-muted">{sport.description}</p>
      )}
      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}
    </div>
  );
}

/** «Предложить вид спорта» — заявка на ревью (если нужного нет). Под формой — свои заявки со
 *  статусом. Заявка НЕ создаёт вид сразу (решение: очередь на ревью). */
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
    <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6 lg:max-w-xl">
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

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-muted">Название</span>
            <input
              name="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Сквош, гребля…"
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
        </div>

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
          className="mt-1 w-fit rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
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
