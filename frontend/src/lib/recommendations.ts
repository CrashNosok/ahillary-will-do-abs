/** История рекомендаций через TanStack Query: список, деталь по id и генерация по кнопке.
 *  Список и детали — раздельные ключи кэша; генерация инвалидирует только список, чтобы
 *  история перечитала свежую запись, а уже открытые детали (immutable) не дёргались зря. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Recommendation } from './api';

const LIST_KEY = ['recommendations', 'list'] as const;
const detailKey = (id: number) => ['recommendations', 'detail', id] as const;

/** История: последние сохранённые рекомендации (свежие сверху — порядок задаёт бэкенд). */
export function useRecommendations() {
  return useQuery<Recommendation[]>({
    queryKey: LIST_KEY,
    queryFn: () => api.listRecommendations(),
  });
}

/** Деталь по id. Запрос идёт только при выбранном id (null — ничего не открыто). */
export function useRecommendation(id: number | null) {
  return useQuery<Recommendation>({
    queryKey: detailKey(id ?? -1),
    queryFn: () => api.getRecommendation(id as number),
    enabled: id != null,
  });
}

/** Сгенерировать рекомендацию (POST /generate). На успехе кладём запись в кэш детали
 *  (открывается без повторного запроса) и инвалидируем список — история обновится. */
export function useGenerateRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.generateRecommendation(),
    onSuccess: (rec) => {
      qc.setQueryData(detailKey(rec.id), rec);
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}
