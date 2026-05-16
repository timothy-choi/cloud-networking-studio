import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { formatApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';

export function RegisterPage() {
  const { register, clearSession } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (searchParams.get('reset') === '1') {
      clearSession();
    }
  }, [searchParams, clearSession]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await register(email.trim(), password, displayName.trim());
      navigate('/', { replace: true });
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 px-4 py-16 dark:bg-zinc-950">
      <div className="mx-auto max-w-md space-y-6 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Create account</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block text-sm">
          <span className="text-zinc-600 dark:text-zinc-400">Display name</span>
          <input
            type="text"
            required
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-950"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="text-zinc-600 dark:text-zinc-400">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-950"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="text-zinc-600 dark:text-zinc-400">Password (min 8 characters)</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-950"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {err ? <p className="text-sm text-red-600 dark:text-red-400">{err}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? 'Creating…' : 'Create account'}
        </button>
      </form>
      <p className="text-center text-sm text-cns-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-zinc-900 underline dark:text-zinc-100">
          Sign in
        </Link>
      </p>
      <div className="border-t border-zinc-200 pt-4 dark:border-zinc-700">
        <p className="text-center text-xs text-cns-muted">Stuck after a token or server change?</p>
        <button
          type="button"
          onClick={() => clearSession()}
          className="mt-2 w-full rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-950 hover:bg-amber-100 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-950/70"
        >
          Clear stored session
        </button>
      </div>
    </div>
    </div>
  );
}
