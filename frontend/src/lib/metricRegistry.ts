/** Реестр метрик-параметров на фронте: ЗАБИРАЕТСЯ С БЭКА (GET /metrics/registry) — единый
 *  источник правды (backend/app/services/metrics.py), без дублирования списка. Плюс чистые
 *  хелперы для целей: вытащить карту целей из активной цели и значение по ключу. */

import { useQuery } from '@tanstack/react-query';
import { api, type Goal, type MetricGroup, type MetricSpec } from './api';

export type { MetricGroup, MetricSpec } from './api';

/** Реестр метрик с бэка (кэш «навсегда» — список меняется редко, инвалидировать не нужно). */
export function useMetricRegistry() {
  return useQuery<MetricSpec[]>({
    queryKey: ['metric-registry'],
    queryFn: api.listMetricRegistry,
    staleTime: Infinity,
  });
}

/** Текущие показатели {ключ: значение} — дефолт для полей целей. Свежесть 30 c (как цель). */
export function useCurrentMetrics() {
  return useQuery<Record<string, number>>({
    queryKey: ['metrics-current'],
    queryFn: api.getCurrentMetrics,
    staleTime: 30_000,
  });
}

/** Метрики одной группы из загруженного реестра (порядок реестра сохраняется). */
export function metricsByGroup(registry: MetricSpec[], group: MetricGroup): MetricSpec[] {
  return registry.filter((m) => m.group === group);
}

/** Единая карта целей из target_metrics_json (единственный источник; ключи валидирует бэк). */
export function effectiveTargets(goal: Goal | null | undefined): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(goal?.target_metrics_json ?? {})) {
    if (v != null) out[k] = v;
  }
  return out;
}

/** Цель по одной метрике (число) или null, если не задана. */
export function goalTarget(goal: Goal | null | undefined, key: string): number | null {
  const t = effectiveTargets(goal);
  return key in t ? t[key] : null;
}
