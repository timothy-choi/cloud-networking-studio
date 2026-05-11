import { useEffect, useMemo, useRef, useState } from 'react';

import type { DeploymentEventLevel } from '../../types/deployment';
import type { DeploymentEventResponse } from '../../types/deployment';

type LevelFilter = DeploymentEventLevel | 'all';

interface Props {
  events: DeploymentEventResponse[];
  loading?: boolean;
  /** Hide repetitive runtime inspection noise until user opts in. */
  hideInspectionByDefault?: boolean;
  variant?: 'default' | 'compact';
  className?: string;
  listClassName?: string;
}

type DisplayRow =
  | { kind: 'event'; event: DeploymentEventResponse }
  | { kind: 'collapsed'; count: number; sample: DeploymentEventResponse };

function isInspectionNoise(ev: DeploymentEventResponse): boolean {
  const m = ev.message.toLowerCase();
  return (
    (ev.level === 'info' || ev.level === 'debug') &&
    (/runtime inspect|snapshot|polling|poll\b|refresh runtime|describe container/i.test(m) ||
      /^(ok|heartbeat)/i.test(m))
  );
}

function buildRows(sorted: DeploymentEventResponse[]): DisplayRow[] {
  const out: DisplayRow[] = [];
  let i = 0;
  while (i < sorted.length) {
    const ev = sorted[i];
    if (isInspectionNoise(ev)) {
      let count = 1;
      let j = i + 1;
      while (j < sorted.length && isInspectionNoise(sorted[j]) && sorted[j].message === ev.message) {
        count += 1;
        j += 1;
      }
      if (count >= 4) {
        out.push({ kind: 'collapsed', count, sample: ev });
        i = j;
        continue;
      }
    }
    out.push({ kind: 'event', event: ev });
    i += 1;
  }
  return out;
}

export function DeploymentEventStream({
  events,
  loading,
  hideInspectionByDefault,
  variant = 'default',
  className,
  listClassName,
}: Props) {
  const [filter, setFilter] = useState<LevelFilter>('all');
  const [newestFirst, setNewestFirst] = useState(true);
  const [showInspection, setShowInspection] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const baseEvents = useMemo(() => {
    if (!hideInspectionByDefault || showInspection) return events;
    return events.filter((e) => !isInspectionNoise(e));
  }, [events, hideInspectionByDefault, showInspection]);

  const filtered = useMemo(() => {
    const rows = filter === 'all' ? baseEvents : baseEvents.filter((e) => e.level === filter);
    return [...rows].sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      return newestFirst ? tb - ta : ta - tb;
    });
  }, [baseEvents, filter, newestFirst]);

  const displayRows = useMemo(() => buildRows(filtered), [filtered]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (newestFirst) {
      el.scrollTop = 0;
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [displayRows, newestFirst, baseEvents.length]);

  const headerPad = variant === 'compact' ? 'px-2.5 py-1.5' : 'px-3 py-2';
  const titleCls = variant === 'compact' ? 'text-[11px]' : 'text-xs';

  return (
    <div
      className={`flex flex-col rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80 ${className ?? ''}`}
    >
      <div
        className={`flex flex-wrap items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 ${headerPad}`}
      >
        <span className={`font-semibold text-zinc-800 dark:text-zinc-100 ${titleCls}`}>Deployment events</span>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as LevelFilter)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
        >
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
          <option value="debug">Debug</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-cns-muted">
          <input
            type="checkbox"
            checked={newestFirst}
            onChange={(e) => setNewestFirst(e.target.checked)}
          />
          Newest first
        </label>
        {hideInspectionByDefault ? (
          <label className="flex items-center gap-1.5 text-[11px] text-cns-muted">
            <input
              type="checkbox"
              checked={showInspection}
              onChange={(e) => setShowInspection(e.target.checked)}
            />
            Show inspection noise
          </label>
        ) : null}
        {loading ? <span className="text-xs text-cns-muted">Updating…</span> : null}
      </div>
      <div
        ref={listRef}
        className={`overflow-auto scroll-smooth ${listClassName ?? 'max-h-80'}`.trim()}
      >
        {displayRows.length === 0 ? (
          <p className="p-4 text-sm text-cns-muted">No events match filters.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {displayRows.map((row, idx) =>
              row.kind === 'collapsed' ? (
                <li
                  key={`c-${row.sample.id}-${idx}`}
                  className="border-l-2 border-zinc-600 bg-zinc-50/80 px-3 py-1.5 text-[11px] text-zinc-600 dark:bg-zinc-950/40 dark:text-zinc-400"
                >
                  <span className="font-mono text-[10px] text-zinc-600 dark:text-zinc-500">
                    {row.count}× similar:{' '}
                  </span>
                  {row.sample.message}
                </li>
              ) : (
                <EventRow key={row.event.id} event={row.event} />
              ),
            )}
          </ul>
        )}
      </div>
    </div>
  );
}

function EventRow({ event }: { event: DeploymentEventResponse }) {
  const stripe =
    event.level === 'error'
      ? 'border-l-4 border-red-500 bg-red-50/80 dark:bg-red-950/25'
      : event.level === 'warning'
        ? 'border-l-4 border-amber-400 bg-amber-50/70 dark:bg-amber-950/25'
        : event.level === 'debug'
          ? 'border-l-4 border-zinc-500 bg-zinc-50/50 dark:bg-zinc-950/50'
          : 'border-l-4 border-sky-500 bg-sky-50/40 dark:bg-sky-950/20';

  return (
    <li className={`flex gap-3 px-3 py-2 text-xs ${stripe}`}>
      <LevelBadge level={event.level} />
      <div className="min-w-0 flex-1">
        <div className="font-mono text-[10px] text-cns-muted">{formatTs(event.created_at)}</div>
        <div className="mt-0.5 text-zinc-800 dark:text-zinc-100">{event.message}</div>
      </div>
    </li>
  );
}

function LevelBadge({ level }: { level: DeploymentEventLevel }) {
  const cls =
    level === 'error'
      ? 'bg-red-600/15 text-red-800 dark:text-red-200'
      : level === 'warning'
        ? 'bg-amber-500/20 text-amber-900 dark:text-amber-100'
        : level === 'debug'
          ? 'bg-zinc-600/25 text-zinc-800 dark:text-zinc-300'
          : 'bg-sky-600/15 text-sky-900 dark:text-sky-100';
  return (
    <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
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
