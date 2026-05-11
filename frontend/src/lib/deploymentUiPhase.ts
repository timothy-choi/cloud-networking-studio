import type { DeploymentStatus } from '../types/deployment';
import type { RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyStatus } from '../types/topology';
import { hasStoppedContainers } from './runtimeHealth';

/** UI-only lifecycle phase derived from runtime + local controller activity. */
export type ControlPlanePhase =
  | 'inactive'
  | 'ready'
  | 'deploying'
  | 'healthy'
  | 'degraded'
  | 'healing'
  | 'failed'
  | 'stopped';

export function deriveControlPlanePhase(
  runtime: RuntimeTopologyResponse | null,
  topologyStatus: TopologyStatus,
  localBusy: string | null,
  nodeCount: number,
): { phase: ControlPlanePhase; shortLabel: string; description: string } {
  const ds: DeploymentStatus | null = runtime?.deployment_status ?? null;

  if (localBusy === 'heal') {
    return { phase: 'healing', shortLabel: 'Healing', description: 'Heal operation in progress.' };
  }
  if (localBusy === 'reconcile') {
    return { phase: 'healing', shortLabel: 'Reconciling', description: 'Reconciliation pass running.' };
  }
  if (localBusy === 'deploy') {
    return { phase: 'deploying', shortLabel: 'Deploying', description: 'Deployment request in flight.' };
  }

  if (ds === 'failed') {
    return { phase: 'failed', shortLabel: 'Failed', description: 'Last deployment failed.' };
  }
  if (ds === 'stopped' || ds === 'cancelled') {
    return { phase: 'stopped', shortLabel: 'Stopped', description: 'Deployment is stopped or cancelled.' };
  }
  if (ds === 'pending' || ds === 'provisioning') {
    return { phase: 'deploying', shortLabel: 'Deploying', description: 'Runtime is provisioning resources.' };
  }

  if (!runtime?.latest_deployment_id && topologyStatus === 'draft' && nodeCount === 0) {
    return { phase: 'inactive', shortLabel: 'Inactive', description: 'Add nodes or load a template to begin.' };
  }

  if (!runtime?.latest_deployment_id && topologyStatus === 'draft' && nodeCount > 0) {
    return {
      phase: 'ready',
      shortLabel: 'Ready',
      description: 'Topology intent saved — deploy to provision the runtime.',
    };
  }

  if (hasStoppedContainers(runtime)) {
    return { phase: 'degraded', shortLabel: 'Degraded', description: 'One or more containers are not running.' };
  }

  if (ds === 'running' || ds === 'succeeded') {
    return {
      phase: 'healthy',
      shortLabel: 'Healthy',
      description: 'Deployment reports success and workloads are running.',
    };
  }

  return { phase: 'ready', shortLabel: 'Ready', description: 'Control plane idle.' };
}
