import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { RequireSession } from './auth/RequireSession';
import { Layout } from './components/Layout';
import { AcceptInvitationPage } from './pages/AcceptInvitationPage';
import { ApiTokensPage } from './pages/ApiTokensPage';
import { DashboardPage } from './pages/DashboardPage';
import { LoginPage } from './pages/LoginPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { PlatformMetricsPage } from './pages/PlatformMetricsPage';
import { PlatformSecurityPage } from './pages/PlatformSecurityPage';
import { PublicHomeRoute } from './pages/PublicHomeRoute';
import { RegisterPage } from './pages/RegisterPage';
import { TemplatesPage } from './pages/TemplatesPage';
import { TopologyDetailPage } from './pages/TopologyDetailPage';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<PublicHomeRoute />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<RequireSession />}>
            <Route element={<Layout />}>
              <Route path="invitations/accept" element={<AcceptInvitationPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="platform-metrics" element={<PlatformMetricsPage />} />
              <Route path="platform-security" element={<PlatformSecurityPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="api-tokens" element={<ApiTokensPage />} />
              <Route path="templates" element={<TemplatesPage />} />
              <Route path="topologies/:topologyId" element={<TopologyDetailPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
