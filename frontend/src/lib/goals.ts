/** Состояние SMART-цели через TanStack Query: текущая активная цель + сохранение.
 *  GOAL_KEY — единый ключ кэша; сохранение инвалидирует его, чтобы экран перечитал цель. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Goal, type GoalInput } from './api';

const GOAL_KEY = ['goals', 'active'] as const;

/** Активная цель (или null, если её ещё нет). Берём из списка /goals (200 + []),
 *  поэтому пустое состояние — это норма, а не ошибка/спиннер. Инвариант «одна
 *  активная» держит бэкенд, так что find по status однозначен. */
export function useActiveGoal() {
  return useQuery<Goal | null>({
    queryKey: GOAL_KEY,
    queryFn: async () => {
      const goals = await api.listGoals();
      return goals.find((g) => g.status === 'active') ?? null;
    },
    staleTime: 30_000,
  });
}

/** Сохранить цель: есть активная → PATCH, иначе POST (инвариант «одна активная» держит бэкенд). */
export function useSaveGoal(current: Goal | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: GoalInput) =>
      current ? api.updateGoal(current.id, input) : api.createGoal(input),
    onSuccess: (goal) => qc.setQueryData(GOAL_KEY, goal),
  });
}
