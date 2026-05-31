import { useMemo, useCallback, useState, useEffect, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  deployTopology,
  destroyDeployment,
  healDeployment,
  reconcileDeployment,
} from '../api/deployments';
import {
  injectStopNode,
  injectRestartNode,
  runHttpTest,
  runPingTest,
  deleteTopology,
  patchTopology,
} from '../api/topologies';
import { CollapsibleSection } from '../components/ui/CollapsibleSection';
import { SectionEmptyState } from '../components/SectionEmptyState';
import { DeploymentLifecycleTimeline } from '../components/deployment/DeploymentLifecycleTimeline';
import { DeploymentOperationTimeline } from '../components/deployment/DeploymentOperationTimeline';
import { DeploymentCleanupPanel } from '../components/deployment/DeploymentCleanupPanel';
import { DeploymentMetricsPanel } from '../components/metrics/DeploymentMetricsPanel';
import { ApiErrorDisplay } from '../components/errors/ApiErrorDisplay';
import { DeploymentPhaseStrip } from '../components/deployment/DeploymentPhaseStrip';
import { DeploymentProgressRail } from '../components/deployment/DeploymentProgressRail';
import { DeploymentRecentEventsPanel } from '../components/deployment/DeploymentRecentEventsPanel';
import { DeploymentEventStream } from '../components/events/DeploymentEventStream';
import { FailureHistory } from '../components/failures/FailureHistory';
import { RuntimeHealthBadges } from '../components/runtime/RuntimeHealthBadges';
import { RuntimeMetricsPanel } from '../components/runtime/RuntimeMetricsPanel';
import { RuntimeAccessPanel } from '../components/runtime/RuntimeAccessPanel';
import { SaveAsTemplateModal } from '../components/templates/SaveAsTemplateModal';
import { Spinner } from '../components/Spinner';
import { TopologyWorkspace } from '../components/topology/TopologyWorkspace';
import { TopologyVersionsPanel } from '../components/topology/TopologyVersionsPanel';
import { DeploymentProfilesPanel } from '../components/topology/DeploymentProfilesPanel';
import { ExternalDeploymentsPanel } from '../components/topology/ExternalDeploymentsPanel';
import { InfrastructureDeploymentsPanel } from '../components/topology/InfrastructureDeploymentsPanel';
import { DeployModal } from '../components/topology/DeployModal';
import { IaCExportPanel } from '../components/topology/IaCExportPanel';
import { TrafficValidationSection } from '../components/traffic/TrafficValidationSection';
import { useDeploymentEvents } from '../hooks/useDeploymentEvents';
import { useFailures } from '../hooks/useFailures';
import { useTopologyRuntime } from '../hooks/useTopologyRuntime';
import { useTrafficTests } from '../hooks/useTrafficTests';
import { computeDeployReadiness } from '../lib/deployReadiness';
import {
  NETWORK_ALLOCATION_HELP,
  readNetworkAllocationMode,
  type NetworkAllocationMode,
} from '../lib/networkAllocation';
import { deriveControlPlanePhase } from '../lib/deploymentUiPhase';
import { formatLinkEdgeLabel } from '../lib/flowTopology';
import { inferRoutedLabRoles, latestTrafficBetweenSorted, scanDeploymentEventsForRoutedIssues } from '../lib/routedTopology';
import { deriveRuntimeHealth, deploymentRuntimeActive, hasStoppedContainers } from '../lib/runtimeHealth';
import { formatOperatorError, type OperatorErrorPresentation } from '../lib/operatorHints';
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
  const navigate = useNavigate();
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
  const runtimeActive = deploymentRuntimeActive(runtime);
  const activeDeploymentId = runtimeActive ? deploymentId : null;

  const {
    events,
    refetch: refetchEvents,
    lastUpdatedAt: eventsUpdatedAt,
    error: eventsPollErr,
  } = useDeploymentEvents(deploymentId);

  const { trafficTests, refetch: refetchTraffic, error: trafficPollErr } = useTrafficTests(id || undefined);

  const { failures, refetch: refetchFailures, error: failuresPollErr } = useFailures(id || undefined);

  const [busy, setBusy] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<OperatorErrorPresentation | null>(null);
  const [pageToast, setPageToast] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [networkAllocationMode, setNetworkAllocationMode] =
    useState<NetworkAllocationMode>('managed');
  const [allocationModeSaving, setAllocationModeSaving] = useState(false);
  const [externalDeploymentsOpen, setExternalDeploymentsOpen] = useState(false);
  const [externalTargetSelection, setExternalTargetSelection] = useState<{
    targetId: string;
    highlight: boolean;
    fromInfra: boolean;
    tab: 'targets' | 'jobs' | 'deployments';
  } | null>(null);
  const [targetsRefreshToken, setTargetsRefreshToken] = useState(0);

  useEffect(() => {
    if (topology) {
      setNetworkAllocationMode(readNetworkAllocationMode(topology.config));
    }
  }, [topology?.id, topology?.config]);

  const refreshLive = useCallback(async () => {
    await Promise.all([refetch(), refetchEvents(), refetchTraffic(), refetchFailures()]);
  }, [refetch, refetchEvents, refetchTraffic, refetchFailures]);

  const deploymentStatus = runtime?.deployment_status ?? null;
  const viewerMode = topology?.my_role === 'viewer';
  const isOwner = topology?.my_role === 'owner';
  const viewerHint =
    'View-only access: ask a project owner or member to deploy, edit, or delete resources.';
  const opLocked = busy !== null || viewerMode;
  const showDestroy = Boolean(activeDeploymentId && deployAllowsDestroy(deploymentStatus));
  const showCleanedUpBanner =
    Boolean(deploymentId) &&
    !runtimeActive &&
    (runtime?.status === 'destroyed' || deploymentStatus === 'stopped');
  const noActiveDeploymentHint = runtimeActive ? null : 'No active deployment.';
  const degraded = hasStoppedContainers(runtime);
  const healthTier = deriveRuntimeHealth(runtime, topology?.status ?? 'draft');

  const deployReadiness = useMemo(
    () => computeDeployReadiness(nodes, links, networkAllocationMode),
    [nodes, links, networkAllocationMode],
  );

  const onNetworkAllocationModeChange = useCallback(
    async (mode: NetworkAllocationMode) => {
      if (!id || viewerMode) return;
      setNetworkAllocationMode(mode);
      setAllocationModeSaving(true);
      try {
        await patchTopology(id, { config: { network_allocation_mode: mode } });
        await refetch();
      } catch (e) {
        setOpsError(formatOperatorError(e));
      } finally {
        setAllocationModeSaving(false);
      }
    },
    [id, viewerMode, refetch],
  );

  const hostTarget = useMemo(() => {
    if (nodes.length < 2) return null;
    const host = nodes.find((n) => n.node_type === 'host');
    const svc = nodes.find((n) => n.node_type === 'generic');
    if (host && svc && host.id !== svc.id) return { source: host, target: svc };
    return { source: nodes[0], target: nodes[1] };
  }, [nodes]);

  const routedRoles = useMemo(() => inferRoutedLabRoles(nodes, links), [nodes, links]);

  const trafficPickerDefaults = useMemo(() => {
    if (routedRoles.host && routedRoles.service) {
      return { src: routedRoles.host.id, tgt: routedRoles.service.id };
    }
    if (hostTarget) return { src: hostTarget.source.id, tgt: hostTarget.target.id };
    return { src: nodes[0]?.id ?? '', tgt: nodes[1]?.id ?? '' };
  }, [routedRoles.host, routedRoles.service, hostTarget, nodes]);

  const [trafficSrc, setTrafficSrc] = useState('');
  const [trafficTgt, setTrafficTgt] = useState('');

  useEffect(() => {
    setTrafficSrc(trafficPickerDefaults.src);
    setTrafficTgt(trafficPickerDefaults.tgt);
  }, [id, trafficPickerDefaults.src, trafficPickerDefaults.tgt]);

  const routedIssues = useMemo(
    () => scanDeploymentEventsForRoutedIssues(events.map((e) => e.message)),
    [events],
  );

  const latestRoutedPing = useMemo(() => {
    if (!routedRoles.host || !routedRoles.service) return null;
    return latestTrafficBetweenSorted(
      trafficTests,
      routedRoles.host.id,
      routedRoles.service.id,
      'ping',
    );
  }, [trafficTests, routedRoles.host, routedRoles.service]);

  const latestRoutedHttp = useMemo(() => {
    if (!routedRoles.host || !routedRoles.service) return null;
    return latestTrafficBetweenSorted(
      trafficTests,
      routedRoles.host.id,
      routedRoles.service.id,
      'http',
    );
  }, [trafficTests, routedRoles.host, routedRoles.service]);

  const routedConnectivityVerified =
    routedRoles.isRoutedLike &&
    latestRoutedPing?.status === 'succeeded' &&
    Boolean(latestRoutedPing?.result?.success) &&
    latestRoutedHttp?.status === 'succeeded' &&
    Boolean(latestRoutedHttp?.result?.success);

  const canDirectedTraffic = Boolean(trafficSrc && trafficTgt && trafficSrc !== trafficTgt);

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

  const latestSeverity = useMemo(() => {
    const sorted = [...events].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    const hit = sorted.find((e) => e.level === 'error' || e.level === 'warning');
    if (!hit) return null;
    return { level: hit.level, message: hit.message, created_at: hit.created_at };
  }, [events]);

  const phaseInfo = useMemo(
    () => deriveControlPlanePhase(runtime, topology?.status ?? 'draft', busy, nodes.length),
    [runtime, topology?.status, busy, nodes.length],
  );

  async function wrap(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setOpsError(null);
    setPageToast(null);
    try {
      await fn();
      await refreshLive();
      setPageToast(`${label.replace(/-/g, ' ')} completed`);
      window.setTimeout(() => setPageToast(null), 4200);
    } catch (e) {
      setOpsError(formatOperatorError(e));
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
          <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
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
          {topology ? (
            <p className="mt-1 text-[11px] text-cns-muted">
              Graph: {nodes.length} nodes · {links.length} links · record updated {fmtWhenIso(topology.updated_at)}
              {lastUpdatedAt != null ? ` · polled ${fmtClock(lastUpdatedAt)}` : null}
            </p>
          ) : null}
          {topology && (
            <div className="mt-3">
              <RuntimeHealthBadges
                topologyStatus={topology.status}
                deploymentStatus={runtimeActive ? deploymentStatus : 'stopped'}
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
          <button
            type="button"
            disabled={opLocked}
            title={viewerMode ? viewerHint : undefined}
            onClick={() => setTemplateModalOpen(true)}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Save as template
          </button>
          <button
            type="button"
            disabled={opLocked || deleteBusy}
            title={viewerMode ? viewerHint : undefined}
            onClick={() => {
              if (
                !window.confirm(
                  'Delete this topology and all nodes, links, and deployment records? This cannot be undone.',
                )
              ) {
                return;
              }
              void (async () => {
                setDeleteBusy(true);
                setOpsError(null);
                try {
                  await deleteTopology(id);
                  navigate('/dashboard');
                } catch (e) {
                  setOpsError(formatOperatorError(e));
                } finally {
                  setDeleteBusy(false);
                }
              })();
            }}
            className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:bg-zinc-900 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            {deleteBusy ? 'Deleting…' : 'Delete topology'}
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
      {opsError && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <div className="font-semibold text-amber-950 dark:text-amber-50">Operation failed</div>
          <p className="mt-1 whitespace-pre-wrap break-words">{opsError.headline}</p>
          {opsError.suggestion ? (
            <p className="mt-2 text-sm">
              <span className="font-semibold">Suggested next step:</span> {opsError.suggestion}
            </p>
          ) : null}
          <CollapsibleSection title="Raw error details" defaultOpen={false}>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/80 p-2 font-mono text-[11px] text-zinc-100">
              {opsError.raw}
            </pre>
          </CollapsibleSection>
        </div>
      )}
      {pageToast && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          {pageToast}
        </div>
      )}

      {templateModalOpen ? (
        <SaveAsTemplateModal
          topologyId={id}
          defaultName={topology?.name ?? 'Topology'}
          onClose={() => setTemplateModalOpen(false)}
          onCreated={() => {
            setPageToast('Template saved. You can reuse it from the Templates library.');
            window.setTimeout(() => setPageToast(null), 4200);
          }}
        />
      ) : null}

      <DeployModal
        open={deployModalOpen}
        onClose={() => setDeployModalOpen(false)}
        topologyId={id}
        runtimeTarget={topology?.runtime_target ?? 'docker'}
        deployWarnings={deployReadiness.warnings}
        blockingReasons={deployReadiness.blockingReasons}
        networkAllocationMode={networkAllocationMode}
        onNetworkAllocationModeChange={setNetworkAllocationMode}
        onDeploy={async (opts) => {
          await wrap('deploy', async () => {
            await deployTopology(id, opts);
          });
        }}
      />

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

      {showCleanedUpBanner ? (
        <div
          role="alert"
          className="rounded-lg border border-zinc-400/60 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900/50 dark:text-zinc-100"
        >
          <strong className="font-semibold">Deployment was cleaned up/destroyed.</strong>{' '}
          {runtime?.message ?? 'Redeploy to create runtime resources again.'}
        </div>
      ) : null}

      {runtime?.topology_sync_status === 'out_of_sync' && runtimeActive && deploymentId ? (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/60 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/35 dark:text-amber-100"
        >
          <strong className="font-semibold">Out of sync with current topology.</strong> This deployment was created from
          an older topology config. Destroy and redeploy, or roll back with destroy/redeploy to align runtime.
        </div>
      ) : null}

      {topology && (
        <div className="grid gap-4 lg:grid-cols-2">
          <DeploymentProgressRail deploymentId={deploymentId} status={deploymentStatus} />
          <DeploymentRecentEventsPanel events={events} pollErr={eventsPollErr} />
        </div>
      )}

      {topology && (
        <RuntimeMetricsPanel
          runtime={runtime}
          lastRuntimePollAt={fmtClock(lastUpdatedAt)}
          lastEventsPollAt={fmtClock(eventsUpdatedAt)}
          latestEventAt={latestEventAt}
          deploymentStatus={deploymentStatus}
          latestSeverity={latestSeverity}
        />
      )}

      {topology && (
        <CollapsibleSection title="IaC Export" defaultOpen>
          <IaCExportPanel topologyId={id} />
        </CollapsibleSection>
      )}

      {topology && (
        <CollapsibleSection title="Versions" defaultOpen={false}>
          <TopologyVersionsPanel
            topologyId={id}
            readOnly={viewerMode}
            isOwner={isOwner}
            onRollback={() => void refreshLive()}
          />
        </CollapsibleSection>
      )}

      {topology && (
        <CollapsibleSection title="Deployment profiles" defaultOpen={false}>
          <DeploymentProfilesPanel topologyId={id} readOnly={viewerMode} isOwner={isOwner} />
        </CollapsibleSection>
      )}

      {topology?.project_id ? (
        <CollapsibleSection title="Infrastructure Deployments" defaultOpen={false}>
          <InfrastructureDeploymentsPanel
            topologyId={id}
            projectId={topology.project_id}
            onUseRuntimeTarget={(targetId) => {
              setExternalDeploymentsOpen(true);
              setExternalTargetSelection({
                targetId,
                highlight: true,
                fromInfra: true,
                tab: 'targets',
              });
              setTargetsRefreshToken((current) => current + 1);
              window.requestAnimationFrame(() => {
                document.getElementById('external-deployments')?.scrollIntoView({ behavior: 'smooth' });
              });
            }}
            onRuntimeTargetsChanged={() => setTargetsRefreshToken((current) => current + 1)}
          />
        </CollapsibleSection>
      ) : null}

      {topology?.project_id ? (
        <CollapsibleSection
          title="External Deployments"
          defaultOpen={false}
          id="external-deployments"
          open={externalDeploymentsOpen}
          onOpenChange={setExternalDeploymentsOpen}
        >
          <ExternalDeploymentsPanel
            topologyId={id}
            projectId={topology.project_id}
            readOnly={viewerMode}
            preferredTab={externalTargetSelection?.tab ?? null}
            preselectedTargetId={externalTargetSelection?.targetId ?? null}
            highlightTargetId={
              externalTargetSelection?.highlight ? externalTargetSelection.targetId : null
            }
            selectedFromInfra={externalTargetSelection?.fromInfra ?? false}
            onSelectedFromInfraAck={() =>
              setExternalTargetSelection((current) =>
                current ? { ...current, fromInfra: false } : null,
              )
            }
            onHighlightDone={() =>
              setExternalTargetSelection((current) =>
                current ? { ...current, highlight: false } : null,
              )
            }
            refreshToken={targetsRefreshToken}
          />
        </CollapsibleSection>
      ) : null}

      {topology && !deploymentId ? (
        <SectionEmptyState
          title="No active deployment yet"
          description="Runtime Access, exposure controls, and in-network operations require a deployment record. Use Runtime actions below to deploy this topology to Docker or Kubernetes."
          secondaryHint={
            <Link to="#runtime-actions" className="font-semibold text-emerald-800 underline dark:text-emerald-400">
              Jump to Runtime actions
            </Link>
          }
        />
      ) : null}

      {topology && activeDeploymentId ? (
        <RuntimeAccessPanel deploymentId={activeDeploymentId} viewerMode={viewerMode} />
      ) : topology && deploymentId && !runtimeActive ? (
        <SectionEmptyState
          title="No active deployment"
          description="Runtime resources were cleaned up or destroyed. Deploy again to access endpoints, logs, and traffic tests."
        />
      ) : null}

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

      <section
        id="runtime-actions"
        className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80"
      >
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Runtime actions</h2>
        <p
          className="mt-0.5 text-xs text-cns-muted"
          title="Deploy applies the graph to the provider. Logs, health checks, traffic tests, and safe exec run against the active deployment. Reconcile and heal fix drift and unhealthy workloads."
        >
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
        <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40">
          <label className="text-xs font-semibold uppercase tracking-wide text-cns-label">
            Network allocation
          </label>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
            <select
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              value={networkAllocationMode}
              disabled={opLocked || allocationModeSaving}
              onChange={(e) =>
                void onNetworkAllocationModeChange(e.target.value as NetworkAllocationMode)
              }
            >
              <option value="managed">Managed networking (recommended)</option>
              <option value="intent">Intent networking (advanced)</option>
            </select>
            {allocationModeSaving ? <Spinner className="h-5 w-5" /> : null}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-cns-muted">
            {NETWORK_ALLOCATION_HELP[networkAllocationMode]}
          </p>
          {topology?.runtime_target === 'kubernetes' && networkAllocationMode === 'intent' ? (
            <p className="mt-2 text-xs font-medium text-amber-800 dark:text-amber-200">
              Intent IP preservation is currently supported for Docker runtime only.
            </p>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={opLocked || !deployReadiness.deployable}
            title={
              viewerMode
                ? viewerHint
                : busy !== null
                  ? 'Wait for the current action to finish.'
                  : !deployReadiness.deployable
                    ? deployReadiness.blockingReasons.join(' ')
                    : deployReadiness.warnings.length > 0
                      ? 'Deploy allowed — review warnings above.'
                      : undefined
            }
            onClick={() => setDeployModalOpen(true)}
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
            disabled={opLocked || !runtimeActive || !hostTarget}
            title={
              viewerMode
                ? viewerHint
                : !runtimeActive
                  ? noActiveDeploymentHint ?? undefined
                : busy !== null
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
            disabled={opLocked || !runtimeActive || !hostTarget}
            title={
              viewerMode
                ? viewerHint
                : !runtimeActive
                  ? noActiveDeploymentHint ?? undefined
                : busy !== null
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
            disabled={opLocked || !runtimeActive || !serviceNode}
            title={
              viewerMode
                ? viewerHint
                : !runtimeActive
                  ? noActiveDeploymentHint ?? undefined
                : busy !== null
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
            disabled={opLocked || !activeDeploymentId}
            title={
              viewerMode
                ? viewerHint
                : busy !== null
                  ? 'Wait for the current action to finish.'
                  : !activeDeploymentId
                    ? noActiveDeploymentHint ?? 'Deploy the topology first so there is an active deployment.'
                    : undefined
            }
            onClick={() =>
              wrap('reconcile', async () => {
                await reconcileDeployment(activeDeploymentId!);
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Reconcile
          </button>
          <button
            type="button"
            disabled={opLocked || !activeDeploymentId}
            title={
              viewerMode
                ? viewerHint
                : busy !== null
                  ? 'Wait for the current action to finish.'
                  : !activeDeploymentId
                    ? noActiveDeploymentHint ?? 'Deploy the topology first — heal applies to the latest deployment.'
                    : degraded
                      ? 'Runs orchestrator heal — recommended when workloads are stopped.'
                      : undefined
            }
            onClick={() =>
              wrap('heal', async () => {
                await healDeployment(activeDeploymentId!);
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
          {showDestroy && activeDeploymentId && (
            <button
              type="button"
              disabled={opLocked}
              title={viewerMode ? viewerHint : busy !== null ? 'Wait for the current action to finish.' : undefined}
              onClick={() =>
                wrap('destroy', async () => {
                  await destroyDeployment(activeDeploymentId);
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
        {deploymentStatus === 'failed' && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-950 dark:border-red-900 dark:bg-red-950/35 dark:text-red-100">
            <p className="font-semibold">Deployment failed</p>
            <p className="mt-1 text-xs leading-relaxed opacity-90">
              Review the operation banner above for API details, inspect recent events, then{' '}
              <strong className="font-semibold">Retry deployment</strong> after fixing the topology or environment. If
              retry is not appropriate, adjust the graph and use <strong className="font-semibold">Deploy to runtime</strong>{' '}
              to create a fresh deployment attempt.
            </p>
            <button
              type="button"
              disabled={opLocked || !deployReadiness.deployable}
              title={viewerMode ? viewerHint : undefined}
              onClick={() => setDeployModalOpen(true)}
              className="mt-3 rounded-lg bg-red-800 px-4 py-2 text-xs font-semibold text-white hover:bg-red-900 disabled:opacity-50 dark:bg-red-700 dark:hover:bg-red-600"
            >
              Retry deployment
            </button>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Routed traffic & validation</h2>
        <p className="mt-0.5 text-xs text-cns-muted">
          Choose source and target for directed ping/HTTP. Quick-path buttons appear when this topology matches the routed
          host–router–service pattern. Latest cross-segment host → service tests feed the status banner.
        </p>
        {routedRoles.isRoutedLike ? (
          <p className="mt-2 rounded-md border border-violet-900/40 bg-violet-950/25 px-2 py-1.5 text-[11px] leading-snug text-violet-100">
            Routed lab pattern detected — after deploy, run <span className="font-semibold">Run routed ping</span> and{' '}
            <span className="font-semibold">Run routed HTTP</span> to exercise the full path across segments.
          </p>
        ) : null}
        {routedConnectivityVerified ? (
          <div
            role="status"
            className="mt-3 rounded-lg border border-emerald-600/50 bg-emerald-50 px-3 py-2 text-sm text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/35 dark:text-emerald-100"
          >
            Routed connectivity verified — latest host → service ping and HTTP both succeeded.
          </div>
        ) : null}
        {routedIssues.routeTableMismatchHint ? (
          <div className="mt-2 rounded-lg border border-amber-500/60 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-100">
            <span className="font-semibold">Route table mismatch:</span> deployment events suggest the in-container routing
            table does not match the intended multinet design — compare runtime <code className="font-mono">ip route</code>{' '}
            output with link gateways and endpoint IPs.
          </div>
        ) : null}
        {routedIssues.leafRouteValidationFailed ? (
          <div className="mt-2 rounded-lg border border-amber-500/60 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-100">
            <span className="font-semibold">Route table / validation:</span> deployment events report leaf route validation
            failures — reconcile gateways and CIDR intent with the router interfaces, then redeploy or heal.
          </div>
        ) : null}
        {routedIssues.dot254Gateway ? (
          <div className="mt-2 rounded-lg border border-amber-500/60 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-100">
            <span className="font-semibold">Bad gateway warning:</span> events mention a <code className="font-mono">.254</code>{' '}
            style gateway — for this lab, gateways should be the router NICs (
            <code className="font-mono">10.72.0.1</code> and <code className="font-mono">10.73.0.1</code>), not an arbitrary
            bridge address.
          </div>
        ) : null}
        {routedIssues.netAdminOrCapHint ? (
          <div className="mt-2 rounded-lg border border-sky-700/50 bg-sky-50 px-3 py-2 text-xs text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100">
            <span className="font-semibold">NET_ADMIN / capability hint:</span> events mention NET_ADMIN, cap_add, or route
            EPERM — the Docker engine host may need elevated capabilities for route programming inside containers.
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-[11px] text-cns-muted">
            Source
            <select
              className="mt-0.5 min-w-[11rem] rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={trafficSrc}
              onChange={(e) => setTrafficSrc(e.target.value)}
            >
              <option value="">—</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name} ({n.node_type})
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-[11px] text-cns-muted">
            Target
            <select
              className="mt-0.5 min-w-[11rem] rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={trafficTgt}
              onChange={(e) => setTrafficTgt(e.target.value)}
            >
              <option value="">—</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name} ({n.node_type})
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !canDirectedTraffic}
            title={
              !runtimeActive
                ? noActiveDeploymentHint ?? undefined
                : !canDirectedTraffic
                  ? 'Pick two different nodes as source and target.'
                  : undefined
            }
            onClick={() =>
              wrap('ping-sel', async () => {
                await runPingTest(id, { source_node_id: trafficSrc, target_node_id: trafficTgt, count: 3 });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Ping selected → target
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !canDirectedTraffic}
            title={
              !runtimeActive
                ? noActiveDeploymentHint ?? undefined
                : !canDirectedTraffic
                  ? 'Pick two different nodes as source and target.'
                  : undefined
            }
            onClick={() =>
              wrap('http-sel', async () => {
                await runHttpTest(id, {
                  source_node_id: trafficSrc,
                  target_node_id: trafficTgt,
                  path: '/',
                  port: 80,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            HTTP selected → target
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.host || !routedRoles.router}
            onClick={() =>
              wrap('ping-host-router', async () => {
                await runPingTest(id, {
                  source_node_id: routedRoles.host!.id,
                  target_node_id: routedRoles.router!.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Ping host → router
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.host || !routedRoles.router}
            onClick={() =>
              wrap('ping-router-host', async () => {
                await runPingTest(id, {
                  source_node_id: routedRoles.router!.id,
                  target_node_id: routedRoles.host!.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Ping router → host
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.router || !routedRoles.service}
            onClick={() =>
              wrap('ping-router-svc', async () => {
                await runPingTest(id, {
                  source_node_id: routedRoles.router!.id,
                  target_node_id: routedRoles.service!.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Ping router → service
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.host || !routedRoles.service}
            onClick={() =>
              wrap('routed-ping', async () => {
                await runPingTest(id, {
                  source_node_id: routedRoles.host!.id,
                  target_node_id: routedRoles.service!.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-950 hover:bg-violet-100 cns-disabled-control dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-100 dark:hover:bg-violet-900/55"
          >
            Run routed ping (host → service)
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.host || !routedRoles.service}
            onClick={() =>
              wrap('routed-http', async () => {
                await runHttpTest(id, {
                  source_node_id: routedRoles.host!.id,
                  target_node_id: routedRoles.service!.id,
                  path: '/',
                  port: 80,
                });
              })
            }
            className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-950 hover:bg-violet-100 cns-disabled-control dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-100 dark:hover:bg-violet-900/55"
          >
            Run routed HTTP (host → service)
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.service || !routedRoles.host}
            onClick={() =>
              wrap('ping-svc-host', async () => {
                await runPingTest(id, {
                  source_node_id: routedRoles.service!.id,
                  target_node_id: routedRoles.host!.id,
                  count: 3,
                });
              })
            }
            className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 cns-disabled-control dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Ping service → host (return path)
          </button>
          <button
            type="button"
            disabled={opLocked || !runtimeActive || !routedRoles.router}
            title={
              !runtimeActive
                ? noActiveDeploymentHint ?? undefined
                : !routedRoles.router
                  ? 'No router node in this topology.'
                  : undefined
            }
            onClick={() =>
              wrap('restart-router', async () => {
                await injectRestartNode(id, {
                  target_node_id: routedRoles.router!.id,
                  description: 'UI: restart router container',
                });
              })
            }
            className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100 cns-disabled-control dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-900/55"
          >
            Restart router node
          </button>
        </div>
        {busy ? (
          <p className="mt-2 flex items-center gap-2 text-xs text-cns-muted">
            <Spinner className="h-4 w-4" /> Working: {busy}…
          </p>
        ) : null}
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
            readOnlyTopology={viewerMode}
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
      {deploymentId ? <DeploymentOperationTimeline deploymentId={deploymentId} /> : null}
      {deploymentId ? (
        <DeploymentCleanupPanel
          deploymentId={deploymentId}
          viewerMode={viewerMode}
          onCleanupComplete={({ message }) => {
            if (message) setPageToast(message);
            void refreshLive();
          }}
        />
      ) : null}
      {deploymentId ? <DeploymentMetricsPanel deploymentId={deploymentId} /> : null}

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
          {eventsPollErr && <ApiErrorDisplay error={eventsPollErr} />}
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
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-cns-label">
                Topology segments (persisted links)
              </h4>
              <ul className="mt-2 space-y-2">
                {links.map((l) => (
                  <li
                    key={l.id}
                    className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-950/60"
                  >
                    <div className="font-mono text-[11px] text-zinc-900 dark:text-zinc-100">{l.network_name}</div>
                    <div className="mt-0.5 whitespace-pre-line font-mono text-[10px] text-cns-muted">
                      {formatLinkEdgeLabel(l)}
                    </div>
                  </li>
                ))}
                {links.length === 0 ? <li className="text-cns-muted">No links in this topology.</li> : null}
              </ul>
            </div>
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
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-cns-label">
                Node → container mapping
              </h4>
              <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-2 font-mono text-[10px] leading-snug text-zinc-800 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200">
                {JSON.stringify(runtime.node_runtime_mapping, null, 2)}
              </pre>
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
                    {c.intended_ip || c.actual_runtime_ip ? (
                      <div className="mt-1 space-y-0.5 font-mono text-[10px] text-zinc-700 dark:text-zinc-300">
                        {c.intended_ip ? <div>Intent IP: {c.intended_ip}</div> : null}
                        {c.actual_runtime_ip ? <div>Runtime IP: {c.actual_runtime_ip}</div> : null}
                      </div>
                    ) : null}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-zinc-600 dark:text-zinc-400">
                      <span>
                        ip_forward:{' '}
                        {c.ip_forward_enabled == null ? '—' : c.ip_forward_enabled ? 'on' : 'off'}
                      </span>
                      <span>forwarding_role: {c.forwarding_role ?? '—'}</span>
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
                    {c.routes_lines && c.routes_lines.length > 0 ? (
                      <div className="mt-2">
                        <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-label">
                          Route table (trimmed)
                        </div>
                        <pre className="mt-0.5 max-h-36 overflow-auto rounded border border-zinc-200 bg-zinc-50 p-2 font-mono text-[10px] leading-snug text-zinc-800 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200">
                          {c.routes_lines.join('\n')}
                        </pre>
                      </div>
                    ) : null}
                    {c.interface_lines && c.interface_lines.length > 0 ? (
                      <div className="mt-2">
                        <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-label">
                          Interface listing (trimmed)
                        </div>
                        <pre className="mt-0.5 max-h-36 overflow-auto rounded border border-zinc-200 bg-zinc-50 p-2 font-mono text-[10px] leading-snug text-zinc-800 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200">
                          {c.interface_lines.join('\n')}
                        </pre>
                      </div>
                    ) : null}
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
