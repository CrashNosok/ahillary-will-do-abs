/** Данные дашборда-хитмапа через TanStack Query: флаги по дням месяца.
 *  Ключ кэша включает диапазон, поэтому смена месяца перечитывает свой месяц. */

import { useQuery } from '@tanstack/react-query';
import { api, type DashboardData } from './api';

export function useDashboard(start: string, end: string) {
  return useQuery<DashboardData>({
    queryKey: ['dashboard', start, end],
    queryFn: () => api.getDashboard(start, end),
    staleTime: 30_000,
  });
}
