/** Auth-состояние через TanStack Query: текущий юзер (/auth/me), вход, выход.
 *  ME_KEY — единый ключ кэша сессии; мутации входа/выхода обновляют его напрямую. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api, type User } from './api';

const ME_KEY = ['auth', 'me'] as const;

/** Текущий пользователь. 401 (не залогинен) — это не «ошибка для ретрая»:
 *  возвращаем null без повторов, чтобы guard сразу редиректил на /login. */
export function useMe() {
  return useQuery<User | null>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      api.login(email, password),
    onSuccess: (user) => qc.setQueryData(ME_KEY, user),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => qc.setQueryData(ME_KEY, null),
  });
}
