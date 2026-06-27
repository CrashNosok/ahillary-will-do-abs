/** Челленджи через TanStack Query (M6·F25): каталог вызовов + участие + видео-пруф.
 *  Отдельный файл от sports.ts — это поверхность челленджей, а не каталог дисциплин. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Challenge, type ChallengeParticipant } from './api';

const CHALLENGES_KEY = ['challenges'] as const;
const PARTICIPATIONS_KEY = ['challenge-participations'] as const;

/** Каталог всех челленджей (M6·B34): их находят и присоединяются. */
export function useChallenges() {
  return useQuery<Challenge[]>({ queryKey: CHALLENGES_KEY, queryFn: api.listChallenges });
}

/** Мои участия (challenge_id→статус): чтобы «Вы участвуете»/статус переживали перезагрузку. */
export function useMyChallengeParticipations() {
  return useQuery<ChallengeParticipant[]>({
    queryKey: PARTICIPATIONS_KEY,
    queryFn: api.listMyChallengeParticipations,
  });
}

/** Присоединиться к челленджу. По успеху инвалидируем «мои участия» — карта статусов
 *  пересоберётся, и кнопка станет «Вы участвуете» из реального состояния, а не локального. */
export function useJoinChallenge() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (challengeId: number) => api.joinChallenge(challengeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: PARTICIPATIONS_KEY }),
  });
}

/** Загрузить видео-пруф участия. Отдельного запроса «пруфы» пока нет — консьюмер берёт
 *  результат из onSuccess.
 *  ponytail: без invalidate — нечего обновлять. Добавить, когда появится список пруфов. */
export function useUploadChallengeProof() {
  return useMutation({
    mutationFn: (vars: { challengeId: number; file: File; notes?: string }) =>
      api.uploadChallengeProof(vars.challengeId, vars.file, vars.notes),
  });
}
