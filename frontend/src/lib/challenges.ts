/** Челленджи через TanStack Query (M6·F25): каталог вызовов + участие + видео-пруф.
 *  Отдельный файл от sports.ts — это поверхность челленджей, а не каталог дисциплин. */

import { useMutation, useQuery } from '@tanstack/react-query';
import { api, type Challenge } from './api';

const CHALLENGES_KEY = ['challenges'] as const;

/** Каталог всех челленджей (M6·B34): их находят и присоединяются. */
export function useChallenges() {
  return useQuery<Challenge[]>({ queryKey: CHALLENGES_KEY, queryFn: api.listChallenges });
}

/** Присоединиться к челленджу. Каталог /challenges от join не меняется (это общий список,
 *  а не «мои»), а отдельного запроса «мои участия» пока нет — консьюмер берёт результат
 *  из onSuccess.
 *  ponytail: без invalidate — нет запроса, на который влияет join. Добавить, когда
 *  появится «мои челленджи». */
export function useJoinChallenge() {
  return useMutation({ mutationFn: (challengeId: number) => api.joinChallenge(challengeId) });
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
