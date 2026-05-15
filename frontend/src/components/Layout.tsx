import { Link, Outlet } from 'react-router-dom';
import { getApiBase } from '../api/client';
import { useAuth } from '../auth/AuthContext';

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-baseline gap-3">
            <Link to="/" className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Cloud Networking Studio
            </Link>
            <span className="hidden text-xs font-medium uppercase tracking-wider text-cns-label sm:inline">
              Control plane
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {user ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="max-w-[10rem] truncate text-zinc-700 dark:text-zinc-300" title={user.email}>
                  {user.display_name}
                </span>
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  Log out
                </button>
              </div>
            ) : null}
            <div className="font-mono text-[11px] text-cns-muted">
              API{' '}
              <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {getApiBase()}
              </span>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
