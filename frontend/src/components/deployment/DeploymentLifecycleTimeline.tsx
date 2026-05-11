import { useMemo } from 'react';

import type { DeploymentEventResponse } from '../../types/deployment';
import type { FailureInjectionResponse } from '../../types/failure';
import type { TrafficTestResponse } from '../../types/traffic';

type Tone = 'neutral' | 'info' | 'warn' | 'error' | 'ok';

interface TimelineRow {
  id: string;
  at: string;
  category: string;
  title: string;
  subtitle?: string | null;
  tone: Tone;
}

function classifyEvent(ev: DeploymentEventResponse): { cat: string; tone: Tone } {
  const m = ev.message.toLowerCase();
  if (ev.level === 'error') return { cat: 'deployment', tone: 'error' };
  if (ev.level === 'warning') return { cat: 'deployment', tone: 'warn' };
  if (/heal|healing/.test(m)) return { cat: 'heal', tone: 'ok' };
  if (/reconcil/.test(m)) return { cat: 'reconcile', tone: 'info' };
  if (/provision|deploy|runtime target/.test(m)) return { cat: 'deploy', tone: 'info' };
  if (/destroy|teardown|stop deployment/.test(m)) return { cat: 'lifecycle', tone: 'warn' };
  return { cat: 'deployment', tone: ev.level === 'debug' ? 'neutral' : 'info' };
}

export function DeploymentLifecycleTimeline({
  events,
  trafficTests,
  failures,
}: {
  events: DeploymentEventResponse[];
  trafficTests: TrafficTestResponse[];
  failures: FailureInjectionResponse[];
}) {
  const rows = useMemo(() => {
    const list: TimelineRow[] = [];
    for (const e of events) {
      const { cat, tone } = classifyEvent(e);
      list.push({
        id: `ev-${e.id}`,
        at: e.created_at,
        category: cat,
        title: e.message,
        subtitle: e.level,
        tone,
      });
    }
    for (const t of trafficTests) {
      list.push({
        id: `tt-${t.id}`,
        at: t.created_at,
        category: 'traffic',
        title: `${t.test_type.toUpperCase()} test`,
        subtitle: t.command?.slice(0, 80),
        tone: t.result?.success === false ? 'error' : 'ok',
      });
    }
    for (const f of failures) {
      list.push({
        id: `fail-${f.id}`,
        at: f.created_at,
        category: 'failure',
        title: `${f.failure_type.replace(/_/g, ' ')}`,
        subtitle: f.description,
        tone: f.status === 'failed' ? 'error' : 'warn',
      });
    }
    list.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
    return list.slice(0, 80);
  }, [events, trafficTests, failures]);

  const toneDot: Record<Tone, string> = {
    neutral: 'bg-zinc-500',
    info: 'bg-sky-400',
    warn: 'bg-amber-400',
    error: 'bg-red-500',
    ok: 'bg-emerald-400',
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Deployment history</h3>
        <p className="text-[11px] text-cns-muted">
          Recent deployment events, traffic tests, and failure injections (newest first).
        </p>
      </div>
      <ul className="max-h-72 divide-y divide-zinc-100 overflow-auto dark:divide-zinc-800">
        {rows.length === 0 ? (
          <li className="px-3 py-6 text-center text-sm text-cns-muted">No history yet.</li>
        ) : (
          rows.map((r) => (
            <li key={r.id} className="flex gap-3 px-3 py-2 text-xs">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${toneDot[r.tone]}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    {r.category}
                  </span>
                  <span className="font-mono text-[10px] text-cns-muted">{fmtTs(r.at)}</span>
                </div>
                <div className="mt-0.5 font-medium text-zinc-800 dark:text-zinc-100">{r.title}</div>
                {r.subtitle ? (
                  <div className="mt-0.5 line-clamp-2 text-cns-muted">{r.subtitle}</div>
                ) : null}
              </div>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

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
