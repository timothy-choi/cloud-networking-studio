import { useEffect, useState } from 'react';

import { getPlatformMetrics } from '../../api/platformMetrics';
import { formatApiError } from '../../api/client';
import type { PlatformMetricsResponse } from '../../types/platformMetrics';

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/50">
      <div className="text-[10px] font-medium uppercase tracking-wide text-cns-label">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">{value}</div>
    </div>
  );
}

export function PlatformMetricsCard({ compact = false }: { compact?: boolean }) {
  const [data, setData] = useState<PlatformMetricsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void getPlatformMetrics()
      .then(setData)
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  if (err) {
    return <p className="text-sm text-red-700 dark:text-red-300">{err}</p>;
  }
  if (!data) {
    return <p className="text-sm text-cns-muted">Loading platform metrics…</p>;
  }

  const avg = data.deploy_duration.average_deploy_duration_seconds;
  const runtime = data.runtime_provider_status;

  return (
    <div className={compact ? 'space-y-3' : 'space-y-4'}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MetricTile label="Active deployments" value={data.active_deployments} />
        <MetricTile label="Succeeded" value={data.deployment_success_count} />
        <MetricTile label="Failed" value={data.deployment_failure_count} />
        <MetricTile label="Terminal sessions" value={data.active_terminal_sessions} />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <MetricTile
          label="Avg deploy (s)"
          value={avg != null ? avg.toFixed(1) : '—'}
        />
        <MetricTile label="API requests" value={data.api_requests.total_requests} />
        <MetricTile label="Cleanup eligible" value={data.cleanup_status.eligible_deployments} />
      </div>
      <div className="rounded-lg border border-zinc-200 px-3 py-2 text-xs dark:border-zinc-700">
        <div className="font-medium text-zinc-800 dark:text-zinc-100">Runtime provider</div>
        <div className="mt-1 text-cns-muted">
          {runtime.runtime_executor} · {runtime.runtime_provider ?? 'n/a'} · status {runtime.status}
          {runtime.runner_reachable != null ? ` · runner ${runtime.runner_reachable ? 'up' : 'down'}` : ''}
        </div>
      </div>
      {!compact && data.recent_failed_operations.length > 0 ? (
        <div>
          <h4 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Recent failures</h4>
          <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-xs text-cns-muted">
            {data.recent_failed_operations.slice(0, 8).map((f, i) => (
              <li key={`${f.created_at}-${i}`}>
                <span className="font-mono text-[10px]">{f.action}</span> — {f.message ?? f.status}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
