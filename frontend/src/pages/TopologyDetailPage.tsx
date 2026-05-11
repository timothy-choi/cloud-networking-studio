import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { formatApiError } from '../api/client';
import {
  deployTopology,
  destroyDeployment,
  healDeployment,
  listDeploymentEvents,
  reconcileDeployment,
} from '../api/deployments';
import {
  getTopology,
  getTopologyRuntime,
  injectStopNode,
  listLinks,
  listNodes,
  runHttpTest,
  runPingTest,
} from '../api/topologies';
import { TopologyGraph } from '../components/TopologyGraph';
import type {
  DeploymentEventResponse,
  DeploymentStatus,
  RuntimeTopologyResponse,
  TopologyLinkResponse,
  TopologyNodeResponse,
  TopologyResponse,
  TrafficTestResponse,
} from '../types/api';

function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
      {children}
    </span>
  );
}

function deployAllowsDestroy(status: DeploymentStatus | null): boolean {
  if (!status) return false;
  return status !== 'stopped' && status !== 'cancelled';
}

export function TopologyDetailPage() {
  const { topologyId } = useParams<{ topologyId: string }>();
  const id = topologyId ?? '';

  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [nodes, setNodes] = useState<TopologyNodeResponse[]>([]);
  const [links, setLinks] = useState<TopologyLinkResponse[]>([]);
  const [runtime, setRuntime] = useState<RuntimeTopologyResponse | null>(null);
  const [events, setEvents] = useState<DeploymentEventResponse[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [opsNote, setOpsNote] = useState<string | null>(null);
  const [lastTraffic, setLastTraffic] = useState<TrafficTestResponse | null>(null);

  const refreshAll = useCallback(async () => {
    if (!id) return;
    setLoadErr(null);
    try {
      const [topo, ns, ls, rt] = await Promise.all([
        getTopology(id),
        listNodes(id),
        listLinks(id),
        getTopologyRuntime(id),
      ]);
      setTopology(topo);
      setNodes(ns);
      setLinks(ls);
      setRuntime(rt);

      if (rt.latest_deployment_id) {
        try {
          const ev = await listDeploymentEvents(rt.latest_deployment_id);
          setEvents(ev);
        } catch {
          setEvents([]);
        }
      } else {
        setEvents([]);
      }
    } catch (e) {
      setLoadErr(formatApiError(e));
    }
  }, [id]);

  useEffect(() => {
    queueMicrotask(() => {
      void refreshAll();
    });
  }, [refreshAll]);

  const deploymentId = runtime?.latest_deployment_id ?? null;
  const deploymentStatus = runtime?.deployment_status ?? null;
  const showDestroy = Boolean(deploymentId && deployAllowsDestroy(deploymentStatus));

  const hostTarget = useMemo(() => {
    const host = nodes.find((n) => n.name === 'host-a');
    const svc = nodes.find((n) => n.name === 'service-b');
    if (host && svc) return { source: host, target: svc };
    if (nodes.length >= 2) return { source: nodes[0], target: nodes[1] };
    return null;
  }, [nodes]);

  const serviceNode = useMemo(
    () => nodes.find((n) => n.name === 'service-b') ?? nodes.find((n) => n.node_type === 'generic') ?? nodes[1],
    [nodes],
  );

  async function wrap(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setOpsNote(null);
    try {
      await fn();
      await refreshAll();
    } catch (e) {
      setOpsNote(formatApiError(e));
    } finally {
      setBusy(null);
    }
  }

  if (!id) {
    return <p className="text-sm text-red-600">Missing topology id.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
            ← Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            {topology?.name ?? 'Topology'}
          </h1>
          <p className="font-mono text-xs text-zinc-500">{id}</p>
        </div>
        <button
          type="button"
          onClick={() => void refreshAll()}
          disabled={busy !== null}
          className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          Refresh data
        </button>
      </div>

      {loadErr && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {loadErr}
        </div>
      )}
      {opsNote && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {opsNote}
        </div>
      )}

      {topology && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Status</div>
            <div className="mt-1">
              <Badge>{topology.status}</Badge>
            </div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Runtime target</div>
            <div className="mt-1 text-sm font-medium">{topology.runtime_target}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Networking</div>
            <div className="mt-1 text-sm font-medium">{topology.networking_mode}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Deployment</div>
            <div className="mt-1 truncate font-mono text-xs">
              {deploymentStatus ?? '—'} {deploymentId ? `· ${deploymentId.slice(0, 8)}…` : ''}
            </div>
          </div>
        </div>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Runtime controls</h2>
        <p className="mt-0.5 text-xs text-zinc-500">Uses live backend endpoints · Docker must be available for full effect.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              wrap('deploy', async () => {
                await deployTopology(id);
              })
            }
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            Deploy topology
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => wrap('runtime', refreshAll)}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Refresh runtime
          </button>
          <button
            type="button"
            disabled={busy !== null || !hostTarget}
            onClick={() =>
              wrap('ping', async () => {
                const r = await runPingTest(id, {
                  source_node_id: hostTarget!.source.id,
                  target_node_id: hostTarget!.target.id,
                  count: 3,
                });
                setLastTraffic(r);
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Run ping test
          </button>
          <button
            type="button"
            disabled={busy !== null || !hostTarget}
            onClick={() =>
              wrap('http', async () => {
                const r = await runHttpTest(id, {
                  source_node_id: hostTarget!.source.id,
                  target_node_id: hostTarget!.target.id,
                  path: '/',
                  port: 80,
                });
                setLastTraffic(r);
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Run HTTP test
          </button>
          <button
            type="button"
            disabled={busy !== null || !serviceNode}
            onClick={() =>
              wrap('stop', async () => {
                await injectStopNode(id, {
                  target_node_id: serviceNode!.id,
                  description: 'UI stop-node injection',
                });
              })
            }
            className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
          >
            Stop service node
          </button>
          <button
            type="button"
            disabled={busy !== null || !deploymentId}
            onClick={() =>
              wrap('reconcile', async () => {
                await reconcileDeployment(deploymentId!);
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Reconcile
          </button>
          <button
            type="button"
            disabled={busy !== null || !deploymentId}
            onClick={() =>
              wrap('heal', async () => {
                await healDeployment(deploymentId!);
              })
            }
            className="rounded-lg border border-emerald-600/40 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/60"
          >
            Heal
          </button>
          {showDestroy && deploymentId && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                wrap('destroy', async () => {
                  await destroyDeployment(deploymentId);
                })
              }
              className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100 disabled:opacity-50 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200 dark:hover:bg-red-950/80"
            >
              Destroy deployment
            </button>
          )}
        </div>
        {busy && <p className="mt-2 text-xs text-zinc-500">Working: {busy}…</p>}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Topology graph</h2>
          <TopologyGraph nodes={nodes} links={links} />
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Runtime state</h2>
          <div className="max-h-[440px] overflow-auto rounded-xl border border-zinc-200 bg-zinc-950 p-4 font-mono text-[11px] leading-relaxed text-emerald-100/95 dark:border-zinc-700">
            {runtime ? (
              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(runtime, null, 2)}</pre>
            ) : (
              <span className="text-zinc-500">No runtime snapshot yet.</span>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Deployment events</h2>
          <p className="text-xs text-zinc-500">
            {deploymentId ? `Deployment ${deploymentId}` : 'Deploy to append events'}
          </p>
        </div>
        <div className="max-h-72 overflow-auto">
          {events.length === 0 ? (
            <p className="p-4 text-sm text-zinc-500">No events loaded.</p>
          ) : (
            <ul className="divide-y divide-zinc-100 font-mono text-xs dark:divide-zinc-800">
              {events.map((ev) => (
                <li key={ev.id} className="flex gap-3 px-4 py-2">
                  <span
                    className={`shrink-0 uppercase ${
                      ev.level === 'error'
                        ? 'text-red-600 dark:text-red-400'
                        : ev.level === 'warning'
                          ? 'text-amber-700 dark:text-amber-400'
                          : 'text-zinc-500'
                    }`}
                  >
                    {ev.level}
                  </span>
                  <span className="text-zinc-600 dark:text-zinc-300">{ev.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Last traffic test</h2>
        </div>
        <div className="max-h-60 overflow-auto p-4 font-mono text-[11px] text-zinc-700 dark:text-zinc-300">
          {lastTraffic ? (
            <pre className="whitespace-pre-wrap break-all">{JSON.stringify(lastTraffic, null, 2)}</pre>
          ) : (
            <span className="text-sm text-zinc-500">Run ping or HTTP test to see results.</span>
          )}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Nodes</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {nodes.map((n) => (
              <li key={n.id} className="flex justify-between gap-2 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                <span className="font-medium">{n.name}</span>
                <span className="font-mono text-xs text-zinc-500">{n.ip_address ?? '—'}</span>
              </li>
            ))}
            {nodes.length === 0 && <li className="text-zinc-500">No nodes</li>}
          </ul>
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Links</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {links.map((l) => (
              <li key={l.id} className="border-b border-zinc-100 pb-2 dark:border-zinc-800">
                <div className="font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                  {l.network_name} {l.cidr ? `· ${l.cidr}` : ''}
                </div>
              </li>
            ))}
            {links.length === 0 && <li className="text-zinc-500">No links</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
