import { Navigate } from 'react-router-dom';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../auth/AuthContext';
import { HomePage } from './HomePage';

/** `/` — marketing site for guests; authenticated users go straight to the dashboard. */
export function PublicHomeRoute() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }
  return <HomePage />;
}
