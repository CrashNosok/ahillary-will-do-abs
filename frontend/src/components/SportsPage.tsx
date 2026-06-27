/** Каталог дисциплин: «Мои виды спорта» (привязанные) наверху, ниже «Каталог» (остальные) с
 *  фильтром по категории; привязал → переехал наверх. Карточки одинаковые (имя · нейтральный чип
 *  категории · мини-описание · кнопка-тоггл Привязать/Привязан→Отвязать). «Предложить вид спорта»
 *  — внизу. Упражнения — на странице вида (/sports/:id). */

import { useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  SPORT_CATEGORIES,
  sportCategoryLabel,
  type Sport,
  type SportCategory,
  type SportSummary,
} from '../lib/api';
import {
  useCreateSuggestion,
  useLinkSport,
  useMySports,
  useSportCategories,
  useSports,
  useSportSummaries,
  useSuggestions,
  useUnlinkSport,
} from '../lib/sports';

const ZERO_SUMMARY: Omit<SportSummary, 'sport_id'> = {
  levels: 0,
  events: 0,
  mentors: 0,
  challenges: 0,
  exercises: 0,
  achievements_total: 0,
  achievements_unlocked: 0,
  workouts: 0,
  current_level: null,
  linked: false,
};

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

// 2 карточки в ряд (а не 3) — карточки шире, влезает полезная сводка.
const cardGridCls = 'grid gap-5 md:grid-cols-2';

// Визуальный «характер» категории: эмодзи + тон (oklch hue) для значка/акцента/свечения карточки.
// Один источник правды — чтобы каждая дисциплина выглядела по-своему и «хотелось тыкнуть».
const CATEGORY_META: Record<SportCategory, { icon: string; hue: number }> = {
  strength: { icon: '🏋️', hue: 35 },
  endurance: { icon: '🏃', hue: 150 },
  combat: { icon: '🥊', hue: 20 },
  team: { icon: '⚽', hue: 255 },
  racket: { icon: '🎾', hue: 115 },
  action: { icon: '🪂', hue: 320 },
  precision: { icon: '🎯', hue: 200 },
  artistic: { icon: '🤸', hue: 350 },
  other: { icon: '⭐', hue: 90 },
};
const categoryMeta = (c: SportCategory) => CATEGORY_META[c] ?? CATEGORY_META.other;
const hueColor = (hue: number, l = 80, c = 0.14) => `oklch(${l}% ${c} ${hue})`;

function errorMessage(err: unknown): string | null {
  if (err instanceof ApiError) return err.message;
  if (err) return 'Не удалось сохранить. Проверьте, что сервер запущен.';
  return null;
}

const statusLabel = (s: string): string =>
  ({ pending: 'на ревью', approved: 'добавлен', rejected: 'отклонён' })[s] ?? s;

