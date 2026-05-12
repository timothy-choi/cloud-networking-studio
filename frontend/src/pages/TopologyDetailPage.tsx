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
import { CollapsibleSection } from '../components/ui/CollapsibleSection';
import { DeploymentLifecycleTimeline } from '../components/deployment/DeploymentLifecycleTimeline';
import { DeploymentPhaseStrip } from '../components/deployment/DeploymentPhaseStrip';
import { DeploymentEventStream } from '../components/events/DeploymentEventStream';
import { FailureHistory } from '../components/failures/FailureHistory';
import { RuntimeHealthBadges } from '../components/runtime/RuntimeHealthBadges';
import { RuntimeMetricsPanel } from '../components/runtime/RuntimeMetricsPanel';
import { Spinner } from '../components/Spinner';
import { TopologyWorkspace } from '../components/topology/TopologyWorkspace';
import { TrafficValidationSection } from '../components/traffic/TrafficValidationSection';
import { useDeploymentEvents } from '../hooks/useDeploymentEvents';
import { useFailures } from '../hooks/useFailures';
import { useTopologyRuntime } from '../hooks/useTopologyRuntime';
import { useTrafficTests } from '../hooks/useTrafficTests';
import { computeDeployReadiness } from '../lib/deployReadiness';
import { deriveControlPlanePhase } from '../lib/deploymentUiPhase';
import { formatLinkEdgeLabel } from '../lib/flowTopology';
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
  return status !== 'stopped';
}

function fmtClock(ts: number | null): string {
  if (ts == null) return '—';
  try {
    return new Date(ts).toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return '—';
  }
}

