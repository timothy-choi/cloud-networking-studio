import { useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatApiError, getControllerStatus, getHealth } from '../api/client';
import { getMetricsSummary } from '../api/metrics';
import { listProjects } from '../api/projects';
import type { ProjectResponse } from '../api/projects';
import { createDemoTopology, deleteTopology, listTopologies } from '../api/topologies';
import { CreateBlankTopologyModal } from '../components/CreateBlankTopologyModal';
import { CreateProjectModal } from '../components/CreateProjectModal';
import { Spinner } from '../components/Spinner';
import { usePolling } from '../hooks/usePolling';
import type { ControllerStatusResponse, HealthResponse, TopologyResponse } from '../types';
import type { MetricsSummaryResponse } from '../types/metrics';
import { CNS_SELECTED_PROJECT_KEY } from '../auth/storage';

function readSessionProjectId(): string | null {
  try {
    return sessionStorage.getItem(CNS_SELECTED_PROJECT_KEY);
  } catch {
    return null;
  }
}

function writeSessionProjectId(id: string | null): void {
  try {
    if (id) sessionStorage.setItem(CNS_SELECTED_PROJECT_KEY, id);
    else sessionStorage.removeItem(CNS_SELECTED_PROJECT_KEY);
  } catch {
    // ignore
  }
}

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
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [blankOpen, setBlankOpen] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [metrics, setMetrics] = useState<MetricsSummaryResponse | null>(null);
  const [metricsErr, setMetricsErr] = useState<string | null>(null);

  const refresh = useCallback(
    async (projectIdOverride?: string | null) => {
      setHealthErr(null);
      setListErr(null);
      setMetricsErr(null);
      setRefreshing(true);
      try {
        const projs = await listProjects();
        setProjects(projs);
        let nextSel: string | null = null;
        if (projectIdOverride != null && projs.some((p) => p.id === projectIdOverride)) {
          nextSel = projectIdOverride;
        } else if (selectedProjectId && projs.some((p) => p.id === selectedProjectId)) {
          nextSel = selectedProjectId;
        } else {
          const stored = readSessionProjectId();
          if (stored && projs.some((p) => p.id === stored)) nextSel = stored;
          else nextSel = projs[0]?.id ?? null;
        }
        setSelectedProjectId(nextSel);
        writeSessionProjectId(nextSel);

        const [h, c, t, m] = await Promise.all([
          getHealth(),
          getControllerStatus().catch(() => null),
          listTopologies(nextSel ?? undefined),
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
          const projs = await listProjects();
          setProjects(projs);
          let nextSel: string | null = null;
          if (projectIdOverride != null && projs.some((p) => p.id === projectIdOverride)) {
            nextSel = projectIdOverride;
          } else if (selectedProjectId && projs.some((p) => p.id === selectedProjectId)) {
            nextSel = selectedProjectId;
          } else {
            const stored = readSessionProjectId();
            if (stored && projs.some((p) => p.id === stored)) nextSel = stored;
            else nextSel = projs[0]?.id ?? null;
          }
          setSelectedProjectId(nextSel);
          writeSessionProjectId(nextSel);
          setTopologies(await listTopologies(nextSel ?? undefined));
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
    },
    [selectedProjectId],
  );

  usePolling(refresh, 10_000, true);

  async function onCreateFromTemplate() {
    if (!selectedProjectId) {
      alert('Create or select a project first.');
      return;
    }
    setTemplateLoading(true);
    try {
      const { topologyId } = await createDemoTopology(selectedProjectId);
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
      <CreateProjectModal
        open={projectModalOpen}
        onClose={() => setProjectModalOpen(false)}
        onCreated={(p) => {
          writeSessionProjectId(p.id);
          void refresh(p.id);
        }}
      />

      <CreateBlankTopologyModal
        open={blankOpen}
        onClose={() => setBlankOpen(false)}
        projectId={selectedProjectId}
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

      <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[12rem] flex-1 text-sm font-medium text-zinc-800 dark:text-zinc-200">
            <span className="text-xs font-semibold uppercase tracking-wide text-cns-label">Project</span>
            <select
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={selectedProjectId ?? ''}
              onChange={(e) => {
                const id = e.target.value || null;
                setSelectedProjectId(id);
                writeSessionProjectId(id);
                void refresh(id);
              }}
              disabled={projects.length === 0}
            >
              {projects.length === 0 ? <option value="">No projects yet</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => setProjectModalOpen(true)}
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            New project
          </button>
        </div>
        {projects.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-amber-300/80 bg-amber-50/50 p-5 dark:border-amber-800/60 dark:bg-amber-950/20">
            <h3 className="text-sm font-semibold text-amber-950 dark:text-amber-100">No projects yet</h3>
            <p className="mt-2 text-sm leading-relaxed text-amber-950/90 dark:text-amber-100/90">
              Projects scope your topologies and deployments. Create a project to get started, or{' '}
              <Link to="/register" className="font-semibold text-amber-950 underline dark:text-amber-50">
                register
              </Link>{' '}
              if you do not have an account — registration creates a starter workspace and signs you in.
            </p>
            <button
              type="button"
              onClick={() => setProjectModalOpen(true)}
              className="mt-4 rounded-lg bg-amber-900 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 dark:bg-amber-700 dark:hover:bg-amber-600"
            >
              Create your first project
            </button>
          </div>
        ) : (
          <p className="mt-2 text-xs text-cns-muted">
            Topology list is scoped to the selected project. Switch projects to see other labs.
          </p>
        )}
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
        {metrics && metrics.total_deployments === 0 ? (
          <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50/80 px-4 py-3 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950/50 dark:text-zinc-300">
            <span className="font-semibold text-zinc-900 dark:text-zinc-100">No deployments yet</span> across your
            workspaces. Open a topology from the list below and use <strong className="font-semibold">Deploy to runtime</strong>{' '}
            when you are ready.
          </div>
        ) : null}
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
            disabled={!selectedProjectId}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            Create blank topology
          </button>
          <button
            type="button"
            onClick={() => void onCreateFromTemplate()}
            disabled={templateLoading || !selectedProjectId}
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
          <div className="p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-zinc-100 text-2xl dark:bg-zinc-800">
              ◇
            </div>
            <h3 className="mt-4 text-base font-semibold text-zinc-900 dark:text-zinc-50">No topologies in this project</h3>
            <p className="mx-auto mt-2 max-w-md text-sm text-cns-muted">
              Create a blank lab from scratch or start from a template. Topologies are saved graphs you can deploy to the
              Docker runtime.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <button
                type="button"
                onClick={() => setBlankOpen(true)}
                disabled={!selectedProjectId}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              >
                Create blank topology
              </button>
              <button
                type="button"
                onClick={() => void onCreateFromTemplate()}
                disabled={templateLoading || !selectedProjectId}
                className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
              >
                {templateLoading ? 'Creating…' : 'Create from template'}
              </button>
            </div>
          </div>
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
