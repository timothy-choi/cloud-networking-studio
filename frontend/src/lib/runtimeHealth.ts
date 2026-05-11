import type { DeploymentStatus } from '../types/deployment';
import type { RuntimeHealthTier, RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyStatus } from '../types/topology';

export function hasStoppedContainers(runtime: RuntimeTopologyResponse | null): boolean {
  if (!runtime?.containers?.length) return false;
  return runtime.containers.some((c) => !c.running);
}

export function deriveRuntimeHealth(
  runtime: RuntimeTopologyResponse | null,
  topologyStatus: TopologyStatus,
): RuntimeHealthTier {
  const ds = runtime?.deployment_status;
  if (ds === 'failed') return 'failed';
  if (!runtime?.latest_deployment_id && topologyStatus === 'draft') return 'idle';
  if (ds === 'pending' || ds === 'deploying' || ds === 'stopping') return 'degraded';
  if (hasStoppedContainers(runtime)) return 'degraded';
  if (ds === 'stopped') return 'idle';
  if (ds === 'succeeded') return 'healthy';
  return 'idle';
}

export function deploymentPhaseActive(status: DeploymentStatus | null): boolean {
  if (!status) return false;
  return ['pending', 'deploying', 'stopping'].includes(status);
}

export function deploymentWorkloadLive(status: DeploymentStatus | null): boolean {
  if (!status) return false;
  return ['pending', 'deploying', 'stopping', 'succeeded'].includes(status);
}

/** Map topology node → workload running state using runtime snapshot. */
export function nodeWorkloadStatus(
  nodeId: string,
  runtime: RuntimeTopologyResponse | null,
): 'running' | 'stopped' | 'unknown' {
  if (!runtime?.containers?.length) return 'unknown';
  const c = runtime.containers.find((x) => x.node_id === nodeId);
  if (!c) return 'unknown';
  return c.running ? 'running' : 'stopped';
}
