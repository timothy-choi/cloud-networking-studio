import { apiFetch } from './client';
import type { ServiceExposureRow } from '../types/runtime';

export async function listDeploymentExposures(deploymentId: string): Promise<{
  deployment_id: string;
  exposures: ServiceExposureRow[];
}> {
  return apiFetch(`/deployments/${deploymentId}/runtime/exposures`);
}

export async function exposeDeploymentService(
  deploymentId: string,
  serviceResourceId: string,
  body: { ttl_hours?: number } = {},
): Promise<ServiceExposureRow> {
  return apiFetch<ServiceExposureRow>(`/deployments/${deploymentId}/runtime/services/${serviceResourceId}/expose`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function unexposeDeploymentService(
  deploymentId: string,
  serviceResourceId: string,
): Promise<void> {
  await apiFetch<unknown>(`/deployments/${deploymentId}/runtime/services/${serviceResourceId}/expose`, {
    method: 'DELETE',
  });
}
