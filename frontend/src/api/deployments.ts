import { apiFetch } from './client';
import type { NetworkAllocationMode } from '../lib/networkAllocation';
import type { DeploymentEventResponse, DeploymentResponse } from '../types/deployment';
import type { DeploymentTimelineResponse } from '../types/deploymentTimeline';
import type { HealingResponse, ReconciliationResponse } from '../types/runtime';

export type DeployTopologyOptions = {
  network_allocation_mode?: NetworkAllocationMode;
};

export async function deployTopology(
  topologyId: string,
  options?: DeployTopologyOptions,
): Promise<DeploymentResponse> {
  const body =
    options?.network_allocation_mode != null
      ? { network_allocation_mode: options.network_allocation_mode }
      : undefined;
  return apiFetch<DeploymentResponse>(`/topologies/${topologyId}/deploy`, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
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
