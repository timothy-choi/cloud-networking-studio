import type { DeploymentStatus } from '../../types/deployment';
import type { RuntimeHealthTier } from '../../types/runtime';
import type { TopologyStatus } from '../../types/topology';

interface Props {
  topologyStatus: TopologyStatus;
  deploymentStatus: DeploymentStatus | null;
  runtimeTier: RuntimeHealthTier;
  pollLive?: boolean;
}

function Pill({
  label,
  variant,
}: {
  label: string;
  variant: 'green' | 'yellow' | 'red' | 'slate' | 'blue';
}) {
  const map = {
    green:
      'bg-emerald-500/15 text-emerald-800 ring-emerald-500/30 dark:text-emerald-300 dark:ring-emerald-500/40',
    yellow:
      'bg-amber-500/15 text-amber-900 ring-amber-500/30 dark:text-amber-200 dark:ring-amber-500/40',
    red: 'bg-red-500/15 text-red-800 ring-red-500/30 dark:text-red-300 dark:ring-red-500/40',
    slate: 'bg-zinc-500/15 text-zinc-700 ring-zinc-500/25 dark:text-zinc-300 dark:ring-zinc-500/35',
    blue: 'bg-sky-500/15 text-sky-900 ring-sky-500/30 dark:text-sky-200 dark:ring-sky-500/40',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${map[variant]}`}>
      {label}
    </span>
  );
}

function tierLabel(tier: RuntimeHealthTier): { text: string; variant: 'green' | 'yellow' | 'red' | 'slate' } {
  switch (tier) {
    case 'healthy':
      return { text: 'Runtime healthy', variant: 'green' };
    case 'degraded':
      return { text: 'Runtime degraded', variant: 'yellow' };
    case 'failed':
      return { text: 'Runtime failed', variant: 'red' };
    default:
      return { text: 'Idle / no workload', variant: 'slate' };
  }
}

export function RuntimeHealthBadges({ topologyStatus, deploymentStatus, runtimeTier, pollLive }: Props) {
  const t = tierLabel(runtimeTier);
  const topoVariant =
    topologyStatus === 'active' ? 'green' : topologyStatus === 'archived' ? 'slate' : 'blue';

  const depLabel = deploymentStatus ?? 'none';
  let depVariant: 'green' | 'yellow' | 'red' | 'slate' = 'slate';
  if (deploymentStatus === 'succeeded') depVariant = 'green';
  else if (deploymentStatus === 'failed') depVariant = 'red';
  else if (deploymentStatus === 'stopped') depVariant = 'slate';
  else if (
    deploymentStatus === 'pending' ||
    deploymentStatus === 'deploying' ||
    deploymentStatus === 'stopping'
  )
    depVariant = 'yellow';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Pill label={`Topology: ${topologyStatus}`} variant={topoVariant} />
      <Pill label={`Deployment: ${depLabel}`} variant={depVariant} />
      <Pill label={t.text} variant={t.variant} />
      {pollLive && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-900/5 px-2 py-0.5 text-[11px] text-zinc-700 dark:bg-white/5 dark:text-zinc-300">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          Live poll
        </span>
      )}
    </div>
  );
}
