import type { ControlPlanePhase } from '../../lib/deploymentUiPhase';

const PHASE_STYLES: Record<
  ControlPlanePhase,
  { pill: string; bar: string }
> = {
  inactive: {
    pill: 'border-zinc-600 bg-zinc-900 text-zinc-300',
    bar: 'bg-zinc-600',
  },
  ready: {
    pill: 'border-sky-700 bg-sky-950/60 text-sky-100',
    bar: 'bg-sky-500',
  },
  deploying: {
    pill: 'border-amber-600 bg-amber-950/50 text-amber-100',
    bar: 'bg-amber-400',
  },
  healthy: {
    pill: 'border-emerald-700 bg-emerald-950/45 text-emerald-100',
    bar: 'bg-emerald-400',
  },
  degraded: {
    pill: 'border-orange-600 bg-orange-950/40 text-orange-100',
    bar: 'bg-orange-400',
  },
  healing: {
    pill: 'border-yellow-600 bg-yellow-950/35 text-yellow-100',
    bar: 'bg-yellow-400',
  },
  failed: {
    pill: 'border-red-700 bg-red-950/50 text-red-100',
    bar: 'bg-red-500',
  },
  stopped: {
    pill: 'border-zinc-600 bg-zinc-900 text-zinc-300',
    bar: 'bg-zinc-500',
  },
};

export function DeploymentPhaseStrip({
  phase,
  shortLabel,
  description,
}: {
  phase: ControlPlanePhase;
  shortLabel: string;
  description: string;
}) {
  const st = PHASE_STYLES[phase];
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-700/80 bg-zinc-950/40 px-4 py-3 dark:border-zinc-700">
      <div className={`h-10 w-1.5 shrink-0 rounded-full ${st.bar}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-cns-inverse-muted">Control plane phase</span>
          <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${st.pill}`}>{shortLabel}</span>
        </div>
        <p className="mt-1 text-xs leading-snug text-zinc-300">{description}</p>
      </div>
    </div>
  );
}
