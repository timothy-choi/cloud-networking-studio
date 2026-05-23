import { useCallback, useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import { getDeploymentTimeline } from '../../api/deployments';
import type { TimelineEventResponse } from '../../types/deploymentTimeline';

function fmtTs(iso: string): string {
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

function statusTone(status: string): string {
  if (status === 'failed') return 'bg-red-500';
  if (status === 'succeeded') return 'bg-emerald-400';
  if (status === 'running') return 'bg-sky-400';
  return 'bg-zinc-500';
}

export function DeploymentOperationTimeline({ deploymentId }: { deploymentId: string | null }) {
  const [events, setEvents] = useState<TimelineEventResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!deploymentId) {
      setEvents([]);
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const body = await getDeploymentTimeline(deploymentId);
      setEvents(body.events);
    } catch (e) {
      setErr(formatApiError(e));
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!deploymentId) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Operation timeline</h3>
        <p className="text-[11px] text-cns-muted">
          Structured deploy/destroy lifecycle events with correlation IDs (oldest first).
        </p>
      </div>
      {err ? (
        <div className="px-3 py-4 text-xs text-red-700 dark:text-red-300">{err}</div>
      ) : loading && events.length === 0 ? (
        <div className="px-3 py-6 text-center text-sm text-cns-muted">Loading timeline…</div>
      ) : events.length === 0 ? (
        <div className="px-3 py-6 text-center text-sm text-cns-muted">No operation events yet.</div>
      ) : (
        <ul className="max-h-72 divide-y divide-zinc-100 overflow-auto dark:divide-zinc-800">
          {events.map((ev) => (
            <TimelineRow key={ev.id} event={ev} />
          ))}
        </ul>
      )}
    </div>
  );
}

function TimelineRow({ event }: { event: TimelineEventResponse }) {
  const [open, setOpen] = useState(false);
  const failed = event.status === 'failed';
  const meta = event.metadata;
  const errorDetail =
    failed && meta && typeof meta.error === 'string'
      ? meta.error
      : failed && meta?.errors
        ? JSON.stringify(meta.errors)
        : null;

  return (
    <li className="px-3 py-2 text-xs">
      <div className="flex gap-3">
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusTone(event.status)}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase text-indigo-900 dark:bg-indigo-950/80 dark:text-indigo-100">
              {event.event_type}
            </span>
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {event.status}
            </span>
            <span className="font-mono text-[10px] text-cns-muted">{fmtTs(event.created_at)}</span>
          </div>
          <div className="mt-0.5 font-medium text-zinc-800 dark:text-zinc-100">{event.message}</div>
          {event.request_id ? (
            <div className="mt-1 font-mono text-[10px] text-cns-muted">request_id: {event.request_id}</div>
          ) : null}
          {failed && (errorDetail || meta) ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="mt-1 text-[10px] font-medium text-amber-800 underline dark:text-amber-300"
            >
              {open ? 'Hide' : 'Show'} error details
            </button>
          ) : null}
          {open && errorDetail ? (
            <pre className="mt-1 max-h-32 overflow-auto rounded bg-zinc-100 p-2 font-mono text-[10px] text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
              {errorDetail}
            </pre>
          ) : null}
        </div>
      </div>
    </li>
  );
}
