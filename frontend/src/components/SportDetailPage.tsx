/** Детальная страница вида спорта (M5·F20/F21): открывается из карточки каталога по /sports/:id.
 *  Каркас (M5·F21): шапка (имя/категория-чип/описания) рендерится из useSport(id) — лёгкий
 *  GET /sports/{id}; not-found/loading/error страницы тоже на нём. Тело (секции каталога:
 *  ступени/события/менторы/рекомендации) — из useSportOverview(id) (M5·B27). M5·F23: события/
 *  менторы/рекомендации показываются read-only карточками, а ачивки — отдельной карточкой со
 *  счётчиком владельца и deep-link на общий экран /achievements. Read-only, глобальный каталог. */

import { type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, type Sponsor, sportCategoryLabel } from '../lib/api';
import { useMySports, useSport, useSportOverview } from '../lib/sports';
import { useSponsors } from '../lib/sponsors';
import LevelLadder from './LevelLadder';

const eventDateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : eventDateFmt.format(d);
}

/** Внешняя ссылка из каталога — рендерим только http(s), чтобы не отдать в href
 *  javascript:/data:-схему из данных, которыми мы не управляем напрямую. */
function externalHref(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

// Общий вид read-only карточки секции (события/менторы/рекомендации) — один источник правды.
const itemCardCls = 'flex flex-col gap-1 rounded-xl border border-line bg-panel p-4';

const backLink = (
  <Link to="/sports" className="text-sm font-medium text-accent hover:underline">
    ← Виды спорта
  </Link>
);

export default function SportDetailPage() {
  const { sportId } = useParams();
  const id = Number(sportId);
  // Шапка/состояния страницы — на useSport (M5·F21); тело (секции/ачивки) — на overview (M5·B27).
  const { data: sport, isPending, error } = useSport(id);
  const { data: overview, isPending: overviewPending, error: overviewError } = useSportOverview(id);
  // Текущий уровень владельца — из его привязок /me/sports (M2·B19); null, если дисциплина
  // не привязана к пользователю (тогда лестница показывается без подсветки).
  const { data: mySports } = useMySports();
  const currentLevelId = mySports?.find((s) => s.sport_id === id)?.current_level_id ?? null;
  // Полоса спонсоров (M6·F29) — глобальный каталог партнёров, общий для всех дисциплин.
  const { data: sponsors, isPending: sponsorsPending, error: sponsorsError } = useSponsors();

  if (!Number.isFinite(id) || (error instanceof ApiError && error.status === 404)) {
    return <StateScreen message="Вид спорта не найден." />;
  }
  if (error) {
    return (
      <StateScreen message="Не удалось загрузить дисциплину. Проверьте, что сервер запущен." />
    );
  }
  if (isPending || !sport) {
    return <StateScreen message="Загрузка…" />;
  }

  // overview грузится параллельно: пока его нет — секции показывают «Загрузка…», а не «пусто».
  const levels = overview?.levels ?? [];
  const events = overview?.events ?? [];
  const mentors = overview?.mentors ?? [];
  const recommendations = overview?.recommendations ?? [];

  return (
    <section
      aria-labelledby="sport-detail-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        {backLink}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 id="sport-detail-heading" className="text-display">
            {sport.name}
          </h1>
          <span className="rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-ink">
            {sportCategoryLabel(sport.category)}
          </span>
        </div>
        {sport.description && (
          <p className="mt-4 text-lg leading-relaxed text-muted">{sport.description}</p>
        )}
        {sport.long_description && (
          <p className="mt-3 leading-relaxed text-muted">{sport.long_description}</p>
        )}
      </div>

      {/* Спонсоры (M6·F29): полоса партнёров проекта (глобальный каталог /sponsors, не привязан
          к дисциплине). Read-only — карточки-пилюли с именем и внешней ссылкой при http(s) url. */}
      <SponsorStrip sponsors={sponsors} isLoading={sponsorsPending} isError={!!sponsorsError} />

      {/* Достижения (M5·F23): счётчик ачивок дисциплины (скоуп пользователя) + deep-link на
          общий экран достижений. Read-only — генерация/разблокировка живут на /achievements. */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-6">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-xl font-semibold tracking-tight">Достижения</h2>
          <p className="text-muted">
            {overviewPending
              ? 'Загрузка…'
              : overviewError
                ? 'Не удалось загрузить.'
                : `Ачивок по дисциплине: ${overview?.achievement_count ?? 0}`}
          </p>
        </div>
        <Link
          to="/achievements"
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 active:translate-y-0"
        >
          Все достижения →
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Ступени"
          isLoading={overviewPending}
          isError={!!overviewError}
          isEmpty={levels.length === 0}
          emptyText="Ступеней пока нет."
        >
          <LevelLadder levels={levels} currentLevelId={currentLevelId} />
        </Section>

        <Section
          title="События"
          isLoading={overviewPending}
          isError={!!overviewError}
          isEmpty={events.length === 0}
          emptyText="Событий пока нет."
        >
          {events.map((ev) => (
            <li key={ev.id} className={itemCardCls}>
              <span className="font-medium">{ev.title}</span>
              <span className="text-sm text-muted">
                {formatDate(ev.starts_on)}
                {ev.ends_on ? ` — ${formatDate(ev.ends_on)}` : ''}
                {ev.location ? ` · ${ev.location}` : ''}
              </span>
              {ev.description && <span className="text-sm text-muted">{ev.description}</span>}
              {externalHref(ev.url) && (
                <a
                  href={externalHref(ev.url)!}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-sm font-medium text-accent hover:underline"
                >
                  Открыть ↗
                </a>
              )}
            </li>
          ))}
        </Section>

        <Section
          title="Наставники"
          isLoading={overviewPending}
          isError={!!overviewError}
          isEmpty={mentors.length === 0}
          emptyText="Наставников пока нет."
        >
          {mentors.map((m) => (
            <li key={m.id} className={itemCardCls}>
              <span className="font-medium">{m.name}</span>
              {m.bio && <span className="text-sm text-muted">{m.bio}</span>}
              {m.contact && <span className="text-sm text-muted">{m.contact}</span>}
              {externalHref(m.url) && (
                <a
                  href={externalHref(m.url)!}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-sm font-medium text-accent hover:underline"
                >
                  Профиль ↗
                </a>
              )}
            </li>
          ))}
        </Section>

        <Section
          title="Рекомендации"
          isLoading={overviewPending}
          isError={!!overviewError}
          isEmpty={recommendations.length === 0}
          emptyText="Рекомендаций пока нет."
        >
          {recommendations.map((r) => (
            <li key={r.id} className={itemCardCls}>
              <span className="font-medium">{r.title}</span>
              <span className="text-sm text-muted">{r.body}</span>
            </li>
          ))}
        </Section>
      </div>
    </section>
  );
}

/** Экран простого состояния (загрузка/ошибка/не найдено) — с тем же возвратом в каталог. */
function StateScreen({ message }: { message: string }) {
  return (
    <section className="flex flex-col gap-4">
      {backLink}
      <p className="text-muted">{message}</p>
    </section>
  );
}

/** Карточка-секция каталога дисциплины: заголовок + список, пустое состояние, «Загрузка…»
 *  (пока тянется агрегат /overview — чтобы не мигало «пусто» до прихода данных) или ошибка
 *  загрузки (чтобы сбой /overview не выглядел как «данных нет»). */
function Section({
  title,
  isLoading,
  isError,
  isEmpty,
  emptyText,
  children,
}: {
  title: string;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyText: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <h2 className="font-display text-xl font-semibold tracking-tight">{title}</h2>
      {isLoading ? (
        <p className="text-muted">Загрузка…</p>
      ) : isError ? (
        <p className="text-muted">Не удалось загрузить.</p>
      ) : isEmpty ? (
        <p className="text-muted">{emptyText}</p>
      ) : (
        <ul className="flex flex-col gap-3">{children}</ul>
      )}
    </div>
  );
}

/** Полоса спонсоров (M6·F29): горизонтальный ряд пилюль-партнёров. Имя всегда; внешняя ссылка —
 *  только при http(s) `url` (логотип не рендерим: файла на отдачу нет, был бы 404). Те же
 *  состояния загрузки/ошибки/пусто, что и у секций дисциплины, чтобы не мигало «пусто». */
function SponsorStrip({
  sponsors,
  isLoading,
  isError,
}: {
  sponsors: Sponsor[] | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <h2 className="font-display text-xl font-semibold tracking-tight">Спонсоры</h2>
      {isLoading ? (
        <p className="text-muted">Загрузка…</p>
      ) : isError ? (
        <p className="text-muted">Не удалось загрузить.</p>
      ) : !sponsors || sponsors.length === 0 ? (
        <p className="text-muted">Спонсоров пока нет.</p>
      ) : (
        <ul className="flex flex-wrap gap-3">
          {sponsors.map((s) => (
            <li key={s.id}>{renderSponsorPill(s)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

const sponsorPillCls =
  'inline-flex items-center rounded-full border border-line bg-panel px-4 py-2 text-sm font-medium';

/** Одна пилюля спонсора: ссылка при http(s) url, иначе статичный чип. description — в title. */
function renderSponsorPill(s: Sponsor) {
  const href = externalHref(s.url);
  const title = s.description ?? undefined;
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        title={title}
        className={`${sponsorPillCls} text-accent transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:underline active:translate-y-0`}
      >
        {s.name} ↗
      </a>
    );
  }
  return (
    <span title={title} className={sponsorPillCls}>
      {s.name}
    </span>
  );
}
