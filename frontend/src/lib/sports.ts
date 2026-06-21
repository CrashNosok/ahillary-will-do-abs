/** Каталог дисциплин через TanStack Query (S3.3 UI): виды спорта + их упражнения.
 *  Упражнения тянем одним списком и группируем по sport_id на экране — без N+1.
 *  Создание инвалидирует свой ключ, чтобы список тут же подхватил новую запись. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Exercise, type ExerciseInput, type Sport, type SportInput } from './api';

const SPORTS_KEY = ['sports'] as const;
const EXERCISES_KEY = ['exercises'] as const;

export function useSports() {
  return useQuery<Sport[]>({ queryKey: SPORTS_KEY, queryFn: api.listSports });
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