export default function SportsPage() {
  const [filter, setFilter] = useState<SportCategory | ''>('');
  // Тянем ВСЕ виды + сводку (счётчики/прогресс) и делим на клиенте: «мои» (привязанные ИЛИ с
  // прогрессом) и каталог (остальные). Фильтр категории — только к каталогу.
  const { data: allSports, isPending } = useSports();
  const { data: categories } = useSportCategories();
  const { data: mySports } = useMySports();
  const { data: summaries } = useSportSummaries();
  const linkedIds = useMemo(() => new Set((mySports ?? []).map((s) => s.sport_id)), [mySports]);
  const summaryById = useMemo(() => {
    const m = new Map<number, SportSummary>();
    for (const s of summaries ?? []) m.set(s.sport_id, s);
    return m;
  }, [summaries]);
  const summaryOf = (id: number): SportSummary =>
    summaryById.get(id) ?? { sport_id: id, ...ZERO_SUMMARY };

  // «Мои виды спорта» = привязан ИЛИ есть прогресс (ачивки/тренировки/уровень) — прогресс не
  // сбрасывается при отвязке (мягкая отвязка хранит уровень) и продолжает показываться здесь же.
  const isMine = (s: Sport) => {
    const sum = summaryOf(s.id);
    return (
      linkedIds.has(s.id) ||
      sum.achievements_unlocked > 0 ||
      sum.workouts > 0 ||
      sum.current_level != null
    );
  };
  const mine = useMemo(() => (allSports ?? []).filter(isMine), [allSports, linkedIds, summaryById]);
  const catalog = useMemo(
    () => (allSports ?? []).filter((s) => !isMine(s) && (!filter || s.category === filter)),
    [allSports, linkedIds, summaryById, filter],
  );

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
          Привязанные дисциплины — вверху. Из каталога ниже добавляйте новые; нет нужной —
          предложите её. Упражнения дисциплины — на её странице.
        </p>
      </div>

      {/* Мои виды спорта (привязанные) — всегда наверху. */}
      <div className="flex flex-col gap-5">
        <h2 className="text-display">Мои виды спорта</h2>
        {mine.length === 0 ? (
          <p className="text-muted">Пока ничего не привязано — выберите из каталога ниже.</p>
        ) : (
          <ul className={cardGridCls}>
            {mine.map((sport) => (
              <li key={sport.id}>
                <SportCard
                  sport={sport}
                  linked={linkedIds.has(sport.id)}
                  summary={summaryOf(sport.id)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Каталог (непривязанные) + фильтр категории. */}
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-display">Каталог</h2>
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
        ) : catalog.length === 0 ? (
          <p className="text-muted">
            {filter
              ? 'В этой категории непривязанных видов нет.'
              : mine.length > 0
                ? 'Все виды уже привязаны 🎉 Нет нужного — предложите ниже.'
                : 'Видов спорта пока нет — предложите первый ниже.'}
          </p>
        ) : (
          <ul className={cardGridCls}>
            {catalog.map((sport) => (
              <li key={sport.id}>
                <SportCard sport={sport} linked={false} summary={summaryOf(sport.id)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <SuggestSportForm />
    </section>
  );
}

/** Карточка вида спорта — единый шаблон (одинаковое тело в «Мои» и каталоге, отличаются лишь
 *  данными): описание · текущий уровень (нулевой по умолчанию) · полоса достижений (0 по
 *  умолчанию) · сетка из 4 метрик с цветовым кодом. Категория задаёт тон (значок-медальон +
 *  угловое свечение + акценты через CSS-var --cat), карточка приподнимается на ховере и целиком
 *  кликабельна. Кнопка-тоггл: не привязан → «Привязать»; привязан → «✓ Привязан», на ховере
 *  краснеет в «Отвязать». */
function SportCard({
  sport,
  linked,
  summary,
}: {
  sport: Sport;
  linked: boolean;
  summary: SportSummary;
}) {
  const link = useLinkSport();
  const unlink = useUnlinkSport();
  const pending = link.isPending || unlink.isPending;
  const toggle = () => (linked ? unlink.mutate(sport.id) : link.mutate({ sport_id: sport.id }));
  const error = errorMessage(link.error ?? unlink.error);
  const meta = categoryMeta(sport.category);
  const style = { '--cat': hueColor(meta.hue) } as CSSProperties;

  return (
    <article
      style={style}
      className="group/card relative isolate flex h-full cursor-pointer flex-col gap-4 overflow-hidden rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-5 transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-1 hover:border-[var(--cat)] hover:shadow-[0_22px_50px_-24px_var(--cat)]"
    >
      {/* Атмосфера категории: мягкое свечение в углу + тонкая верхняя полоса. -z-10 + isolate
          держат их за контентом, не перехватывая клики (вся карточка кликабельна — см. ниже). */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-16 -z-10 size-44 rounded-full opacity-25 blur-3xl transition-opacity duration-[var(--duration-normal)] group-hover/card:opacity-50"
        style={{ background: 'var(--cat)' }}
      />
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-1"
        style={{ background: 'linear-gradient(90deg, transparent, var(--cat), transparent)' }}
      />

      {/* Шапка: медальон-значок · имя + категория (микроподпись) · кнопка-тоггл. Шапка НЕ
          positioned — чтобы растянутая ссылка имени (after:inset-0) покрыла всю карточку. */}
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="grid size-12 shrink-0 place-items-center rounded-2xl border border-[var(--cat)]/40 text-2xl"
          style={{
            background:
              'radial-gradient(120% 120% at 30% 20%, color-mix(in oklch, var(--cat) 38%, transparent), transparent 70%)',
          }}
        >
          {meta.icon}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {/* Растянутая ссылка: ::after покрывает всю карточку → клик в любом месте ведёт на
              страницу вида, курсор — pointer. Интерактив выше (кнопка) поднят z-10. */}
          <Link
            to={`/sports/${sport.id}`}
            className="font-display text-xl font-bold leading-tight tracking-tight transition-colors duration-[var(--duration-fast)] after:absolute after:inset-0 after:content-[''] hover:text-[var(--cat)]"
          >
            {sport.name}
          </Link>
          <span className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted">
            {sportCategoryLabel(sport.category)}
          </span>
        </div>
        {linked ? (
          <button
            type="button"
            onClick={toggle}
            disabled={pending}
            aria-pressed
            title="Нажмите, чтобы отвязать"
            className="group/link relative z-10 inline-flex shrink-0 items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:border-red-400/50 hover:bg-red-500/10 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? (
              '…'
            ) : (
              <>
                <span className="group-hover/link:hidden">✓ Привязан</span>
                <span className="hidden group-hover/link:inline">Отвязать</span>
              </>
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={toggle}
            disabled={pending}
            aria-pressed={false}
            className="relative z-10 shrink-0 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition-opacity duration-[var(--duration-fast)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? '…' : 'Привязать'}
          </button>
        )}
      </div>

      {/* Описание — фиксированный блок ровно в 3 строки (min-h 3lh + обрезка), чтобы карточки
          с описанием на 1 и на 3 строки были одной высоты. */}
      <p className="line-clamp-3 min-h-[3lh] text-sm leading-relaxed text-muted">
        {sport.description}
      </p>

      {/* Тело — единое: уровень (нулевой по умолчанию) + достижения + метрики с цветовым кодом. */}
      <CardBody s={summary} />

      {error && (
        <p role="alert" className="relative z-10 text-sm font-medium text-amber">
          {error}
        </p>
      )}

      {/* Призыв открыть — декоративный (вся карточка уже ссылка); стрелка уезжает на ховере. */}
      <span className="mt-auto inline-flex w-fit items-center gap-1 pt-1 text-sm font-semibold text-[var(--cat)]">
        Открыть
        <span className="transition-transform duration-[var(--duration-fast)] group-hover/card:translate-x-1">
          →
        </span>
      </span>
    </article>
  );
}

/** Метрики дисциплины: ключ суммы · значок · подпись · тон (oklch hue) для цветового кода.
 *  Свой цвет/иконка у каждой → глаз цепляется и считывает мгновенно, а не читает колонку чисел.
 *  ВАЖНО (скоуп данных): «Мои тренировки» — личный счётчик (по user_id), а упражнения/события/
 *  челленджи — это ОБЩИЙ каталог дисциплины (не «мои»). Поэтому они разделены: личное наверху,
 *  каталожное — под подписью «В каталоге», чтобы число челленджей не читалось как «мои». */
type MetricMeta = { key: keyof SportSummary; icon: string; label: string; hue: number };
const PERSONAL_METRICS = [
  { key: 'workouts', icon: '🏋️', label: 'Мои тренировки', hue: 255 },
] as const satisfies readonly MetricMeta[];
const CATALOG_METRICS = [
  { key: 'exercises', icon: '🤸', label: 'Упражнения', hue: 145 },
  { key: 'events', icon: '📅', label: 'События', hue: 70 },
  { key: 'challenges', icon: '🔥', label: 'Челленджи', hue: 330 },
] as const satisfies readonly MetricMeta[];

/** Одна метрика: цветной значок + крупное число + подпись. Цвет и иконка — мгновенное узнавание. */
function MetricCell({
  icon,
  label,
  value,
  hue,
}: {
  icon: string;
  label: string;
  value: number;
  hue: number;
}) {
  const style = { '--m': hueColor(hue) } as CSSProperties;
  return (
    <div
      style={style}
      className="flex items-center gap-2.5 rounded-xl border border-[var(--m)]/25 bg-[var(--m)]/8 px-3 py-2.5"
    >
      <span
        aria-hidden
        className="grid size-9 shrink-0 place-items-center rounded-lg bg-[var(--m)]/15 text-base"
      >
        {icon}
      </span>
      <div className="flex min-w-0 flex-col leading-none">
        <span className="font-display text-xl font-bold tabular-nums text-fg">{value}</span>
        <span className="truncate text-[0.65rem] font-medium uppercase tracking-wide text-muted">
          {label}
        </span>
      </div>
    </div>
  );
}

/** Тело карточки (единое для «Мои» и каталога; отличаются лишь данными):
 *   - текущий уровень — есть всегда, «Нулевой» нейтральным тоном, реальный — в тоне категории;
 *   - достижения — полоса выполнено/всего (0 по умолчанию), без кубков (число и шкала и так всё
 *     показывают);
 *   - сетка из 4 метрик с цветовым кодом (тренировки/упражнения/события/челленджи). */
function CardBody({ s }: { s: SportSummary }) {
  const hasLevel = !!s.current_level;
  const hasAch = s.achievements_total > 0;
  const pct = hasAch ? Math.round((s.achievements_unlocked / s.achievements_total) * 100) : 0;
  const allDone = hasAch && s.achievements_unlocked === s.achievements_total;

  return (
    <div className="flex flex-col gap-3">
      {/* Уровень — на каждой карточке; «Нулевой» нейтрально, реальный — в тоне категории. */}
      <span
        className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
          hasLevel ? 'border-[var(--cat)]/45 bg-[var(--cat)]/12' : 'border-line bg-ink/40'
        }`}
      >
        <span aria-hidden>🎖</span>
        <span className="text-muted">Уровень:</span>
        <span className={`font-bold ${hasLevel ? 'text-[var(--cat)]' : 'text-fg'}`}>
          {s.current_level ?? 'Нулевой'}
        </span>
      </span>

      {/* Достижения — подпись + число (0 по умолчанию) + полоса прогресса. */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold uppercase tracking-wide text-muted">Достижения</span>
          <span className="font-display text-sm font-bold tabular-nums text-fg">
            {allDone ? (
              <span className="text-accent">Всё открыто ✨</span>
            ) : hasAch ? (
              <>
                {s.achievements_unlocked}
                <span className="text-muted">/{s.achievements_total}</span>
              </>
            ) : (
              '0'
            )}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Достижения"
          aria-valuemin={0}
          aria-valuemax={s.achievements_total}
          aria-valuenow={s.achievements_unlocked}
          className="h-2 overflow-hidden rounded-full bg-ink shadow-inner"
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-[var(--cat)] to-accent transition-[width] duration-[var(--duration-normal)] ease-[var(--ease-out-expo)]"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Метрики — цветовой код вместо колонки чисел. Личное (мои тренировки) отделено от
          каталожного (упражнения/события/челленджи), чтобы скоуп чисел читался однозначно. */}
      <div className="mt-1 flex flex-col gap-2 border-t border-line/50 pt-3">
        {PERSONAL_METRICS.map((m) => (
          <MetricCell key={m.key} icon={m.icon} label={m.label} value={s[m.key]} hue={m.hue} />
        ))}
        <span className="mt-1 text-[0.6rem] font-semibold uppercase tracking-wide text-muted">
          В каталоге дисциплины
        </span>
        <div className="grid grid-cols-3 gap-2">
          {CATALOG_METRICS.map((m) => (
            <MetricCell key={m.key} icon={m.icon} label={m.label} value={s[m.key]} hue={m.hue} />
          ))}
        </div>
      </div>
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
