import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AchievementsPage from './components/AchievementsPage';
import ActivityImportPage from './components/ActivityImportPage';
import AppShell from './components/AppShell';
import BodyMeasurementsPage from './components/BodyMeasurementsPage';
import ChallengesPage from './components/ChallengesPage';
import CoachPhrasesPage from './components/CoachPhrasesPage';
import Dashboard from './components/Dashboard';
import DataEntryPage from './components/DataEntryPage';
import GoalPage from './components/GoalPage';
import ImportPage from './components/ImportPage';
import InbodyImportPage from './components/InbodyImportPage';
import PlaceholderPage from './components/PlaceholderPage';
import ProfilePage from './components/ProfilePage';
import ProgressPage from './components/ProgressPage';
import ProtectedRoute from './components/ProtectedRoute';
import RecommendationsPage from './components/RecommendationsPage';
import SportDetailPage from './components/SportDetailPage';
import SportsPage from './components/SportsPage';
import WorkoutLoggerPage from './components/WorkoutLoggerPage';
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
            <Route path="profile" element={<ProfilePage />} />
            <Route path="data-entry" element={<DataEntryPage />} />
            <Route path="progress" element={<ProgressPage />} />
            <Route path="sports" element={<SportsPage />} />
            <Route path="sports/:sportId" element={<SportDetailPage />} />
            <Route path="achievements" element={<AchievementsPage />} />
            <Route path="challenges" element={<ChallengesPage />} />
            <Route path="coach-phrases" element={<CoachPhrasesPage />} />
            <Route path="workouts" element={<WorkoutLoggerPage />} />
            <Route path="recommendations" element={<RecommendationsPage />} />
            <Route path="goal" element={<GoalPage />} />
            <Route path="body" element={<BodyMeasurementsPage />} />
            <Route path="import" element={<ImportPage />} />
            <Route path="import-activity" element={<ActivityImportPage />} />
            <Route path="import-inbody" element={<InbodyImportPage />} />
            <Route path="settings" element={<PlaceholderPage title="Настройки" />} />
          </Route>

          {/* Неизвестный путь → дашборд (а без сессии guard уведёт на /login). */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
