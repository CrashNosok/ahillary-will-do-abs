/** Спонсоры через TanStack Query (M6·F29): глобальный каталог партнёров для полосы спонсоров.
 *  Отдельный файл от sports.ts — это поверхность спонсоров, а не каталог дисциплин. Read-only. */

import { useQuery } from '@tanstack/react-query';
import { api, type Sponsor } from './api';

const SPONSORS_KEY = ['sponsors'] as const;

/** Каталог всех спонсоров (M6·B29): глобальный список для полосы на странице дисциплины. */
export function useSponsors() {
  return useQuery<Sponsor[]>({ queryKey: SPONSORS_KEY, queryFn: api.listSponsors });
}
