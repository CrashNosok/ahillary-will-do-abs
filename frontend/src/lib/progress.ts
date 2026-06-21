/** Прогресс тела (S2.7) через TanStack Query: ряды веса/обхватов за период.
 *  Ключ кэша включает диапазон — смена периода перечитывает свой диапазон. */

import { useQuery } from '@tanstack/react-query';
import { api, type BodyProgress, type EnergyProgress, type InbodyProgress } from './api';

export function useBodyProgress(start: string, end: string) {
  return useQuery<BodyProgress>({
    queryKey: ['progress-body', start, end],
    queryFn: () => api.getBodyProgress(start, end),
    staleTime: 30_000,
  });
}

export function useEnergyProgress(start: string, end: string) {
  return useQuery<EnergyProgress>({
    queryKey: ['progress-energy', start, end],
    queryFn: () => api.getEnergyProgress(start, end),
    staleTime: 30_000,
  });
}

export function useInbodyProgress(start: string, end: string) {
  return useQuery<InbodyProgress>({
    queryKey: ['progress-inbody', start, end],
    queryFn: () => api.getInbodyProgress(start, end),
    staleTime: 30_000,
  });
}
