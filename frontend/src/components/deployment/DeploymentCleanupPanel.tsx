import { useCallback, useEffect, useState } from 'react';

import { getDeploymentCleanupStatus, runDeploymentCleanup } from '../../api/deployments';
import type { DeploymentCleanupStatusResponse } from '../../types/cleanup';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';

export function DeploymentCleanupPanel({
  deploymentId,
  viewerMode,
}: {
  deploymentId: string | null;
  viewerMode?: boolean;
}) {
  const [status, setStatus] = useState<DeploymentCleanupStatusResponse | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!deploymentId) {
      setStatus(null);
      return;
    }
    setErr(null);
    try {
      setStatus(await getDeploymentCleanupStatus(deploymentId));
    } catch (e) {
      setErr(e);
      setStatus(null);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!deploymentId) return null;

  async function onCleanup() {
    if (!deploymentId || viewerMode) return;
    setBusy(true);
    setNote(null);
    setErr(null);
    try {
      const out = await runDeploymentCleanup(deploymentId);
      setNote(out.ok ? 'Cleanup completed (best-effort).' : 'Cleanup finished with warnings.');
      await load();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Cleanup</h3>
        <p className="text-[11px] text-cns-muted">Runtime resource cleanup and TTL status.</p>
      </div>
      <div className="space-y-2 px-3 py-3 text-xs">
        {err ? <ApiErrorDisplay error={err} /> : null}
        {note ? <p className="text-emerald-800 dark:text-emerald-300">{note}</p> : null}
        {status ? (
          <>
            <div className="flex flex-wrap gap-2">
              <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] dark:bg-zinc-800">
                status: {status.status}
              </span>
              {status.expired ? (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                  TTL expired
                </span>
              ) : null}
              {status.eligible_for_cleanup ? (
                <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] text-sky-900 dark:bg-sky-950 dark:text-sky-200">
                  eligible
                </span>
              ) : null}
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-cns-muted">
              <dt>Runtime resources</dt>
              <dd className="text-right text-zinc-800 dark:text-zinc-200">{status.runtime_resources_count}</dd>
              <dt>Stale terminals</dt>
              <dd className="text-right text-zinc-800 dark:text-zinc-200">{status.stale_terminal_sessions}</dd>
              <dt>TTL (hours)</dt>
              <dd className="text-right text-zinc-800 dark:text-zinc-200">
                {status.deployment_ttl_hours > 0 ? status.deployment_ttl_hours : 'disabled'}
              </dd>
              {status.expires_at ? (
                <>
                  <dt>Expires</dt>
                  <dd className="text-right font-mono text-[10px] text-zinc-800 dark:text-zinc-200">
                    {new Date(status.expires_at).toLocaleString()}
                  </dd>
                </>
              ) : null}
            </dl>
            {status.reasons.length > 0 ? (
              <p className="text-[11px] text-cns-muted">Reasons: {status.reasons.join(', ')}</p>
            ) : null}
          </>
        ) : !err ? (
          <p className="text-cns-muted">Loading cleanup status…</p>
        ) : null}
        {!viewerMode ? (
          <button
            type="button"
            disabled={busy || !status?.eligible_for_cleanup}
            onClick={() => void onCleanup()}
            className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          >
            {busy ? 'Cleaning up…' : 'Run cleanup'}
          </button>
        ) : null}
      </div>
    </div>
  );
}
