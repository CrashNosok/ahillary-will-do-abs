/** Ачивки по видам спорта через TanStack Query (S5.3 UI).
 *  Каждый вид спорта — свой запрос (useQueries), параллельно и без N+1-водопада;
 *  экран зипует результаты со списком спортов по индексу (порядок сохраняется). */

import { useQueries } from '@tanstack/react-query';
import { api, type Achievement, type Sport } from './api';

/** Запросы ачивок для каждого вида спорта. Результат i-го запроса соответствует sports[i]. */
export function useSportAchievements(sports: Sport[] | undefined) {
  return useQueries({
    queries: (sports ?? []).map((sport) => ({
      queryKey: ['sport-achievements', sport.id] as const,
      queryFn: (): Promise<Achievement[]> => api.listAchievements(sport.id),
    })),
  });
}
