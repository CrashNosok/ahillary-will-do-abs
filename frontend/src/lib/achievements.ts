/** Ачивки по видам спорта через TanStack Query (S5.3 UI).
 *  Каждый вид спорта — свой запрос (useQueries), параллельно и без N+1-водопада;
 *  экран зипует результаты со списком спортов по индексу (порядок сохраняется). */

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Achievement, type Sport } from './api';

const sportAchievementsKey = (sportId: number) => ['sport-achievements', sportId] as const;

/** Запросы ачивок для каждого вида спорта. Результат i-го запроса соответствует sports[i]. */
export function useSportAchievements(sports: Sport[] | undefined) {
  return useQueries({
    queries: (sports ?? []).map((sport) => ({
      queryKey: sportAchievementsKey(sport.id),
      queryFn: (): Promise<Achievement[]> => api.listAchievements(sport.id),
    })),
  });
}

/** Ачивки одного вида спорта (для детальной страницы спорта — там же открытие через пруф). */
export function useAchievementsForSport(sportId: number) {
  return useQuery({
    queryKey: sportAchievementsKey(sportId),
    queryFn: (): Promise<Achievement[]> => api.listAchievements(sportId),
    enabled: Number.isFinite(sportId),
  });
}

/** Загрузка видео-пруфа ачивки (S5.6): после успеха обновляем список спорта,
 *  чтобы has_proof стал true и кнопка разблокировки разблокировалась. */
export function useUploadProof(sportId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ achievementId, file }: { achievementId: number; file: File }) =>
      api.uploadAchievementProof(achievementId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: sportAchievementsKey(sportId) }),
  });
}

/** Закрытие ачивки (S5.6): после успеха список спорта обновляется — карточка
 *  переключается в unlocked. */
export function useUnlockAchievement(sportId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (achievementId: number) => api.unlockAchievement(achievementId),
    onSuccess: () => qc.invalidateQueries({ queryKey: sportAchievementsKey(sportId) }),
  });
}
