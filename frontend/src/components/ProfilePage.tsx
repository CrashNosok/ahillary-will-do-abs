/** Личный кабинет (M5·F24): «Мой кабинет» — хаб дисциплин пользователя. Показывает
 *  привязанные виды спорта с личным рейтингом и текущим уровнем, позволяет привязать
 *  новую дисциплину (link, опц. с уровнем и рейтингом) и отвязать существующую (unlink).
 *  Всё на готовых эндпоинтах: GET/POST/DELETE /me/sports (B19) + каталог /sports + сводка
 *  /sports/{id}/overview (B27) для названия уровня. Read-write по своим связкам, скоуп по сессии. */

import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, sportCategoryLabel, type Sport, type UserSport } from '../lib/api';
import { useMe } from '../lib/auth';
import {
  useLinkSport,
  useMySports,
  useSportOverview,
  useSports,
  useUnlinkSport,
} from '../lib/sports';

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';
const cardCls =
  'flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6';

function errorMessage(err: unknown): string | null {
  if (err instanceof ApiError) return err.message;
  if (err) return 'Не удалось сохранить. Проверьте, что сервер запущен.';
  return null;
}

export default function ProfilePage() {
  const { data: user } = useMe();
  const { data: mySports, isPending } = useMySports();
  const linkedIds = useMemo(() => new Set((mySports ?? []).map((s) => s.sport_id)), [mySports]);

  return (
    <section aria-labelledby="profile-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Кабинет
        </p>
        <h1 id="profile-heading" className="mt-3 text-display">
          Мой кабинет
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          {user ? `Привет, ${user.display_name || user.email}! ` : ''}
          Ваши дисциплины, рейтинг и текущий уровень — в одном месте.
        </p>
      </div>

      <div className="flex flex-col gap-5">
        <h2 className="text-display">Мои дисциплины</h2>
        {isPending ? (
          <p className="text-muted">Загрузка…</p>
        ) : !mySports || mySports.length === 0 ? (
          <p className="text-muted">
            Вы пока не привязали ни одной дисциплины — добавьте первую ниже.
          </p>
        ) : (
          <ul className="grid gap-5 sm:grid-cols-2">
            {mySports.map((s) => (
              <li key={s.sport_id}>
                <MySportCard sport={s} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <LinkSportForm linkedIds={linkedIds} />
    </section>
  );
}

/** Карточка привязанной дисциплины: название (→ деталь), категория, рейтинг, текущий
 *  уровень и отвязка. После отвязки карточка исчезает из списка (инвалидация ['me','sports']). */
function MySportCard({ sport }: { sport: UserSport }) {
  const unlink = useUnlinkSport();
  const error = errorMessage(unlink.error);

  return (
    <div className={cardCls}>
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-display text-xl font-semibold tracking-tight">
          <Link
            to={`/sports/${sport.sport_id}`}
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
          onClick={() => unlink.mutate(sport.sport_id)}
          disabled={unlink.isPending}
          className="ml-auto rounded-full border border-accent bg-accent/15 px-3 py-1 text-sm font-medium text-accent transition-colors duration-[var(--duration-fast)] hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {unlink.isPending ? '…' : 'Отвязать'}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-4 border-t border-line pt-4">
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm font-medium text-muted">Рейтинг</dt>
          <dd className="font-display text-lg font-semibold">
            {sport.rating != null ? sport.rating : '—'}
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm font-medium text-muted">Уровень</dt>
          <dd className="font-display text-lg font-semibold">
            {sport.current_level_id != null ? (
              <LevelLabel sportId={sport.sport_id} levelId={sport.current_level_id} />
            ) : (
              <span className="text-muted">Не задан</span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}

/** Название текущего уровня по его id. Монтируется только когда уровень задан, поэтому
 *  сводка не тянется впустую для дисциплин без уровня.
 *  ponytail: переиспользуем /overview (есть готовый хук); если станет тяжело — точечный
 *  GET /sports/{id}/levels (B28). */
function LevelLabel({ sportId, levelId }: { sportId: number; levelId: number }) {
  const { data: overview, isPending } = useSportOverview(sportId);
  if (isPending) return <span className="text-muted">…</span>;
  const level = overview?.levels.find((l) => l.id === levelId);
  if (!level) return <span className="text-muted">№{levelId}</span>;
  return (
    <span>
      {level.label} <span className="text-sm font-normal text-muted">· {level.code}</span>
    </span>
  );
}

/** Форма привязки новой дисциплины: выбор из непривязанного каталога + опц. уровень
 *  (если у дисциплины есть ступени) и опц. рейтинг. Успех инвалидирует ['me','sports'],
 *  и дисциплина тут же появляется в списке выше. */
function LinkSportForm({ linkedIds }: { linkedIds: Set<number> }) {
  const { data: sports } = useSports();
  const link = useLinkSport();
  const [sportId, setSportId] = useState<number | ''>('');
  const [levelId, setLevelId] = useState<number | ''>('');
  const [rating, setRating] = useState('');

  const available = useMemo(
    () => (sports ?? []).filter((s) => !linkedIds.has(s.id)),
    [sports, linkedIds],
  );

  // Ступени выбранной дисциплины — для опционального выбора уровня при привязке.
  const { data: overview } = useSportOverview(sportId === '' ? NaN : sportId);
  const levels = overview?.levels ?? [];

  function onSelectSport(value: string) {
    setSportId(value === '' ? '' : Number(value));
    setLevelId(''); // у новой дисциплины свои ступени — сбрасываем выбор уровня
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (sportId === '') return;
    const ratingTrimmed = rating.trim();
    const ratingNum = ratingTrimmed === '' ? null : Number(ratingTrimmed);
    link.mutate(
      {
        sport_id: sportId,
        current_level_id: levelId === '' ? null : levelId,
        rating: ratingNum != null && Number.isFinite(ratingNum) ? ratingNum : null,
      },
      {
        onSuccess: () => {
          setSportId('');
          setLevelId('');
          setRating('');
        },
      },
    );
  }

  const error = errorMessage(link.error);

  if (sports && available.length === 0) {
    return (
      <div className={cardCls}>
        <h2 className="text-display">Привязать дисциплину</h2>
        <p className="text-muted">
          Все дисциплины каталога уже привязаны. Новые можно завести в разделе{' '}
          <Link to="/sports" className="font-medium text-accent hover:underline">
            «Виды спорта»
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Привязать дисциплину"
      className={`${cardCls} max-w-2xl`}
    >
      <h2 className="text-display">Привязать дисциплину</h2>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-muted">Дисциплина</span>
        <select
          name="sport_id"
          required
          value={sportId === '' ? '' : String(sportId)}
          onChange={(e) => onSelectSport(e.target.value)}
          className={`${inputCls} [color-scheme:dark]`}
        >
          <option value="">Выберите вид спорта</option>
          {available.map((s: Sport) => (
            <option key={s.id} value={s.id}>
              {s.name} · {sportCategoryLabel(s.category)}
            </option>
          ))}
        </select>
      </label>

      {levels.length > 0 && (
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-muted">Уровень</span>
          <select
            name="current_level_id"
            value={levelId === '' ? '' : String(levelId)}
            onChange={(e) => setLevelId(e.target.value === '' ? '' : Number(e.target.value))}
            className={`${inputCls} [color-scheme:dark]`}
          >
            <option value="">Без уровня</option>
            {[...levels]
              .sort((a, b) => a.rank - b.rank)
              .map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label} · {l.code}
                </option>
              ))}
          </select>
        </label>
      )}

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-muted">Рейтинг</span>
        <input
          name="rating"
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          value={rating}
          onChange={(e) => setRating(e.target.value)}
          placeholder="Необязательно — напр. 1500"
          className={inputCls}
        />
      </label>

      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={link.isPending || sportId === ''}
        className="mt-1 w-fit rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {link.isPending ? 'Привязываем…' : 'Привязать'}
      </button>
    </form>
  );
}
