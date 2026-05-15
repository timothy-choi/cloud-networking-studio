import { useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatApiError, getControllerStatus, getHealth } from '../api/client';
import { getMetricsSummary } from '../api/metrics';
import { createDemoTopology, deleteTopology, listTopologies } from '../api/topologies';
import { CreateBlankTopologyModal } from '../components/CreateBlankTopologyModal';
import { Spinner } from '../components/Spinner';
import { usePolling } from '../hooks/usePolling';
import type { ControllerStatusResponse, HealthResponse, TopologyResponse } from '../types';
import type { MetricsSummaryResponse } from '../types/metrics';

function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      hour12: false,
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

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
  const [metrics, setMetrics] = useState<MetricsSummaryResponse | null>(null);
  const [metricsErr, setMetricsErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setHealthErr(null);
    setListErr(null);
    setMetricsErr(null);
    setRefreshing(true);
    try {
      const [h, c, t, m] = await Promise.all([
        getHealth(),
        getControllerStatus().catch(() => null),
        listTopologies(),
        getMetricsSummary().catch(() => null),
      ]);
      setHealth(h);
      setController(c);
      setTopologies(t);
      setMetrics(m);
    } catch (e) {
      setHealthErr(formatApiError(e));
      setHealth(null);
      setMetrics(null);
      try {
        setTopologies(await listTopologies());
      } catch (e2) {
        setListErr(formatApiError(e2));
      }
      try {
        setMetrics(await getMetricsSummary());
      } catch {
        setMetricsErr('Metrics summary unavailable');
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
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Observability</h2>
          <span className="text-[11px] text-cns-muted">
            <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:bg-zinc-800">GET /metrics/summary</code>
            · see <code className="font-mono text-[10px]">docs/OBSERVABILITY.md</code>
          </span>
        </div>
        {metricsErr ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{metricsErr}</p> : null}
        {metrics ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
              <div className="text-[10px] font-semibold uppercase text-cns-label">Active deployments</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
                {metrics.active_deployments}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
              <div className="text-[10px] font-semibold uppercase text-cns-label">Failed deployments</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-red-700 dark:text-red-400">
                {metrics.failed_deployments}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
              <div className="text-[10px] font-semibold uppercase text-cns-label">Traffic tests (fail / total)</div>
              <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
                {metrics.failed_traffic_tests} / {metrics.total_traffic_tests}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
              <div className="text-[10px] font-semibold uppercase text-cns-label">Failure injections (fail / total)</div>
              <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
                {metrics.failed_failure_injections} / {metrics.total_failure_injections}
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-xs text-cns-muted">Loading metrics…</p>
        )}
        {metrics && metrics.latest_events.length > 0 ? (
          <div className="mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Recent deployment events</h3>
            <ul className="mt-2 max-h-48 divide-y divide-zinc-100 overflow-auto rounded-lg border border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
              {metrics.latest_events.slice(0, 12).map((ev) => (
                <li key={ev.id} className="flex flex-wrap items-start gap-2 px-2 py-1.5 text-xs">
                  <span
                    className={`shrink-0 rounded px-1 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                      ev.level === 'error'
                        ? 'bg-red-100 text-red-900 dark:bg-red-950/60 dark:text-red-200'
                        : ev.level === 'warning'
                          ? 'bg-amber-100 text-amber-950 dark:bg-amber-950/50 dark:text-amber-100'
                          : 'bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200'
                    }`}
                  >
                    {ev.level}
                  </span>
                  <Link to={`/topologies/${ev.topology_id}`} className="shrink-0 font-mono text-[10px] text-sky-700 hover:underline dark:text-sky-400">
                    topo…
                  </Link>
                  <span className="min-w-0 flex-1 text-zinc-800 dark:text-zinc-100">{ev.message}</span>
                  <span className="shrink-0 font-mono text-[10px] text-cns-muted">{fmtWhen(ev.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
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
              <li key={t.id} className="flex items-stretch">
                <Link
                  to={`/topologies/${t.id}`}
                  className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-zinc-900 dark:text-zinc-100">{t.name}</div>
                    <div className="font-mono text-xs text-cns-muted">{t.id}</div>
                    <div className="mt-1 text-[11px] text-cns-muted">
                      {t.node_count ?? 0} nodes · {t.link_count ?? 0} links · updated {fmtWhen(t.updated_at)}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      {t.status}
                    </span>
                    <span className="text-xs text-cns-muted">{t.runtime_target}</span>
                  </div>
                </Link>
                <button
                  type="button"
                  title="Delete topology"
                  className="shrink-0 border-l border-zinc-200 px-3 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-zinc-800 dark:text-red-400 dark:hover:bg-red-950/40"
                  onClick={async (e) => {
                    e.preventDefault();
                    if (
                      !window.confirm(
                        `Delete topology “${t.name}” and all nodes, links, and deployment records? This cannot be undone.`,
                      )
                    ) {
                      return;
                    }
                    try {
                      await deleteTopology(t.id);
                      await refresh();
                    } catch (err) {
                      alert(formatApiError(err));
                    }
                  }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
