import { useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatApiError, getControllerStatus, getHealth } from '../api/client';
import { createDemoTopology, listTopologies } from '../api/topologies';
import { CreateBlankTopologyModal } from '../components/CreateBlankTopologyModal';
import { Spinner } from '../components/Spinner';
import { usePolling } from '../hooks/usePolling';
import type { ControllerStatusResponse, HealthResponse, TopologyResponse } from '../types';

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
  const [templateLoading, setTemplateLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [blankOpen, setBlankOpen] = useState(false);

  const refresh = useCallback(async () => {
    setHealthErr(null);
    setListErr(null);
    setRefreshing(true);
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
    } finally {
      setRefreshing(false);
    }
  }, []);

  usePolling(refresh, 10_000, true);

  async function onCreateFromTemplate() {
    setTemplateLoading(true);
    try {
      const { topologyId } = await createDemoTopology();
      await refresh();
      navigate(`/topologies/${topologyId}`);
    } catch (e) {
      alert(formatApiError(e));
    } finally {
      setTemplateLoading(false);
    }
  }

  const healthy = health?.status === 'ok';

  return (
    <div className="space-y-8">
      <CreateBlankTopologyModal
        open={blankOpen}
        onClose={() => setBlankOpen(false)}
        onCreated={(topologyId) => {
          void refresh();
          navigate(`/topologies/${topologyId}`);
        }}
      />

      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Topology studio
          </h1>
          {refreshing && <Spinner className="h-5 w-5" />}
        </div>
        <p className="mt-1 max-w-2xl text-sm text-cns-muted">
          Design environments, attach a runtime, and operate workloads. Topologies refresh every 10s.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-cns-label">Backend health</div>
          <div className="mt-2 flex items-center gap-2">
            {health ? (
              <StatusBadge ok={healthy} label={healthy ? 'Reachable' : 'Degraded'} />
            ) : (
              <span className="flex items-center gap-2 text-sm text-cns-muted">
                <Spinner className="h-4 w-4" /> Checking…
              </span>
            )}
          </div>
          {health && (
            <p className="mt-2 font-mono text-xs text-cns-muted">
              {health.service} · {health.environment}
            </p>
          )}
          {healthErr && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{healthErr}</p>}
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-cns-label">Topologies</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {topologies.length}
          </div>
          <p className="mt-1 text-xs text-cns-muted">Saved lab graphs</p>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="text-xs font-medium uppercase tracking-wide text-cns-label">Deployments (managed)</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {controller?.managed_deployments_count ?? '—'}
          </div>
          <p className="mt-1 text-xs text-cns-muted">
            Active: {controller?.active_deployments_count ?? '—'} · Mode {controller?.controller_mode ?? '—'}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">New topology</h2>
        <p className="mt-1 text-xs text-cns-muted">
          Start from scratch or load a starter graph. Templates only append nodes and links — they never replace your
          work unless you use “Replace with sample lab” inside the editor.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setBlankOpen(true)}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            Create blank topology
          </button>
          <button
            type="button"
            onClick={() => void onCreateFromTemplate()}
            disabled={templateLoading}
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {templateLoading ? 'Creating…' : 'Create from template'}
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {refreshing ? <Spinner className="h-4 w-4" /> : null}
            Refresh now
          </button>
        </div>
        <p className="mt-4 border-t border-zinc-100 pt-3 text-[11px] leading-relaxed text-cns-muted dark:border-zinc-800">
          For scripted environments, see{' '}
          <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:bg-zinc-800">scripts/demo_full_flow.sh</code>{' '}
          in the repo (optional; lower priority than the UI flows above).
        </p>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Your topologies</h2>
          <p className="text-xs text-cns-muted">Newest first · open to edit and deploy</p>
        </div>
        {listErr ? (
          <p className="p-4 text-sm text-red-600 dark:text-red-400">{listErr}</p>
        ) : topologies.length === 0 ? (
          <p className="p-6 text-sm text-cns-muted">
            No topologies yet — create a blank lab or use a template, or use the REST API.
          </p>
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
                    <div className="font-mono text-xs text-cns-muted">{t.id}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      {t.status}
                    </span>
                    <span className="text-xs text-cns-muted">{t.runtime_target}</span>
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
