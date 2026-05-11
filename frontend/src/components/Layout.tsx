import { Link, Outlet } from 'react-router-dom';
import { getApiBase } from '../api/client';

export function Layout() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-baseline gap-3">
            <Link to="/" className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Cloud Networking Studio
            </Link>
            <span className="hidden text-xs font-medium uppercase tracking-wider text-zinc-500 sm:inline">
              Control plane
            </span>
          </div>
          <div className="font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
            API{' '}
            <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {getApiBase()}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
