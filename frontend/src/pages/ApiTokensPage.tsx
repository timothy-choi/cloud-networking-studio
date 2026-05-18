import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatApiError } from '../api/client';
import { createApiToken, listApiTokens, revokeApiToken, type ApiTokenCreated, type ApiTokenRow } from '../api/apiTokens';
import { SectionEmptyState } from '../components/SectionEmptyState';
import { Spinner } from '../components/Spinner';

function fmtWhen(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}

export function ApiTokensPage() {
  const [rows, setRows] = useState<ApiTokenRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await listApiTokens());
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate() {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    setErr(null);
    setCreated(null);
    try {
      const t = await createApiToken({ name: n });
      setCreated(t);
      setName('');
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(id: string) {
    if (!window.confirm('Revoke this token? CI jobs using it will fail.')) return;
    setBusy(true);
    setErr(null);
    try {
      await revokeApiToken(id);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">API tokens</h1>
        <p className="mt-1 max-w-2xl text-sm text-cns-muted">
          Use Bearer tokens from scripts and CI (same permissions as your account). Each token is shown in full only once — store it in your secret manager.
        </p>
      </div>

      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}

      {created ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100">
          <div className="font-semibold">Copy this token now</div>
          <p className="mt-1 text-xs">It will not be shown again.</p>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
            {created.token}
          </pre>
          <button
            type="button"
            className="mt-2 text-xs font-semibold text-amber-900 underline dark:text-amber-200"
            onClick={() => setCreated(null)}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Create token</h2>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-xs text-cns-label">
            Name
            <input
              className="mt-1 block w-64 rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. GitHub Actions prod"
            />
          </label>
          <button
            type="button"
            disabled={busy || !name.trim()}
            className="rounded-lg border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-sm font-semibold text-emerald-900 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100"
            onClick={() => void onCreate()}
          >
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Your tokens</h2>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400"
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-cns-muted">
            <Spinner className="h-4 w-4" />
            Loading…
          </div>
        ) : rows.length === 0 ? (
          <SectionEmptyState
            title="No API tokens yet"
            description="Personal Bearer tokens authenticate scripts and CI jobs with the same project access as your interactive login. Create one with the form above — the secret is shown only once, so copy it into your password manager."
            secondaryHint={
              <span>
                See <code className="rounded bg-zinc-100 px-1 font-mono text-[10px] dark:bg-zinc-800">docs/CI_CD_INTEGRATION.md</code> and{' '}
                <code className="rounded bg-zinc-100 px-1 font-mono text-[10px] dark:bg-zinc-800">python3 -m cli.cns</code> for examples.
              </span>
            }
          />
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900/60"
              >
                <div>
                  <div className="font-medium text-zinc-900 dark:text-zinc-50">{r.name}</div>
                  <div className="text-[11px] text-cns-muted">
                    hint …{r.token_hint} · created {fmtWhen(r.created_at)}
                    {r.last_used_at ? ` · last used ${fmtWhen(r.last_used_at)}` : ''}
                    {r.revoked_at ? ` · revoked ${fmtWhen(r.revoked_at)}` : ''}
                  </div>
                </div>
                {!r.revoked_at ? (
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded border border-red-300 px-2 py-1 text-xs text-red-800 dark:border-red-800 dark:text-red-300"
                    onClick={() => void onRevoke(r.id)}
                  >
                    Revoke
                  </button>
                ) : (
                  <span className="text-xs text-cns-muted">Revoked</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-cns-muted">
        CLI: set <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">PYTHONPATH</code> to the repo root and run{' '}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">python3 -m cli.cns token set</code> or see{' '}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">docs/CI_CD_INTEGRATION.md</code>.
      </p>
    </div>
  );
}
