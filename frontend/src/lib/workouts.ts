/** Медиа тренировок через TanStack Query (M2·B18): галерея дня.
 *  Отдельный файл от sports.ts — это поверхность тренировок, а не каталог дисциплин. */

import { useQuery } from '@tanstack/react-query';
import { api, type SimpleWorkoutMedia } from './api';

/** Медиа (id+type) всех тренировок владельца за день. Ключ включает дату, чтобы кэш
 *  не смешивал дни; запрос идёт только при заданной дате (пустая → хук простаивает). */
export function useDayWorkoutMedia(date: string) {
  return useQuery<SimpleWorkoutMedia[]>({
    queryKey: ['workout-media', date],
    queryFn: () => api.listDayWorkoutMedia(date),
    enabled: !!date,
  });
}
