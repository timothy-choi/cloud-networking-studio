import type { RuntimeTopologyResponse } from '../../types/runtime';

interface RuntimeMetricsPanelProps {
  runtime: RuntimeTopologyResponse | null;
  deploymentUpdatedHint?: string | null;
  eventsUpdatedHint?: string | null;
}

export function RuntimeMetricsPanel({
  runtime,
  deploymentUpdatedHint,
  eventsUpdatedHint,
}: RuntimeMetricsPanelProps) {
  const containers = runtime?.containers ?? [];
  const running = containers.filter((c) => c.running).length;
  const stopped = containers.filter((c) => !c.running).length;
  const nets = runtime?.networks?.length ?? 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <MetricCard label="Containers" value={containers.length} />
      <MetricCard label="Running" value={running} tone={running > 0 ? 'ok' : 'muted'} />
      <MetricCard label="Stopped" value={stopped} tone={stopped > 0 ? 'warn' : 'muted'} />
      <MetricCard label="Networks" value={nets} />
      <MetricCard label="Deploy updated" value={deploymentUpdatedHint ?? '—'} small />
      <MetricCard label="Events updated" value={eventsUpdatedHint ?? '—'} small />
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone = 'muted',
  small,
}: {
  label: string;
  value: string | number;
  tone?: 'ok' | 'warn' | 'muted';
  small?: boolean;
}) {
  const toneCls =
    tone === 'ok'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'warn'
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-zinc-900 dark:text-zinc-100';
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/60">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`mt-0.5 truncate font-mono ${small ? 'text-[11px]' : 'text-lg font-semibold tabular-nums'} ${toneCls}`}>
        {value}
      </div>
    </div>
  );
}
