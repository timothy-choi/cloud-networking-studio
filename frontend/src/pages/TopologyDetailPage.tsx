import { useMemo, useCallback, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { formatApiError } from '../api/client';
import {
  deployTopology,
  destroyDeployment,
  healDeployment,
  reconcileDeployment,
} from '../api/deployments';
import { injectStopNode, runHttpTest, runPingTest } from '../api/topologies';
import { DeploymentEventStream } from '../components/events/DeploymentEventStream';
import { FailureHistory } from '../components/failures/FailureHistory';
import { RuntimeHealthBadges } from '../components/runtime/RuntimeHealthBadges';
import { RuntimeMetricsPanel } from '../components/runtime/RuntimeMetricsPanel';
import { Spinner } from '../components/Spinner';
import { TopologyGraph } from '../components/TopologyGraph';
import { TrafficTestHistory } from '../components/traffic/TrafficTestHistory';
import { useDeploymentEvents } from '../hooks/useDeploymentEvents';
import { useFailures } from '../hooks/useFailures';
import { useTopologyRuntime } from '../hooks/useTopologyRuntime';
import { useTrafficTests } from '../hooks/useTrafficTests';
import { deriveRuntimeHealth, hasStoppedContainers } from '../lib/runtimeHealth';
import type { DeploymentStatus } from '../types/deployment';

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

function fmtClock(ts: number | null): string {
  if (ts == null) return '—';
  try {
    return new Date(ts).toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return '—';
  }
}

export function TopologyDetailPage() {
  const { topologyId } = useParams<{ topologyId: string }>();
  const id = topologyId ?? '';

  const {
    topology,
    nodes,
    links,
    runtime,
    loading,
    error,
    refetch,
    lastUpdatedAt,
  } = useTopologyRuntime(id || undefined);

  const deploymentId = runtime?.latest_deployment_id ?? null;

  const {
    events,
    refetch: refetchEvents,
    lastUpdatedAt: eventsUpdatedAt,
    error: eventsPollErr,
  } = useDeploymentEvents(deploymentId);

  const { trafficTests, refetch: refetchTraffic, error: trafficPollErr } = useTrafficTests(id || undefined);

  const { failures, refetch: refetchFailures, error: failuresPollErr } = useFailures(id || undefined);

  const [busy, setBusy] = useState<string | null>(null);
  const [opsNote, setOpsNote] = useState<string | null>(null);

  const refreshLive = useCallback(async () => {
    await Promise.all([refetch(), refetchEvents(), refetchTraffic(), refetchFailures()]);
  }, [refetch, refetchEvents, refetchTraffic, refetchFailures]);

  const deploymentStatus = runtime?.deployment_status ?? null;
  const showDestroy = Boolean(deploymentId && deployAllowsDestroy(deploymentStatus));
  const degraded = hasStoppedContainers(runtime);
  const healthTier = deriveRuntimeHealth(runtime, topology?.status ?? 'draft');

  const hostTarget = useMemo(() => {
    const host = nodes.find((n) => n.name === 'host-a');
    const svc = nodes.find((n) => n.name === 'service-b');
    if (host && svc) return { source: host, target: svc };
    if (nodes.length >= 2) return { source: nodes[0], target: nodes[1] };
    return null;
  }, [nodes]);

  const serviceNode = useMemo(
    () =>
      nodes.find((n) => n.name === 'service-b') ??
      nodes.find((n) => n.node_type === 'generic') ??
      nodes[1],
    [nodes],
  );

  const nodeNameById = useMemo(() => new Map(nodes.map((n) => [n.id, n.name])), [nodes]);

  async function wrap(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setOpsNote(null);
    try {
      await fn();
      await refreshLive();
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
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              {topology?.name ?? 'Topology'}
            </h1>
            {loading && <Spinner className="h-5 w-5" />}
          </div>
          <p className="font-mono text-xs text-zinc-500">{id}</p>
          {topology && (
            <div className="mt-3">
              <RuntimeHealthBadges
                topologyStatus={topology.status}
                deploymentStatus={deploymentStatus}
                runtimeTier={healthTier}
                pollLive
              />
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void refreshLive()}
            disabled={busy !== null}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            {busy ? <Spinner className="h-4 w-4" /> : null}
            Refresh now
          </button>
        </div>
      </div>

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <span>{error}</span>
          <button
            type="button"
            className="rounded-md bg-red-100 px-3 py-1 text-xs font-semibold text-red-900 hover:bg-red-200 dark:bg-red-950 dark:text-red-200 dark:hover:bg-red-900"
            onClick={() => void refreshLive()}
          >
            Retry
          </button>
        </div>
      )}
      {opsNote && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {opsNote}
        </div>
      )}

      {degraded && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/60 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100">
          <span>
            <strong>Degraded:</strong> one or more containers are stopped. Run reconcile, then heal.
          </span>
        </div>
      )}

      {topology && (
        <RuntimeMetricsPanel
          runtime={runtime}
          deploymentUpdatedHint={fmtClock(lastUpdatedAt)}
          eventsUpdatedHint={fmtClock(eventsUpdatedAt)}
        />
      )}

      {topology && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Topology record</div>
            <div className="mt-1">
              <Badge>{topology.status}</Badge>
            </div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Runtime target</div>
            <div className="mt-1 text-sm font-medium">{topology.runtime_target}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Networking mode</div>
            <div className="mt-1 text-sm font-medium">{topology.networking_mode}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Latest deployment</div>
            <div className="mt-1 truncate font-mono text-xs">
              {deploymentStatus ?? '—'}{' '}
              {deploymentId ? `· ${deploymentId.slice(0, 8)}…` : ''}
            </div>
          </div>
        </div>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Runtime controls</h2>
        <p className="mt-0.5 text-xs text-zinc-500">
          Live polling keeps runtime, events, traffic, and failures fresh every few seconds.
        </p>
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
            onClick={() => wrap('refresh', refreshLive)}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Refresh runtime
          </button>
          <button
            type="button"
            disabled={busy !== null || !hostTarget}
            onClick={() =>
              wrap('ping', async () => {
                await runPingTest(id, {
                  source_node_id: hostTarget!.source.id,
                  target_node_id: hostTarget!.target.id,
                  count: 3,
                });
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
                await runHttpTest(id, {
                  source_node_id: hostTarget!.source.id,
                  target_node_id: hostTarget!.target.id,
                  path: '/',
                  port: 80,
                });
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
            className={`rounded-lg border px-4 py-2 text-sm font-semibold shadow-sm disabled:opacity-50 ${
              degraded
                ? 'border-amber-500 bg-amber-400 text-amber-950 ring-2 ring-amber-400/80 hover:bg-amber-300 dark:border-amber-400 dark:bg-amber-500 dark:text-zinc-950 dark:hover:bg-amber-400'
                : 'border-emerald-600/40 bg-emerald-50 text-emerald-950 hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/60'
            }`}
          >
            Heal deployment
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
        {busy && (
          <p className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
            <Spinner className="h-4 w-4" /> Working: {busy}…
          </p>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Workload graph</h2>
          <TopologyGraph nodes={nodes} links={links} runtime={runtime} />
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Runtime snapshot (JSON)</h2>
          <div className="max-h-[460px] overflow-auto rounded-xl border border-zinc-200 bg-zinc-950 p-4 font-mono text-[11px] leading-relaxed text-emerald-100/95 dark:border-zinc-700">
            {runtime ? (
              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(runtime, null, 2)}</pre>
            ) : (
              <span className="text-zinc-500">No runtime snapshot yet.</span>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-2">
          {eventsPollErr && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              Events poll: {eventsPollErr}
            </div>
          )}
          <DeploymentEventStream events={events} loading={busy !== null} />
        </div>
        <div className="space-y-2">
          {trafficPollErr && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              Traffic poll: {trafficPollErr}
            </div>
          )}
          <TrafficTestHistory tests={trafficTests} />
        </div>
      </div>

      <div className="space-y-2">
        {failuresPollErr && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            Failures poll: {failuresPollErr}
          </div>
        )}
        <FailureHistory failures={failures} nodeNameById={nodeNameById} />
      </div>

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
