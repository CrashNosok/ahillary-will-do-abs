import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useMe } from '../lib/auth';

/** Пускает дальше только при валидной сессии. Пока /auth/me грузится — лоадер;
 *  нет юзера (401) или ошибка проверки → редирект на /login с запоминанием цели. */
export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useMe();
  const location = useLocation();

  if (isPending) {
    return (
      <div className="grid min-h-screen place-items-center text-muted" role="status">
        Загрузка…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
