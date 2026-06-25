/** Каталог дисциплин через TanStack Query (S3.3 UI): виды спорта + их упражнения.
 *  Упражнения тянем одним списком и группируем по sport_id на экране — без N+1.
 *  Создание инвалидирует свой ключ, чтобы список тут же подхватил новую запись. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api,
  type Exercise,
  type ExerciseInput,
  type Sport,
  type SportCategory,
  type SportInput,
} from './api';

const SPORTS_KEY = ['sports'] as const;
const EXERCISES_KEY = ['exercises'] as const;
const SPORT_CATEGORIES_KEY = ['sport-categories'] as const;

/** Каталог дисциплин; category фильтрует через ?category= (M1·B15). Ключ включает категорию,
 *  чтобы кэш не смешивал выборки; инвалидация по префиксу ['sports'] обновляет все варианты. */
export function useSports(category?: SportCategory) {
  return useQuery<Sport[]>({
    queryKey: [...SPORTS_KEY, category ?? 'all'],
    queryFn: () => api.listSports(category),
  });
}

/** Канонический список категорий с бэкенда (M1·B15) — опции фильтра каталога. */
export function useSportCategories() {
  return useQuery<SportCategory[]>({
    queryKey: SPORT_CATEGORIES_KEY,
    queryFn: api.listSportCategories,
  });
}

/** Все упражнения одним запросом — экран сам группирует их по виду спорта. */
export function useExercises() {
  return useQuery<Exercise[]>({ queryKey: EXERCISES_KEY, queryFn: () => api.listExercises() });
}

export function useCreateSport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SportInput) => api.createSport(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: SPORTS_KEY }),
  });
}

export function useCreateExercise() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ExerciseInput) => api.createExercise(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: EXERCISES_KEY }),
  });
}