function fmtWhenIso(iso: string | null): string {
  if (!iso) return '—';
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
  const [pageToast, setPageToast] = useState<string | null>(null);

  const refreshLive = useCallback(async () => {
    await Promise.all([refetch(), refetchEvents(), refetchTraffic(), refetchFailures()]);
  }, [refetch, refetchEvents, refetchTraffic, refetchFailures]);

  const deploymentStatus = runtime?.deployment_status ?? null;
  const showDestroy = Boolean(deploymentId && deployAllowsDestroy(deploymentStatus));
  const degraded = hasStoppedContainers(runtime);
  const healthTier = deriveRuntimeHealth(runtime, topology?.status ?? 'draft');

  const deployReadiness = useMemo(() => computeDeployReadiness(nodes, links), [nodes, links]);

  const hostTarget = useMemo(() => {
    if (nodes.length < 2) return null;
    const host = nodes.find((n) => n.node_type === 'host');
    const svc = nodes.find((n) => n.node_type === 'generic');
    if (host && svc && host.id !== svc.id) return { source: host, target: svc };
    return { source: nodes[0], target: nodes[1] };
  }, [nodes]);

  const serviceNode = useMemo(() => {
    const byGeneric = nodes.find((n) => n.node_type === 'generic');
    if (byGeneric) return byGeneric;
    const byHost = nodes.find((n) => n.node_type === 'host');
    return nodes.find((n) => n.id !== byHost?.id) ?? nodes[0] ?? null;
  }, [nodes]);

  const nodeNameById = useMemo(() => new Map(nodes.map((n) => [n.id, n.name])), [nodes]);

  const latestEventAt = useMemo(() => {
    if (!events.length) return null;
    let maxIso = events[0].created_at;
    for (const e of events) {
      if (new Date(e.created_at) > new Date(maxIso)) maxIso = e.created_at;
    }
    return maxIso;
  }, [events]);

  const phaseInfo = useMemo(
    () => deriveControlPlanePhase(runtime, topology?.status ?? 'draft', busy, nodes.length),
    [runtime, topology?.status, busy, nodes.length],
  );

  async function wrap(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setOpsNote(null);
    setPageToast(null);
    try {
      await fn();
      await refreshLive();
      setPageToast(`${label.replace(/-/g, ' ')} completed`);
      window.setTimeout(() => setPageToast(null), 4200);
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
    <div className="space-y-5 pb-10 max-w-full min-w-0 overflow-x-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
            ← Dashboard
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              {topology?.name ?? 'Topology'}
            </h1>
            {degraded ? (
              <span className="rounded-full bg-red-600 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-white shadow-sm">
                Runtime degraded
              </span>
            ) : null}
            {loading && <Spinner className="h-5 w-5" />}
          </div>
          <p className="font-mono text-xs text-cns-muted">{id}</p>
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
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
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
      {pageToast && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          {pageToast}
        </div>
      )}

      {degraded && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-l-4 border-red-500 bg-gradient-to-r from-red-50 to-amber-50 px-4 py-3 text-sm text-red-950 shadow-sm dark:border-red-400 dark:from-red-950/50 dark:to-amber-950/30 dark:text-red-100"
        >
          <span>
            <strong className="font-semibold">Stopped containers detected.</strong> Reconcile to restore intent, then run{' '}
            <strong className="font-semibold">Heal deployment</strong> (highlighted below).
          </span>
        </div>
      )}

      {topology && (
        <RuntimeMetricsPanel
          runtime={runtime}
          lastRuntimePollAt={fmtClock(lastUpdatedAt)}
          lastEventsPollAt={fmtClock(eventsUpdatedAt)}
          latestEventAt={latestEventAt}
        />
      )}

      {topology && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-cns-label">Topology record</div>
            <div className="mt-1">
              <Badge>{topology.status}</Badge>
            </div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-cns-label">Runtime target</div>
            <div className="mt-1 text-sm font-medium">{topology.runtime_target}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-cns-label">Networking mode</div>
            <div className="mt-1 text-sm font-medium">{topology.networking_mode}</div>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="text-xs uppercase tracking-wide text-cns-label">Latest deployment</div>
            <div className="mt-1 truncate font-mono text-xs">
              {deploymentStatus ?? '—'}{' '}
              {deploymentId ? `· ${deploymentId.slice(0, 8)}…` : ''}
            </div>
          </div>
        </div>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Runtime actions</h2>
        <p className="mt-0.5 text-xs text-cns-muted">
          Runtime deployment, traffic checks, failure injection, and reconcile/heal for this lab. Live polling keeps data
          fresh.
        </p>
        {!deployReadiness.deployable ? (
          <p className="mt-2 rounded-md border border-amber-800/50 bg-amber-950/25 px-2 py-1.5 text-xs text-amber-100">
            <span className="font-semibold">Deploy unavailable:</span> {deployReadiness.blockingReasons.join(' ')}
          </p>
        ) : deployReadiness.warnings.length > 0 ? (
          <p className="mt-2 rounded-md border border-sky-900/40 bg-sky-950/20 px-2 py-1.5 text-xs text-sky-100">
            <span className="font-semibold">Before deploy:</span> {deployReadiness.warnings.join(' ')}
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== null || !deployReadiness.deployable}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !deployReadiness.deployable
                  ? deployReadiness.blockingReasons.join(' ')
                  : deployReadiness.warnings.length > 0
                    ? 'Deploy allowed — review warnings above.'
                    : undefined
            }
            onClick={() =>
              wrap('deploy', async () => {
                await deployTopology(id);
              })
            }
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 cns-disabled-control dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            Deploy to runtime
          </button>
          <button
            type="button"
            disabled={busy !== null}
            title={busy !== null ? 'Wait for the current action to finish.' : undefined}
            onClick={() => wrap('refresh', refreshLive)}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Refresh runtime
          </button>
          <button
            type="button"
            disabled={busy !== null || !hostTarget}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !hostTarget
                  ? 'Need at least two nodes with a link for traffic tests.'
                  : undefined
            }
            onClick={() =>
              wrap('ping', async () => {
                await runPingTest(id, {
                  source_node_id: hostTarget!.source.id,
                  target_node_id: hostTarget!.target.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Run ping test
          </button>
          <button
            type="button"
            disabled={busy !== null || !hostTarget}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !hostTarget
                  ? 'Need at least two nodes for HTTP source/target.'
                  : undefined
            }
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
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Run HTTP test
          </button>
          <button
            type="button"
            disabled={busy !== null || !serviceNode}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !serviceNode
                  ? 'Need a workload node to stop.'
                  : undefined
            }
            onClick={() =>
              wrap('stop', async () => {
                await injectStopNode(id, {
                  target_node_id: serviceNode!.id,
                  description: 'UI stop-node injection',
                });
              })
            }
            className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100 cns-disabled-control dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
          >
            Stop service node
          </button>
          <button
            type="button"
            disabled={busy !== null || !deploymentId}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !deploymentId
                  ? 'Deploy the topology first so there is an active deployment.'
                  : undefined
            }
            onClick={() =>
              wrap('reconcile', async () => {
                await reconcileDeployment(deploymentId!);
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Reconcile
          </button>
          <button
            type="button"
            disabled={busy !== null || !deploymentId}
            title={
              busy !== null
                ? 'Wait for the current action to finish.'
                : !deploymentId
                  ? 'Deploy the topology first — heal applies to the latest deployment.'
                  : degraded
                    ? 'Runs orchestrator heal — recommended when workloads are stopped.'
                    : undefined
            }
            onClick={() =>
              wrap('heal', async () => {
                await healDeployment(deploymentId!);
              })
            }
            className={`rounded-lg border px-4 py-2 text-sm font-semibold shadow-sm cns-disabled-control motion-safe:transition ${
              degraded
                ? 'motion-safe:animate-pulse border-amber-500 bg-amber-400 text-amber-950 ring-4 ring-amber-400/90 hover:bg-amber-300 dark:border-amber-400 dark:bg-amber-500 dark:text-zinc-950 dark:ring-amber-300/80 dark:hover:bg-amber-400'
                : 'border-emerald-600/40 bg-emerald-50 text-emerald-950 hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/60'
            }`}
          >
            Heal deployment
          </button>
          {showDestroy && deploymentId && (
            <button
              type="button"
              disabled={busy !== null}
              title={busy !== null ? 'Wait for the current action to finish.' : undefined}
              onClick={() =>
                wrap('destroy', async () => {
                  await destroyDeployment(deploymentId);
                })
              }
              className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100 cns-disabled-control dark:border-red-900 dark:bg-red-950/50 dark:text-red-200 dark:hover:bg-red-950/80"
            >
              Destroy deployment
            </button>
          )}
        </div>
        {busy && (
          <p className="mt-2 flex items-center gap-2 text-xs text-cns-muted">
            <Spinner className="h-4 w-4" /> Working: {busy}…
          </p>
        )}
      </section>

      <TrafficValidationSection tests={trafficTests} pollError={trafficPollErr} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12 xl:items-start xl:gap-6">
        <div className="min-w-0 space-y-3 xl:col-span-8">
          <div>
            <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Topology studio</h2>
            <p className="mt-0.5 text-xs text-cns-muted">
              Toolbar above the canvas · inspector beside the graph · edit, save, template, then deploy from Runtime actions.
            </p>
          </div>
          <TopologyWorkspace
            topologyId={id}
            topology={topology ?? null}
            nodes={nodes}
            links={links}
            runtime={runtime}
            controllerBusy={busy}
            globalBusy={busy !== null}
            onRefresh={refreshLive}
          />
        </div>

        <aside className="flex min-w-0 flex-col gap-4 xl:col-span-4">
          {topology ? (
            <>
              <DeploymentPhaseStrip
                phase={phaseInfo.phase}
                shortLabel={phaseInfo.shortLabel}
                description={phaseInfo.description}
              />
              <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-cns-label">Runtime summary</h3>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between gap-2">
                    <dt className="text-cns-muted">Health</dt>
                    <dd className="font-medium capitalize text-zinc-900 dark:text-zinc-100">{healthTier}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-cns-muted">Deployment</dt>
                    <dd className="truncate font-mono text-xs text-zinc-800 dark:text-zinc-200">
                      {deploymentStatus ?? '—'}
                      {deploymentId ? ` · ${deploymentId.slice(0, 8)}…` : ''}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-cns-muted">Latest event</dt>
                    <dd className="text-right font-mono text-[11px] text-zinc-700 dark:text-zinc-300">
                      {fmtWhenIso(latestEventAt)}
                    </dd>
                  </div>
                </dl>
                <a
                  href="#deployment-events"
                  className="mt-3 inline-block text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400"
                >
                  Full deployment event log ↓
                </a>
              </div>
              <DeploymentEventStream
                events={events}
                loading={busy !== null}
                hideInspectionByDefault
                variant="compact"
                listClassName="max-h-52 xl:max-h-64"
              />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-zinc-300 p-4 text-sm text-cns-muted dark:border-zinc-700">
              Load topology data to see control-plane phase and recent deployment events.
            </div>
          )}
        </aside>
      </div>

      <DeploymentLifecycleTimeline events={events} trafficTests={trafficTests} failures={failures} />

      <div className="grid gap-6 md:grid-cols-2 md:items-start">
        <div className="min-w-0 space-y-2">
          {failuresPollErr && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              Failures poll: {failuresPollErr}
            </div>
          )}
          <FailureHistory failures={failures} nodeNameById={nodeNameById} />
        </div>
        <div id="deployment-events" className="min-w-0 space-y-2">
          {eventsPollErr && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              Events poll: {eventsPollErr}
            </div>
          )}
          <DeploymentEventStream
            events={events}
            loading={busy !== null}
            hideInspectionByDefault
            listClassName="max-h-[min(420px,50vh)]"
          />
        </div>
      </div>

      <CollapsibleSection title="Runtime networks & interfaces" defaultOpen>
        {!runtime ? (
          <p className="text-xs text-cns-muted">No runtime snapshot yet.</p>
        ) : (
          <div className="space-y-4 text-xs text-zinc-800 dark:text-zinc-200">
            <div>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-cns-label">Networks</h4>
              <ul className="mt-2 space-y-2">
                {runtime.networks.map((n) => (
                  <li
                    key={n.network_id}
                    className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1.5 font-mono text-[11px] dark:border-zinc-700 dark:bg-zinc-950/60"
                  >
                    <div className="text-zinc-900 dark:text-zinc-100">{n.name}</div>
                    <div className="text-cns-muted">
                      {n.driver}
                      {n.subnet_hints?.length ? ` · ${n.subnet_hints.join(', ')}` : ''}
                    </div>
                  </li>
                ))}
                {runtime.networks.length === 0 ? (
                  <li className="text-cns-muted">No provider networks in this snapshot.</li>
                ) : null}
              </ul>
            </div>
            <div>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-cns-label">Containers</h4>
              <ul className="mt-2 space-y-3">
                {runtime.containers.map((c) => (
                  <li
                    key={c.container_id}
                    className="rounded-md border border-zinc-200 bg-white px-2 py-2 dark:border-zinc-700 dark:bg-zinc-900/80"
                  >
                    <div className="font-medium text-zinc-900 dark:text-zinc-100">{c.name}</div>
                    <div className="mt-1 font-mono text-[10px] text-cns-muted">
                      node {c.node_id ?? '—'} · {c.running ? 'running' : 'stopped'}
                    </div>
                    {c.network_interfaces && c.network_interfaces.length > 0 ? (
                      <table className="mt-2 w-full border-collapse text-left text-[10px]">
                        <thead>
                          <tr className="text-cns-muted">
                            <th className="py-0.5 pr-2 font-normal">IF</th>
                            <th className="py-0.5 pr-2 font-normal">Docker net</th>
                            <th className="py-0.5 pr-2 font-normal">IPv4</th>
                            <th className="py-0.5 font-normal">GW</th>
                          </tr>
                        </thead>
                        <tbody>
                          {c.network_interfaces.map((i) => (
                            <tr key={`${c.container_id}-${i.interface}-${i.docker_network}`}>
                              <td className="py-0.5 pr-2 font-mono text-emerald-700 dark:text-emerald-400">
                                {i.interface}
                              </td>
                              <td className="py-0.5 pr-2 font-mono text-zinc-700 dark:text-zinc-300">
                                {i.logical_network ?? i.docker_network}
                              </td>
                              <td className="py-0.5 pr-2 font-mono">{i.ipv4}</td>
                              <td className="py-0.5 font-mono text-cns-muted">{i.gateway ?? '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="mt-1 font-mono text-[10px] text-cns-muted">
                        {Object.keys(c.ipv4_by_network).length
                          ? Object.entries(c.ipv4_by_network)
                              .map(([k, v]) => `${k}: ${v}`)
                              .join(' · ')
                          : 'No IP bindings recorded.'}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Raw runtime JSON" defaultOpen={false}>
        <div className="max-h-[min(520px,70vh)] overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-4 font-mono text-[11px] leading-relaxed text-emerald-100/95">
          {runtime ? (
            <pre className="whitespace-pre-wrap break-all">{JSON.stringify(runtime, null, 2)}</pre>
          ) : (
            <span className="text-cns-muted">No runtime snapshot yet.</span>
          )}
        </div>
      </CollapsibleSection>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Nodes</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {nodes.map((n) => (
              <li key={n.id} className="flex justify-between gap-2 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                <span className="font-medium">{n.name}</span>
                <span className="font-mono text-xs text-cns-muted">{n.ip_address ?? '—'}</span>
              </li>
            ))}
            {nodes.length === 0 && <li className="text-cns-muted">No nodes</li>}
          </ul>
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Links</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {links.map((l) => (
              <li key={l.id} className="border-b border-zinc-100 pb-2 dark:border-zinc-800">
                <div className="whitespace-pre-line font-mono text-[11px] text-zinc-700 dark:text-zinc-300">
                  {formatLinkEdgeLabel(l)}
                </div>
              </li>
            ))}
            {links.length === 0 && <li className="text-cns-muted">No links</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
