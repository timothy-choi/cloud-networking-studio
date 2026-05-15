import type { DeploymentEventLevel } from '../../types/deployment';
import type { DeploymentStatus } from '../../types/deployment';
import type { RuntimeTopologyResponse } from '../../types/runtime';

interface RuntimeMetricsPanelProps {
  runtime: RuntimeTopologyResponse | null;
  /** Last successful runtime bundle poll (local clock). */
  lastRuntimePollAt?: string | null;
  /** Last successful deployment-events poll (local clock). */
  lastEventsPollAt?: string | null;
  /** Newest `created_at` from the loaded event stream (API data). */
  latestEventAt?: string | null;
  /** Latest deployment status string from topology runtime bundle. */
  deploymentStatus?: DeploymentStatus | null;
  /** Most recent warning or error in the deployment event stream. */
  latestSeverity?: {
    level: DeploymentEventLevel;
    message: string;
    created_at: string;
  } | null;
}

function fmtIso(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      hour12: false,
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function RuntimeMetricsPanel({
  runtime,
  lastRuntimePollAt,
  lastEventsPollAt,
  latestEventAt,
  deploymentStatus,
  latestSeverity,
}: RuntimeMetricsPanelProps) {
  const containers = runtime?.containers ?? [];
  const running = containers.filter((c) => c.running).length;
  const stopped = containers.filter((c) => !c.running).length;
  const nets = runtime?.networks?.length ?? 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Deployment status" value={deploymentStatus ?? runtime?.deployment_status ?? '—'} />
        <MetricCard label="Containers" value={containers.length} />
        <MetricCard label="Running" value={running} tone={running > 0 ? 'ok' : 'muted'} />
        <MetricCard label="Stopped" value={stopped} tone={stopped > 0 ? 'warn' : 'muted'} emphasize={stopped > 0} />
        <MetricCard label="Networks" value={nets} />
        <MetricCard label="Latest event" value={fmtIso(latestEventAt)} small />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <MetricCard label="Poll: runtime / events" value={`${lastRuntimePollAt ?? '—'} · ${lastEventsPollAt ?? '—'}`} small />
        <div
          className={`rounded-lg border px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/60 ${
            latestSeverity?.level === 'error'
              ? 'border-red-300 bg-red-50/90 dark:border-red-900 dark:bg-red-950/30'
              : latestSeverity?.level === 'warning'
                ? 'border-amber-300 bg-amber-50/90 dark:border-amber-900 dark:bg-amber-950/25'
                : 'border-zinc-200 bg-zinc-50/80'
          }`}
        >
          <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-card-label">
            Latest warning / error
          </div>
          {latestSeverity ? (
            <>
              <div className="mt-0.5 font-mono text-[10px] text-cns-muted">
                {latestSeverity.level} · {fmtIso(latestSeverity.created_at)}
              </div>
              <div className="mt-1 line-clamp-3 text-xs text-zinc-900 dark:text-zinc-100">{latestSeverity.message}</div>
            </>
          ) : (
            <div className="mt-0.5 text-xs text-cns-muted">None in the current event window.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone = 'muted',
  small,
  emphasize,
}: {
  label: string;
  value: string | number;
  tone?: 'ok' | 'warn' | 'muted';
  small?: boolean;
  emphasize?: boolean;
}) {
  const toneCls =
    tone === 'ok'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'warn'
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-zinc-900 dark:text-zinc-100';
  return (
    <div
      className={`rounded-lg border px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/60 ${
        emphasize
          ? 'border-amber-500/70 bg-amber-50 ring-2 ring-amber-400/40 dark:bg-amber-950/35 dark:ring-amber-500/30'
          : 'border-zinc-200 bg-zinc-50/80'
      }`}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-card-label">{label}</div>
      <div
        className={`mt-0.5 truncate font-mono ${small ? 'text-[11px]' : emphasize ? 'text-2xl font-bold tabular-nums' : 'text-lg font-semibold tabular-nums'} ${toneCls}`}
      >
        {value}
      </div>
    </div>
  );
}
