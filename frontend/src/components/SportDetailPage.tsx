/** Детальная страница вида спорта (M5·F20): открывается из карточки каталога по /sports/:id.
 *  Читает сводку дисциплины (M5·B27): шапка (имя/категория/описания) + счётчик ачивок владельца
 *  + секции каталога (ступени/события/менторы/рекомендации), read-only. Глобальный каталог. */

import { type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, sportCategoryLabel } from '../lib/api';
import { useSportOverview } from '../lib/sports';

const eventDateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : eventDateFmt.format(d);
}

const backLink = (
  <Link to="/sports" className="text-sm font-medium text-accent hover:underline">
    ← Виды спорта
  </Link>
);

export default function SportDetailPage() {
  const { sportId } = useParams();
  const id = Number(sportId);
  const { data, isPending, error } = useSportOverview(id);

  if (!Number.isFinite(id) || (error instanceof ApiError && error.status === 404)) {
    return <StateScreen message="Вид спорта не найден." />;
  }
  if (error) {
    return (
      <StateScreen message="Не удалось загрузить дисциплину. Проверьте, что сервер запущен." />
    );
  }
  if (isPending || !data) {
    return <StateScreen message="Загрузка…" />;
  }

  const { sport, levels, events, mentors, recommendations, achievement_count } = data;

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
        <p className="mt-4 text-sm font-medium text-muted">Ачивок: {achievement_count}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Ступени" isEmpty={levels.length === 0} emptyText="Ступеней пока нет.">
          {levels.map((lvl) => (
            <li key={lvl.id} className="flex flex-col gap-0.5">
              <span className="font-medium">
                {lvl.rank}. {lvl.label} <span className="text-sm text-muted">· {lvl.code}</span>
              </span>
              {lvl.description && <span className="text-sm text-muted">{lvl.description}</span>}
            </li>
          ))}
        </Section>

        <Section title="События" isEmpty={events.length === 0} emptyText="Событий пока нет.">
          {events.map((ev) => (
            <li key={ev.id} className="flex flex-col gap-0.5">
              <span className="font-medium">{ev.title}</span>
              <span className="text-sm text-muted">
                {formatDate(ev.starts_on)}
                {ev.ends_on ? ` — ${formatDate(ev.ends_on)}` : ''}
                {ev.location ? ` · ${ev.location}` : ''}
              </span>
              {ev.description && <span className="text-sm text-muted">{ev.description}</span>}
            </li>
          ))}
        </Section>

        <Section
          title="Наставники"
          isEmpty={mentors.length === 0}
          emptyText="Наставников пока нет."
        >
          {mentors.map((m) => (
            <li key={m.id} className="flex flex-col gap-0.5">
              <span className="font-medium">{m.name}</span>
              {m.bio && <span className="text-sm text-muted">{m.bio}</span>}
              {m.contact && <span className="text-sm text-muted">{m.contact}</span>}
            </li>
          ))}
        </Section>

        <Section
          title="Рекомендации"
          isEmpty={recommendations.length === 0}
          emptyText="Рекомендаций пока нет."
        >
          {recommendations.map((r) => (
            <li key={r.id} className="flex flex-col gap-0.5">
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

/** Карточка-секция каталога дисциплины: заголовок + список или пустое состояние. */
function Section({
  title,
  isEmpty,
  emptyText,
  children,
}: {
  title: string;
  isEmpty: boolean;
  emptyText: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <h2 className="font-display text-xl font-semibold tracking-tight">{title}</h2>
      {isEmpty ? (
        <p className="text-muted">{emptyText}</p>
      ) : (
        <ul className="flex flex-col gap-3">{children}</ul>
      )}
    </div>
  );
}
