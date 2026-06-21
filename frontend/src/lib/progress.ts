/** Прогресс тела (S2.7) через TanStack Query: ряды веса/обхватов за период.
 *  Ключ кэша включает диапазон — смена периода перечитывает свой диапазон. */

import { useQuery } from '@tanstack/react-query';
import { api, type BodyProgress } from './api';

export function useBodyProgress(start: string, end: string) {
  return useQuery<BodyProgress>({
    queryKey: ['progress-body', start, end],
    queryFn: () => api.getBodyProgress(start, end),
    staleTime: 30_000,
  });
}
