/** Прогресс тела (S2.7) через TanStack Query: ряды веса/обхватов за период.
 *  Ключ кэша включает диапазон — смена периода перечитывает свой диапазон. */

import { useQuery } from '@tanstack/react-query';
import {
  api,
  type BodyProgress,
  type CardioProgress,
  type EnergyProgress,
  type InbodyProgress,
  type PersonalRecord,
  type StrengthProgress,
} from './api';

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

export function useStrengthProgress(start: string, end: string) {
  return useQuery<StrengthProgress>({
    queryKey: ['progress-strength', start, end],
    queryFn: () => api.getStrengthProgress(start, end),
    staleTime: 30_000,
  });
}

export function useCardioProgress(start: string, end: string) {
  return useQuery<CardioProgress>({
    queryKey: ['progress-cardio', start, end],
    queryFn: () => api.getCardioProgress(start, end),
    staleTime: 30_000,
  });
}

/** Личные рекорды (S3.10) — для подсветки PR-точек на графиках силовых/кардио. */
export function usePersonalRecords() {
  return useQuery<PersonalRecord[]>({
    queryKey: ['personal-records'],
    queryFn: () => api.listPersonalRecords(),
    staleTime: 30_000,
  });
}
