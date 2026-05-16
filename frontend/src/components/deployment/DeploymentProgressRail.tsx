import type { DeploymentStatus } from '../../types/deployment';

type StepVariant = 'complete' | 'active' | 'inactive' | 'error';

interface Step {
  key: string;
  label: string;
  variant: StepVariant;
}

function buildSteps(deploymentId: string | null, status: DeploymentStatus | null): Step[] {
  const labels = ['Created', 'Provisioning', 'Running', 'Failed', 'Destroyed'] as const;

  const base = (variants: StepVariant[]): Step[] =>
    labels.map((label, i) => ({
      key: label.toLowerCase(),
      label,
      variant: variants[i] ?? 'inactive',
    }));

  if (!deploymentId) {
    return base(['active', 'inactive', 'inactive', 'inactive', 'inactive']);
  }

  switch (status) {
    case 'pending':
      return base(['complete', 'active', 'inactive', 'inactive', 'inactive']);
    case 'deploying':
    case 'stopping':
      return base(['complete', 'active', 'inactive', 'inactive', 'inactive']);
    case 'succeeded':
      return base(['complete', 'complete', 'complete', 'inactive', 'inactive']);
    case 'failed':
      return base(['complete', 'complete', 'inactive', 'error', 'inactive']);
    case 'stopped':
      return base(['complete', 'complete', 'complete', 'inactive', 'complete']);
    default:
      return base(['active', 'inactive', 'inactive', 'inactive', 'inactive']);
  }
}

function caption(deploymentId: string | null, status: DeploymentStatus | null): string {
  if (!deploymentId) return 'No deployment yet — use Deploy to runtime when the topology is ready.';
  switch (status) {
    case 'pending':
      return 'Deployment record created — provisioning is starting.';
    case 'deploying':
      return 'Provisioning networks and containers.';
    case 'stopping':
      return 'Stopping workloads and releasing resources.';
    case 'succeeded':
      return 'Deployment is running in the runtime.';
    case 'failed':
      return 'Last deployment failed — fix issues or retry below.';
    case 'stopped':
      return 'Deployment destroyed — create a new deployment to run workloads again.';
    default:
      return '';
  }
}

const VARIANT_RING: Record<StepVariant, string> = {
  complete: 'border-emerald-500 bg-emerald-500 text-white dark:border-emerald-400 dark:bg-emerald-600',
  active: 'border-amber-500 bg-amber-500 text-white ring-2 ring-amber-300/60 dark:border-amber-400 dark:bg-amber-500',
  inactive: 'border-zinc-300 bg-white text-zinc-400 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-500',
  error: 'border-red-600 bg-red-600 text-white dark:border-red-500 dark:bg-red-500',
};

export function DeploymentProgressRail({
  deploymentId,
  status,
}: {
  deploymentId: string | null;
  status: DeploymentStatus | null;
}) {
  const steps = buildSteps(deploymentId, status);
  const cap = caption(deploymentId, status);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Deployment progress</h3>
        <span className="text-[10px] font-mono text-cns-muted">
          {status ?? (deploymentId ? 'unknown' : 'none')}
        </span>
      </div>
      <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{cap}</p>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
        {steps.map((s, idx) => (
          <div key={s.key} className="flex flex-col items-center text-center">
            <div className="flex w-full items-center justify-center">
              {idx > 0 ? (
                <div
                  className={`mr-1 hidden h-0.5 flex-1 sm:block ${
                    steps[idx - 1].variant === 'complete' ? 'bg-emerald-400' : 'bg-zinc-200 dark:bg-zinc-700'
                  }`}
                  aria-hidden
                />
              ) : null}
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-bold ${VARIANT_RING[s.variant]}`}
                aria-current={s.variant === 'active' ? 'step' : undefined}
              >
                {idx + 1}
              </span>
              {idx < steps.length - 1 ? (
                <div
                  className={`ml-1 hidden h-0.5 flex-1 sm:block ${
                    s.variant === 'complete' ? 'bg-emerald-400' : 'bg-zinc-200 dark:bg-zinc-700'
                  }`}
                  aria-hidden
                />
              ) : null}
            </div>
            <span className="mt-2 max-w-[6rem] text-[10px] font-medium leading-tight text-zinc-600 dark:text-zinc-400">
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
