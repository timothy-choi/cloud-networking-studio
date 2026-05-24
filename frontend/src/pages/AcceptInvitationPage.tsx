import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { formatApiError } from '../api/client';
import { acceptInvitation, declineInvitation } from '../api/projectMembers';

export function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const onAccept = useCallback(async () => {
    if (!token) {
      setErr('Missing invitation token. Open the link from your email.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await acceptInvitation(token);
      setDone(r.message);
      window.setTimeout(() => void navigate('/dashboard'), 1500);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [navigate, token]);

  const onDecline = useCallback(async () => {
    if (!token) {
      setErr('Missing invitation token.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await declineInvitation(token);
      setDone(r.message);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [token]);

  return (
    <div className="mx-auto max-w-lg space-y-4 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Project invitation</h1>
      <p className="text-sm text-cns-muted">
        Accept to join the project workspace, or decline if this was unexpected.
      </p>
      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}
      {done ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          {done}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || !token}
          onClick={() => void onAccept()}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Accept invitation'}
        </button>
        <button
          type="button"
          disabled={busy || !token}
          onClick={() => void onDecline()}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-600"
        >
          Decline
        </button>
        <Link to="/dashboard" className="px-2 py-2 text-sm text-cns-muted hover:underline">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
