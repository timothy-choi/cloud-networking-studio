import { apiFetch } from './client';
import type { DeploymentRuntimeDetailResponse } from '../types/runtime';

export async function fetchDeploymentRuntime(
  deploymentId: string,
): Promise<DeploymentRuntimeDetailResponse> {
  return apiFetch<DeploymentRuntimeDetailResponse>(`/deployments/${deploymentId}/runtime`);
}
