/** Личные числовые цели по упражнениям через TanStack Query: список + upsert + снятие.
 *  Питают целевые линии на графиках силовых/кардио и форму в «Мой кабинет». */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type ExerciseTarget } from './api';

const KEY = ['exercise-targets'] as const;

/** Все цели владельца по упражнениям. */
export function useExerciseTargets() {
  return useQuery<ExerciseTarget[]>({ queryKey: KEY, queryFn: api.listExerciseTargets });
}

/** Поставить/обновить цель по упражнению (upsert). По успеху обновляем список. */
export function useSaveExerciseTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { exercise_id: number; target_value: number; unit?: string | null }) =>
      api.upsertExerciseTarget(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

/** Снять цель по упражнению. */
export function useDeleteExerciseTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (exerciseId: number) => api.deleteExerciseTarget(exerciseId),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
