import { apiFetch } from './client';
import type {
  DeploymentMetricsResponse,
  PlatformMetricsResponse,
  ProjectMetricsResponse,
} from '../types/platformMetrics';

export async function getPlatformMetrics(): Promise<PlatformMetricsResponse> {
  return apiFetch<PlatformMetricsResponse>('/platform/metrics');
}

export async function getProjectMetrics(projectId: string): Promise<ProjectMetricsResponse> {
  return apiFetch<ProjectMetricsResponse>(`/projects/${projectId}/metrics`);
}

export async function getDeploymentMetrics(deploymentId: string): Promise<DeploymentMetricsResponse> {
  return apiFetch<DeploymentMetricsResponse>(`/deployments/${deploymentId}/metrics`);
}
