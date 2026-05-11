import { useEffect, useMemo, useRef, useState } from 'react';
import type { DeploymentEventLevel } from '../../types/deployment';
import type { DeploymentEventResponse } from '../../types/deployment';

type LevelFilter = DeploymentEventLevel | 'all';

interface Props {
  events: DeploymentEventResponse[];
  loading?: boolean;
}

export function DeploymentEventStream({ events, loading }: Props) {
  const [filter, setFilter] = useState<LevelFilter>('all');
  const [newestFirst, setNewestFirst] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const rows = filter === 'all' ? events : events.filter((e) => e.level === filter);
    const sorted = [...rows].sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      return newestFirst ? tb - ta : ta - tb;
    });
    return sorted;
  }, [events, filter, newestFirst]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (newestFirst) {
      el.scrollTop = 0;
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered, newestFirst]);

  return (
    <div className="flex flex-col rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">Deployment events</span>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as LevelFilter)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-600 dark:bg-zinc-950"
        >
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
          <option value="debug">Debug</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
          <input
            type="checkbox"
            checked={newestFirst}
            onChange={(e) => setNewestFirst(e.target.checked)}
          />
          Newest first
        </label>
        {loading && <span className="text-xs text-zinc-400">Updating…</span>}
      </div>
      <div ref={listRef} className="max-h-80 overflow-auto">
        {filtered.length === 0 ? (
          <p className="p-4 text-sm text-zinc-500">No events match filters.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {filtered.map((ev) => (
              <li key={ev.id} className="flex gap-3 px-3 py-2 text-xs">
                <LevelBadge level={ev.level} />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[10px] text-zinc-500">{formatTs(ev.created_at)}</div>
                  <div className="mt-0.5 text-zinc-700 dark:text-zinc-200">{ev.message}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function LevelBadge({ level }: { level: DeploymentEventLevel }) {
  const cls =
    level === 'error'
      ? 'bg-red-500/15 text-red-700 dark:text-red-300'
      : level === 'warning'
        ? 'bg-amber-500/15 text-amber-800 dark:text-amber-200'
        : level === 'debug'
          ? 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-400'
          : 'bg-sky-500/15 text-sky-800 dark:text-sky-200';
  return (
    <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 font-medium uppercase tracking-wide ${cls}`}>
      {level}
    </span>
  );
}

function formatTs(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
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
