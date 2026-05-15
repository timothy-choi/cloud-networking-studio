import { Navigate, Outlet } from 'react-router-dom';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../auth/AuthContext';

/** When the API requires login, blocks until a JWT session exists. Local dev uses implicit dev user from /auth/me. */
export function RequireSession() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
