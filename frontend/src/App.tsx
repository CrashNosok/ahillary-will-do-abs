import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import Dashboard from './components/Dashboard';
import PlaceholderPage from './components/PlaceholderPage';
import ProtectedRoute from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          {/* Всё под защитой: layout рендерится только при валидной сессии. */}
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="progress" element={<PlaceholderPage title="Прогресс" />} />
            <Route path="workouts" element={<PlaceholderPage title="Тренировки" />} />
            <Route path="recommendations" element={<PlaceholderPage title="Рекомендации" />} />
            <Route path="goal" element={<PlaceholderPage title="Цель" />} />
            <Route path="settings" element={<PlaceholderPage title="Настройки" />} />
          </Route>

          {/* Неизвестный путь → дашборд (а без сессии guard уведёт на /login). */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
