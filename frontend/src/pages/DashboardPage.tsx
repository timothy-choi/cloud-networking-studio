import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatApiError, getControllerStatus, getHealth } from '../api/client';
import { createDemoTopology, listTopologies } from '../api/topologies';
import type { ControllerStatusResponse, HealthResponse, TopologyResponse } from '../types/api';

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${
        ok
          ? 'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-500/30'
          : 'bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-950/50 dark:text-red-300 dark:ring-red-500/30'
      }`}
    >
      {label}
    </span>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [controller, setController] = useState<ControllerStatusResponse | null>(null);
  const [topologies, setTopologies] = useState<TopologyResponse[]>([]);
  const [listErr, setListErr] = useState<string | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);

  const refresh = useCallback(async () => {
    setHealthErr(null);
    setListErr(null);
    try {
      const [h, c, t] = await Promise.all([
        getHealth(),
        getControllerStatus().catch(() => null),
        listTopologies(),
      ]);
      setHealth(h);
      setController(c);
      setTopologies(t);
    } catch (e) {
      setHealthErr(formatApiError(e));
      setHealth(null);
      try {
        setTopologies(await listTopologies());
      } catch (e2) {
        setListErr(formatApiError(e2));
      }
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void refresh();
    });
  }, [refresh]);

  async function onCreateDemo() {
    setDemoLoading(true);
    try {
      const { topologyId } = await createDemoTopology();
      await refresh();
      navigate(`/topologies/${topologyId}`);
    } catch (e) {
      alert(formatApiError(e));
    } finally {
      setDemoLoading(false);
    }
  }

  const healthy = health?.status === 'ok';

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Platform overview
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Design topologies, deploy to Docker, run probes, inject failures, and reconcile drift — all from the
          control plane API.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Backend health</div>
          <div className="mt-2 flex items-center gap-2">
            {health ? (
              <StatusBadge ok={healthy} label={healthy ? 'Reachable' : 'Degraded'} />
            ) : (
              <span className="text-sm text-zinc-500">Checking…</span>
            )}
          </div>
          {health && (
            <p className="mt-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">
              {health.service} · {health.environment}
            </p>
          )}
          {healthErr && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{healthErr}</p>}
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Topologies</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {topologies.length}
          </div>
          <p className="mt-1 text-xs text-zinc-500">Persisted graph definitions</p>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Deployments (managed)</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {controller?.managed_deployments_count ?? '—'}
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            Active: {controller?.active_deployments_count ?? '—'} · Mode {controller?.controller_mode ?? '—'}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void onCreateDemo()}
          disabled={demoLoading}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          {demoLoading ? 'Creating…' : 'Create demo topology'}
        </button>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          Refresh
        </button>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Topologies</h2>
          <p className="text-xs text-zinc-500">Newest first · click to open detail</p>
        </div>
        {listErr ? (
          <p className="p-4 text-sm text-red-600 dark:text-red-400">{listErr}</p>
        ) : topologies.length === 0 ? (
          <p className="p-6 text-sm text-zinc-500">No topologies yet — create a demo or use the API.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {topologies.map((t) => (
              <li key={t.id}>
                <Link
                  to={`/topologies/${t.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                >
                  <div>
                    <div className="font-medium text-zinc-900 dark:text-zinc-100">{t.name}</div>
                    <div className="font-mono text-xs text-zinc-500">{t.id}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      {t.status}
                    </span>
                    <span className="text-xs text-zinc-500">{t.runtime_target}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
