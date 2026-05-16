import { Navigate, Outlet } from 'react-router-dom';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../auth/AuthContext';

/** Blocks app routes until a JWT session exists (validated via ``GET /auth/me`` with Bearer token). */
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
