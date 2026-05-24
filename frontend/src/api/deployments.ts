import { apiFetch } from './client';
import type { NetworkAllocationMode } from '../lib/networkAllocation';
import type { DeploymentEventResponse, DeploymentResponse } from '../types/deployment';
import type { DeploymentTimelineResponse } from '../types/deploymentTimeline';
import type { DeploymentCleanupResponse, DeploymentCleanupStatusResponse } from '../types/cleanup';
import type { HealingResponse, ReconciliationResponse } from '../types/runtime';

export type DeployTopologyOptions = {
  network_allocation_mode?: NetworkAllocationMode;
  profile_id?: string;
  topology_version_id?: string;
};

export async function deployTopology(
  topologyId: string,
  options?: DeployTopologyOptions,
): Promise<DeploymentResponse> {
  const body: Record<string, string> = {};
  if (options?.network_allocation_mode != null) {
    body.network_allocation_mode = options.network_allocation_mode;
  }
  if (options?.profile_id) body.profile_id = options.profile_id;
  if (options?.topology_version_id) body.topology_version_id = options.topology_version_id;
  return apiFetch<DeploymentResponse>(`/topologies/${topologyId}/deploy`, {
    method: 'POST',
    body: Object.keys(body).length ? JSON.stringify(body) : undefined,
  });
}

export async function destroyDeployment(deploymentId: string): Promise<DeploymentResponse> {
  return apiFetch<DeploymentResponse>(`/deployments/${deploymentId}/destroy`, {
    method: 'POST',
  });
}

export async function listDeploymentEvents(
  deploymentId: string,
): Promise<DeploymentEventResponse[]> {
  return apiFetch<DeploymentEventResponse[]>(`/deployments/${deploymentId}/events`);
}

export async function getDeploymentTimeline(
  deploymentId: string,
): Promise<DeploymentTimelineResponse> {
  return apiFetch<DeploymentTimelineResponse>(`/deployments/${deploymentId}/timeline`);
}

export async function getDeploymentCleanupStatus(
  deploymentId: string,
): Promise<DeploymentCleanupStatusResponse> {
  return apiFetch<DeploymentCleanupStatusResponse>(`/deployments/${deploymentId}/cleanup-status`);
}

export async function runDeploymentCleanup(
  deploymentId: string,
): Promise<DeploymentCleanupResponse> {
  return apiFetch<DeploymentCleanupResponse>(`/deployments/${deploymentId}/cleanup`, {
    method: 'POST',
  });
}

export async function reconcileDeployment(deploymentId: string): Promise<ReconciliationResponse> {
  return apiFetch<ReconciliationResponse>(`/deployments/${deploymentId}/reconcile`, {
    method: 'POST',
  });
}

export async function healDeployment(deploymentId: string): Promise<HealingResponse> {
  return apiFetch<HealingResponse>(`/deployments/${deploymentId}/heal`, {
    method: 'POST',
  });
}
