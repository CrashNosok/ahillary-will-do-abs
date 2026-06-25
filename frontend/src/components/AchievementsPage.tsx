/** Экран достижений (S5.3): ачивки сгруппированы по виду спорта, с тиром (level) и
 *  статусом (locked/in_progress/unlocked). Закрытые визуально отличаются — приглушены,
 *  пунктирная рамка, серый чип. Данные: GET /sports + GET /sports/{id}/achievements (S5.2). */

import {
  achievementThumbnailUrl,
  ApiError,
  sportCategoryLabel,
  type Achievement,
  type AchievementStatus,
  type AchievementTier,
  type Sport,
} from '../lib/api';
import { useSportAchievements, useUnlockAchievement, useUploadProof } from '../lib/achievements';
import { useSports } from '../lib/sports';
import VideoProofUploader from './VideoProofUploader';

// Тиры по возрастанию сложности — для сортировки карточек внутри спорта.
const TIER_ORDER: Record<AchievementTier, number> = {
  foundation: 0,
  intermediate: 1,
  advanced: 2,
  elite: 3,
};

const TIER_LABEL: Record<AchievementTier, string> = {
  foundation: 'База',
  intermediate: 'Средний',
  advanced: 'Продвинутый',
  elite: 'Элита',
};

// Статус → ярлык + классы чипа/точки. Закрытая — намеренно тусклая и серая.
const STATUS_META: Record<AchievementStatus, { label: string; chip: string; dot: string }> = {
  unlocked: {
    label: 'Открыто',
    chip: 'border-accent/40 bg-accent/10 text-accent',
    dot: 'bg-accent',
  },
  in_progress: {
    label: 'В процессе',
    chip: 'border-amber/40 bg-amber/10 text-amber',
    dot: 'bg-amber',
  },
  locked: {
    label: 'Закрыто',
    chip: 'border-line bg-panel text-muted',
    dot: 'bg-muted',
  },
};

const isTier = (level: string | null): level is AchievementTier =>
  level != null && level in TIER_ORDER;

export const tierRank = (level: string | null): number => (isTier(level) ? TIER_ORDER[level] : 99);

const tierLabel = (level: string | null): string =>
  isTier(level) ? TIER_LABEL[level] : (level ?? '—');

export default function AchievementsPage() {
  const { data: sports, isPending: sportsPending } = useSports();
  const results = useSportAchievements(sports);

  const loading = sportsPending || results.some((r) => r.isPending);
  const hasSports = !!sports && sports.length > 0;
  // Есть ли хоть одно подтверждённое достижение во всех видах спорта.
  const anyEarned = results.some((r) => (r.data ?? []).some((a) => a.status === 'unlocked'));

  return (
    <section
      aria-labelledby="achievements-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Прогресс
        </p>
        <h1 id="achievements-heading" className="mt-3 text-display">
          Достижения
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Подтверждённые достижения по видам спорта — то, что ты открыл и заверил видео.
        </p>
      </div>

      {loading ? (
        <p className="text-muted">Загрузка…</p>
      ) : !hasSports ? (
        <p className="text-muted">
          Видов спорта пока нет — заведите их на странице «Виды спорта», затем сгенерируйте ачивки.
        </p>
      ) : !anyEarned ? (
        <p className="text-muted">
          Пока нет подтверждённых достижений. Открой ачивку и загрузи видео-подтверждение — она
          появится здесь.
        </p>
      ) : (
        <div className="flex flex-col gap-[var(--space-section)]">
          {sports.map((sport, i) => (
            <SportAchievements key={sport.id} sport={sport} achievements={results[i]?.data ?? []} />
          ))}
        </div>
      )}
    </section>
  );
}

function SportAchievements({ sport, achievements }: { sport: Sport; achievements: Achievement[] }) {
  // Показываем только достигнутые и подтверждённые (unlocked); тируем по сложности.
  const earned = [...achievements]
    .filter((a) => a.status === 'unlocked')
    .sort((a, b) => tierRank(a.level) - tierRank(b.level) || a.id - b.id);
  if (earned.length === 0) return null; // спорт без подтверждённых достижений не показываем

  return (
    <section aria-labelledby={`sport-${sport.id}-heading`} className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 border-b border-line pb-4">
        <h2 id={`sport-${sport.id}-heading`} className="text-display">
          {sport.name}
        </h2>
        <span className="rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-ink">
          {sportCategoryLabel(sport.category)}
        </span>
        <span className="ml-auto text-sm font-medium text-muted">{earned.length} подтверждено</span>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {earned.map((achievement) => (
          <li key={achievement.id}>
            <AchievementCard achievement={achievement} sportId={sport.id} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Что-то пошло не так. Проверьте, что сервер запущен.';
}

export function AchievementCard({
  achievement,
  sportId,
}: {
  achievement: Achievement;
  sportId: number;
}) {
  const upload = useUploadProof(sportId);
  const unlock = useUnlockAchievement(sportId);

  const status = STATUS_META[achievement.status] ?? STATUS_META.locked;
  const isLocked = achievement.status === 'locked';
  const isUnlocked = achievement.status === 'unlocked';
  // Пруф есть, если бэкенд так сказал (has_proof) или мы только что загрузили его сами.
  const hasProof = achievement.has_proof === true || upload.isSuccess;

  // cache-bust превью: id свежезагруженного пруфа, иначе момент закрытия (стабилен на reload).
  const bust = upload.data?.id ?? achievement.unlocked_at ?? 'p';
  const thumbSrc = hasProof ? achievementThumbnailUrl(achievement.id, bust) : null;

  // Карточка по статусу: закрытая — пунктир + приглушение, открытая — акцентная рамка.
  const cardCls = isLocked
    ? 'border-dashed border-line bg-surface/50'
    : isUnlocked
      ? 'border-accent/30 bg-gradient-to-br from-panel to-surface'
      : 'border-amber/30 bg-surface';

  function onPick(file: File) {
    upload.mutate({ achievementId: achievement.id, file });
  }

  return (
    <article
      className={`flex h-full flex-col gap-3 rounded-[var(--radius-card)] border p-5 ${cardCls}`}
    >
      {thumbSrc && (
        <img
          src={thumbSrc}
          alt={`Превью видео-пруфа: ${achievement.title}`}
          className="aspect-video w-full rounded-xl border border-line object-cover"
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-display text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          {tierLabel(achievement.level)}
        </span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${status.chip}`}
        >
          <span className={`size-1.5 rounded-full ${status.dot}`} aria-hidden="true" />
          {status.label}
        </span>
      </div>

      <h3 className="font-display text-lg font-semibold leading-snug tracking-tight">
        {achievement.title}
      </h3>

      {achievement.description && (
        <p className="text-sm leading-relaxed text-muted">{achievement.description}</p>
      )}

      {/* Загрузка видео → превью → разблокировка (S5.6). На открытой ачивке скрыто. */}
      {!isUnlocked && (
        <div className="mt-auto flex flex-col gap-2 border-t border-line pt-4">
          <VideoProofUploader
            onPick={onPick}
            isPending={upload.isPending}
            hasProof={hasProof}
            error={upload.isError ? errorText(upload.error) : null}
          />

          <button
            type="button"
            onClick={() => unlock.mutate(achievement.id)}
            disabled={!hasProof || unlock.isPending}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          >
            {unlock.isPending ? 'Разблокируем…' : 'Разблокировать'}
          </button>

          {unlock.isError && (
            <p role="alert" className="text-xs font-medium text-amber">
              {errorText(unlock.error)}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
