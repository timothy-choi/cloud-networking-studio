import { useCallback, useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import {
  getRecentRunnerOperations,
  getRunnerStatus,
  getRuntimeStatus,
  recheckRunnerStatus,
} from '../../api/runnerStatus';
import type { RunnerOperationRecord, RunnerStatusDetail, RuntimeStatusResponse } from '../../types/runnerStatus';
import { formatLastRuntimeError, pickActiveRuntimeError } from '../../types/runnerStatus';

function fmtBool(v: boolean | null | undefined): string {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  return '—';
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok?: boolean | null }) {
  const tone =
    ok === true
      ? 'text-emerald-700 dark:text-emerald-400'
      : ok === false
        ? 'text-amber-800 dark:text-amber-300'
        : 'text-zinc-800 dark:text-zinc-100';
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 py-2 last:border-0 dark:border-zinc-800">
      <span className="text-xs text-cns-muted">{label}</span>
      <span className={`text-right text-xs font-medium ${tone}`}>{value}</span>
    </div>
  );
}

export function RunnerStatusContent({
  runtimeStatus,
  runnerStatus,
  operations,
}: {
  runtimeStatus: RuntimeStatusResponse | null;
  runnerStatus: RunnerStatusDetail | null;
  operations: RunnerOperationRecord[];
}) {
  const rs = runnerStatus ?? runtimeStatus?.runner;
  const checkedAt = runnerStatus?.checked_at ?? runtimeStatus?.checked_at;
  const unreachable = rs?.runner_reachable === false;
  const ops = rs?.supported_operations?.length
    ? rs.supported_operations
    : runtimeStatus?.supported_operations ?? [];
  const activeError = pickActiveRuntimeError(runnerStatus, runtimeStatus);
  const activeErrorText = formatLastRuntimeError(activeError);

  return (
    <div className="space-y-4">
      {unreachable ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100">
          Go runner is not reachable
          {rs?.message ? `: ${rs.message}` : ''}. Deploy and runtime operations may fail when{' '}
          <code className="font-mono text-xs">RUNTIME_EXECUTOR=go</code>.
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-zinc-200 bg-zinc-50/50 px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900/40">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Control plane</h3>
          <div className="mt-2">
            <StatusRow label="Backend runtime executor" value={runtimeStatus?.runtime_executor ?? '—'} />
            <StatusRow
              label="Environment"
              value={runtimeStatus?.environment ?? '—'}
              ok={runtimeStatus?.backend_status === 'ok'}
            />
            <StatusRow
              label="Platform status"
              value={runtimeStatus?.status ?? '—'}
              ok={runtimeStatus?.status === 'ok'}
            />
            <StatusRow label="Last check" value={checkedAt ? new Date(checkedAt).toLocaleString() : '—'} />
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-zinc-50/50 px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900/40">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Go runner</h3>
          <div className="mt-2">
            <StatusRow
              label="Runner reachable"
              value={fmtBool(rs?.runner_reachable)}
              ok={rs?.runner_reachable ?? null}
            />
            <StatusRow label="Runner status" value={rs?.runner_status ?? rs?.status ?? '—'} ok={rs?.runner_status === 'ok' || rs?.status === 'ok'} />
            <StatusRow label="Version" value={rs?.version ?? runtimeStatus?.version ?? '—'} />
            <StatusRow
              label="Build"
              value={
                rs?.git_sha && rs?.build_time
                  ? `${rs.git_sha.slice(0, 7)} · ${rs.build_time}`
                  : rs?.git_sha ?? rs?.build_time ?? '—'
              }
            />
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-zinc-50/50 px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900/40">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Runtime provider</h3>
        <div className="mt-2">
          <StatusRow label="Provider" value={rs?.runtime_provider ?? runtimeStatus?.runtime_provider ?? '—'} />
          <StatusRow
            label="Docker reachable"
            value={fmtBool(rs?.docker_reachable ?? runtimeStatus?.docker_reachable)}
            ok={rs?.docker_reachable ?? runtimeStatus?.docker_reachable ?? null}
          />
          <StatusRow
            label="Kubernetes reachable"
            value={fmtBool(rs?.kubernetes_reachable ?? runtimeStatus?.kubernetes_reachable)}
            ok={rs?.kubernetes_reachable ?? runtimeStatus?.kubernetes_reachable ?? null}
          />
          {(rs?.current_context || runtimeStatus?.current_context) ? (
            <StatusRow label="Kube context" value={rs?.current_context ?? runtimeStatus?.current_context ?? '—'} />
          ) : null}
        </div>
      </div>

      {ops.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Supported operations</h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ops.map((op) => (
              <span
                key={op}
                className="rounded-full border border-zinc-200 bg-white px-2 py-0.5 font-mono text-[10px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              >
                {op}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {activeErrorText ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-100">
          {activeErrorText}
        </div>
      ) : null}

      {operations.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Recent runner operations</h3>
          <div className="mt-2 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-zinc-50 text-cns-label dark:bg-zinc-900/80">
                <tr>
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Operation</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Duration</th>
                  <th className="px-3 py-2 font-medium">Request ID</th>
                  <th className="px-3 py-2 font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((op, i) => (
                  <tr key={`${op.created_at}-${op.operation}-${i}`} className="border-t border-zinc-100 dark:border-zinc-800">
                    <td className="whitespace-nowrap px-3 py-2 text-cns-muted">
                      {new Date(op.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 font-mono">{op.operation}</td>
                    <td className={`px-3 py-2 ${op.status === 'ok' ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-800 dark:text-amber-300'}`}>
                      {op.status_code != null && op.status !== 'ok' ? `${op.status} (${op.status_code})` : op.status}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{op.duration_ms} ms</td>
                    <td className="max-w-[8rem] truncate px-3 py-2 font-mono text-[10px] text-cns-muted" title={op.request_id ?? ''}>
                      {op.request_id ?? '—'}
                    </td>
                    <td className="max-w-[14rem] truncate px-3 py-2 text-cns-muted" title={op.error_message ?? ''}>
                      {op.error_message ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function RunnerStatusPanel() {
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatusResponse | null>(null);
  const [runnerStatus, setRunnerStatus] = useState<RunnerStatusDetail | null>(null);
  const [operations, setOperations] = useState<RunnerOperationRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [rechecking, setRechecking] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [rt, rs, ops] = await Promise.all([
        getRuntimeStatus(),
        getRunnerStatus(),
        getRecentRunnerOperations(15),
      ]);
      setRuntimeStatus(rt);
      setRunnerStatus(rs);
      setOperations(ops.operations);
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const recheck = useCallback(async () => {
    setRechecking(true);
    try {
      const rt = await recheckRunnerStatus();
      const [rs, ops] = await Promise.all([getRunnerStatus(), getRecentRunnerOperations(15)]);
      setRuntimeStatus(rt);
      setRunnerStatus(rs);
      setOperations(ops.operations);
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setRechecking(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (loading && !runtimeStatus && !error) {
    return <p className="text-sm text-cns-muted">Loading runtime provider status…</p>;
  }

  if (error && !runtimeStatus) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100">
        Runtime status unavailable. {error}
      </div>
    );
  }

  return (
    <div>
      <RunnerStatusContent
        runtimeStatus={runtimeStatus}
        runnerStatus={runnerStatus}
        operations={operations}
      />
      <button
        type="button"
        onClick={() => void recheck()}
        disabled={rechecking}
        className="mt-4 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
      >
        {rechecking ? 'Rechecking runner…' : 'Recheck runner'}
      </button>
    </div>
  );
}
