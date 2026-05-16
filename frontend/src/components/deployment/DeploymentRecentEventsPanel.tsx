import type { DeploymentEventResponse } from '../../types/deployment';

export function DeploymentRecentEventsPanel({
  events,
  pollErr,
}: {
  events: DeploymentEventResponse[];
  pollErr: string | null;
}) {
  const recent = [...events]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 8);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Recent events</h3>
        <a href="#deployment-events" className="text-[11px] font-medium text-sky-700 hover:underline dark:text-sky-400">
          Full log ↓
        </a>
      </div>
      {pollErr ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{pollErr}</p> : null}
      {recent.length === 0 ? (
        <p className="mt-3 text-sm text-cns-muted">No deployment events yet — deploy to see provisioning output.</p>
      ) : (
        <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
          {recent.map((ev) => (
            <li key={ev.id} className="flex gap-2 py-2 text-xs first:pt-0">
              <span
                className={`shrink-0 rounded px-1 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                  ev.level === 'error'
                    ? 'bg-red-100 text-red-900 dark:bg-red-950/60 dark:text-red-200'
                    : ev.level === 'warning'
                      ? 'bg-amber-100 text-amber-950 dark:bg-amber-950/50 dark:text-amber-100'
                      : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
                }`}
              >
                {ev.level}
              </span>
              <span className="min-w-0 flex-1 leading-snug text-zinc-800 dark:text-zinc-100">{ev.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
