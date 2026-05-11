import { useMemo } from 'react';

import type { TrafficTestResponse, TrafficTestType } from '../../types/traffic';

import { TrafficTestHistory } from './TrafficTestHistory';

function latestOfType(tests: TrafficTestResponse[], type: TrafficTestType): TrafficTestResponse | null {
  const hits = tests.filter((t) => t.test_type === type);
  if (!hits.length) return null;
  return [...hits].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
}

function ResultCard({
  label,
  test,
}: {
  label: string;
  test: TrafficTestResponse | null;
}) {
  const ok = test?.status === 'succeeded';
  const latency =
    test?.result?.latency_ms != null ? `${test.result.latency_ms.toFixed(1)} ms` : '—';
  const summary = test?.result
    ? test.result.success
      ? 'ok'
      : `exit ${test.result.exit_code}`
    : '—';

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-label">{label}</div>
      {!test ? (
        <p className="mt-2 text-sm text-cns-muted">No runs yet</p>
      ) : (
        <>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <span
              className={`text-sm font-semibold ${ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}
            >
              {test.status}
            </span>
            <span className="font-mono text-xs text-cns-muted">{formatTs(test.created_at)}</span>
          </div>
          <div className="mt-2 grid gap-1 text-xs text-zinc-700 dark:text-zinc-300">
            <div className="flex justify-between gap-2">
              <span className="text-cns-muted">Latency</span>
              <span className="font-mono">{latency}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-cns-muted">Result</span>
              <span className="max-w-[140px] truncate font-mono text-right" title={test.result?.stdout}>
                {summary}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function formatTs(iso: string): string {
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

interface Props {
  tests: TrafficTestResponse[];
  pollError?: string | null;
}

/** Traffic validation: last ping / HTTP cards plus full history table. */
export function TrafficValidationSection({ tests, pollError }: Props) {
  const lastPing = useMemo(() => latestOfType(tests, 'ping'), [tests]);
  const lastHttp = useMemo(() => latestOfType(tests, 'http'), [tests]);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Traffic validation</h2>
          <p className="mt-0.5 text-xs text-cns-muted">
            Last ping and HTTP results · full history below · auto-refreshed with runtime polling
          </p>
        </div>
      </div>
      {pollError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Traffic poll: {pollError}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <ResultCard label="Last ping test" test={lastPing} />
        <ResultCard label="Last HTTP test" test={lastHttp} />
      </div>
      <TrafficTestHistory tests={tests} embedded />
    </section>
  );
}
