import { useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import { getDeploymentMetrics } from '../../api/platformMetrics';
import type { DeploymentMetricsResponse } from '../../types/platformMetrics';

export function DeploymentMetricsPanel({ deploymentId }: { deploymentId: string | null }) {
  const [data, setData] = useState<DeploymentMetricsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!deploymentId) {
      setData(null);
      return;
    }
    setErr(null);
    void getDeploymentMetrics(deploymentId)
      .then(setData)
      .catch((e) => setErr(formatApiError(e)));
  }, [deploymentId]);

  if (!deploymentId) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Deployment metrics</h3>
        <p className="text-[11px] text-cns-muted">Duration, resources, cleanup, and recent failures.</p>
      </div>
      <div className="space-y-2 px-3 py-3 text-xs">
        {err ? <p className="text-red-700 dark:text-red-300">{err}</p> : null}
        {!data && !err ? <p className="text-cns-muted">Loading…</p> : null}
        {data ? (
          <>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-cns-muted">
              <dt>Status</dt>
              <dd className="text-right font-medium text-zinc-800 dark:text-zinc-100">{data.status}</dd>
              <dt>Deploy duration (s)</dt>
              <dd className="text-right tabular-nums text-zinc-800 dark:text-zinc-100">
                {data.deploy_duration_seconds != null ? data.deploy_duration_seconds.toFixed(1) : '—'}
              </dd>
              <dt>Runtime resources</dt>
              <dd className="text-right tabular-nums text-zinc-800 dark:text-zinc-100">
                {data.runtime_resources_count}
              </dd>
              <dt>Active terminals</dt>
              <dd className="text-right tabular-nums text-zinc-800 dark:text-zinc-100">
                {data.active_terminal_sessions}
              </dd>
            </dl>
            {data.recent_failed_operations.length > 0 ? (
              <div className="mt-2 border-t border-zinc-100 pt-2 dark:border-zinc-800">
                <div className="font-medium text-zinc-800 dark:text-zinc-100">Recent failures</div>
                <ul className="mt-1 space-y-1 text-[11px] text-cns-muted">
                  {data.recent_failed_operations.slice(0, 5).map((f, i) => (
                    <li key={`${f.created_at}-${i}`}>{f.action}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
