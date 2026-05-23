import { useCallback, useEffect, useState } from 'react';

import { getProjectQuotas } from '../../api/projects';
import { formatApiError } from '../../api/client';
import type { ProjectQuotaResponse } from '../../types/quota';

function UsageBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const hot = pct >= 85;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-cns-muted">
        <span>{label}</span>
        <span>
          {used} / {limit}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full ${hot ? 'bg-amber-500' : 'bg-emerald-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function ProjectQuotaPanel({ projectId }: { projectId: string | null }) {
  const [data, setData] = useState<ProjectQuotaResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) {
      setData(null);
      return;
    }
    setErr(null);
    try {
      setData(await getProjectQuotas(projectId));
    } catch (e) {
      setErr(formatApiError(e));
      setData(null);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!projectId) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
      <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Project quotas</h3>
      <p className="mt-0.5 text-[11px] text-cns-muted">Usage against platform limits for this workspace.</p>
      {err ? <p className="mt-2 text-xs text-red-700 dark:text-red-300">{err}</p> : null}
      {data ? (
        <div className="mt-3 space-y-3">
          <UsageBar
            used={data.usage.active_deployments}
            limit={data.limits.max_active_deployments_per_project}
            label="Active deployments"
          />
          <UsageBar
            used={data.usage.terminal_sessions}
            limit={data.limits.max_terminal_sessions_per_user}
            label="Your terminal sessions"
          />
          <UsageBar
            used={data.usage.api_tokens}
            limit={data.limits.max_api_tokens_per_user}
            label="Your API tokens"
          />
        </div>
      ) : !err ? (
        <p className="mt-2 text-xs text-cns-muted">Loading quotas…</p>
      ) : null}
    </div>
  );
}
