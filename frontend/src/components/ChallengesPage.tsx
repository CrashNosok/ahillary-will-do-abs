/** Экран челленджей «WIPEOUTS» (M6·F26): грид вызовов из каталога + кнопка «Участвовать».
 *  Бэкенд — GET /challenges и POST /challenges/{id}/join (M6·B34); плюминг — lib/challenges (M6·F25).
 *  Название дисциплины в карточке берём из каталога /sports (map sport_id→name). */

import { useMemo, useState } from 'react';
import { ApiError, type Challenge } from '../lib/api';
import { useChallenges, useJoinChallenge, useUploadChallengeProof } from '../lib/challenges';
import { useSports } from '../lib/sports';
import VideoProofUploader from './VideoProofUploader';

function errorMessage(err: unknown): string | null {
  if (err instanceof ApiError) return err.message;
  if (err) return 'Что-то пошло не так. Проверьте, что сервер запущен.';
  return null;
}

export default function ChallengesPage() {
  const { data: challenges, isPending } = useChallenges();
  const { data: sports } = useSports();
  const sportNames = useMemo(
    () => new Map((sports ?? []).map((s) => [s.id, s.name] as const)),
    [sports],
  );

  return (
    <section
      aria-labelledby="challenges-heading"
      className="flex flex-col gap-[var(--space-section)]"
    >
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Челленджи
        </p>
        <h1 id="challenges-heading" className="mt-3 text-hero font-bold uppercase">
          WIPEOUTS
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Принимай вызовы по своим дисциплинам и доказывай результат — присоединяйся к челленджу
          одной кнопкой.
        </p>
      </div>

      {isPending ? (
        <p className="text-muted">Загрузка…</p>
      ) : !challenges || challenges.length === 0 ? (
        <p className="text-muted">Челленджей пока нет.</p>
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {challenges.map((challenge) => (
            <li key={challenge.id}>
              <ChallengeCard challenge={challenge} sportName={sportNames.get(challenge.sport_id)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ChallengeCard({ challenge, sportName }: { challenge: Challenge; sportName?: string }) {
  const join = useJoinChallenge();
  // Эндпоинта «мои участия» пока нет (M6·F25): стартуем как не-участник и отмечаем участие
  // из ответа join. Повторный join существующего участия даёт 409 — это тоже «участвую».
  const [joined, setJoined] = useState(false);
  // Видео-пруф доступен только участнику (бэкенд: 404, если не участвуешь) — отсюда после join.
  const proof = useUploadChallengeProof();
  const hasProof = proof.isSuccess;

  const onJoin = () =>
    join.mutate(challenge.id, {
      onSuccess: () => setJoined(true),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) setJoined(true);
      },
    });

  // 409 = «уже участвую» → это успех (кнопка станет «Вы участвуете»), ошибку не показываем.
  const error =
    join.error instanceof ApiError && join.error.status === 409 ? null : errorMessage(join.error);

  return (
    <article
      className={`flex h-full flex-col gap-4 rounded-[var(--radius-card)] border bg-gradient-to-br from-panel to-surface p-6 ${
        challenge.is_base
          ? 'border-accent/60 shadow-[0_0_40px_-12px] shadow-accent/40'
          : 'border-line'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {challenge.is_base && (
          <span className="rounded-full bg-accent px-3 py-1 text-xs font-semibold uppercase tracking-wide text-accent-ink">
            WIPEOUT
          </span>
        )}
        {sportName && (
          <span className="rounded-full border border-line px-3 py-1 text-xs font-medium text-muted">
            {sportName}
          </span>
        )}
      </div>

      <h2 className="font-display text-xl font-semibold tracking-tight">{challenge.title}</h2>
      <p className="text-muted">{challenge.description}</p>

      {error && (
        <p role="alert" className="text-sm font-medium text-amber">
          {error}
        </p>
      )}

      <div className="mt-auto flex flex-col gap-3 pt-2">
        {joined ? (
          <button
            type="button"
            disabled
            className="w-full rounded-xl border border-accent bg-accent/15 px-5 py-3 font-display font-semibold text-accent"
          >
            Вы участвуете
          </button>
        ) : (
          <button
            type="button"
            onClick={onJoin}
            disabled={join.isPending}
            className="w-full rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {join.isPending ? '…' : 'Участвовать'}
          </button>
        )}

        {/* Пруф результата (M6·F27) — общий VideoProofUploader, доступен только участнику. */}
        {joined && (
          <div className="flex flex-col gap-2 border-t border-line pt-3">
            <p className="text-xs font-medium text-muted">Загрузите видео-пруф результата:</p>
            <VideoProofUploader
              onPick={(file) => proof.mutate({ challengeId: challenge.id, file })}
              isPending={proof.isPending}
              hasProof={hasProof}
              error={proof.isError ? errorMessage(proof.error) : null}
            />
          </div>
        )}
      </div>
    </article>
  );
}
