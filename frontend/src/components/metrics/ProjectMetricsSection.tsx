import { useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import { getProjectMetrics } from '../../api/platformMetrics';
import type { ProjectMetricsResponse } from '../../types/platformMetrics';

export function ProjectMetricsSection({ projectId }: { projectId: string | null }) {
  const [data, setData] = useState<ProjectMetricsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) {
      setData(null);
      return;
    }
    setErr(null);
    void getProjectMetrics(projectId)
      .then(setData)
      .catch((e) => setErr(formatApiError(e)));
  }, [projectId]);

  if (!projectId) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
      <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Project metrics</h3>
      <p className="mt-0.5 text-[11px] text-cns-muted">Deployments, quota usage, and cleanup for this workspace.</p>
      {err ? <p className="mt-2 text-xs text-red-700 dark:text-red-300">{err}</p> : null}
      {!data && !err ? <p className="mt-2 text-xs text-cns-muted">Loading…</p> : null}
      {data ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-cns-muted">Active</dt>
            <dd className="font-semibold tabular-nums">{data.active_deployments}</dd>
          </div>
          <div>
            <dt className="text-cns-muted">Succeeded</dt>
            <dd className="font-semibold tabular-nums">{data.deployment_success_count}</dd>
          </div>
          <div>
            <dt className="text-cns-muted">Failed</dt>
            <dd className="font-semibold tabular-nums">{data.deployment_failure_count}</dd>
          </div>
          <div>
            <dt className="text-cns-muted">Avg deploy (s)</dt>
            <dd className="font-semibold tabular-nums">
              {data.deploy_duration.average_deploy_duration_seconds != null
                ? data.deploy_duration.average_deploy_duration_seconds.toFixed(1)
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-cns-muted">Quota used</dt>
            <dd className="font-semibold tabular-nums">
              {data.quota_usage.active_deployments} / {data.quota_usage.limits.max_active_deployments_per_project}
            </dd>
          </div>
          <div>
            <dt className="text-cns-muted">Cleanup eligible</dt>
            <dd className="font-semibold tabular-nums">{data.cleanup_status.eligible_deployments}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}
