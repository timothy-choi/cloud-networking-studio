import { apiFetch } from './client';
import type {
  DeploymentEventResponse,
  DeploymentResponse,
  HealingResponse,
  ReconciliationResponse,
} from '../types/api';

export async function deployTopology(topologyId: string): Promise<DeploymentResponse> {
  return apiFetch<DeploymentResponse>(`/topologies/${topologyId}/deploy`, {
    method: 'POST',
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
