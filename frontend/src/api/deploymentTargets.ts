import { apiFetch } from './client';

export type DeploymentTargetType = 'remote_docker' | 'kubernetes' | 'terraform' | 'ansible';

/** Runtime targets where topology workloads are deployed. */
export type RuntimeDeploymentTargetType = 'remote_docker' | 'kubernetes';

export const RUNTIME_DEPLOYMENT_TARGET_TYPES: RuntimeDeploymentTargetType[] = [
  'remote_docker',
  'kubernetes',
];

export interface DeploymentTarget {
  id: string;
  project_id: string;
  name: string;
  target_type: DeploymentTargetType;
  config_json: Record<string, unknown>;
  credentials_ref: string | null;
  status: string;
  created_by_user_id: string | null;
  infrastructure_deployment_id?: string | null;
  created_at: string;
}

export async function listDeploymentTargets(projectId: string): Promise<DeploymentTarget[]> {
  const res = await apiFetch<{ items: DeploymentTarget[] }>(
    `/projects/${projectId}/deployment-targets`,
  );
  return res.items;
}

export async function createDeploymentTarget(
  projectId: string,
  body: {
    name: string;
    target_type: DeploymentTargetType;
    config_json?: Record<string, unknown>;
    credentials_ref?: string | null;
    status?: string;
  },
): Promise<DeploymentTarget> {
  return apiFetch<DeploymentTarget>(`/projects/${projectId}/deployment-targets`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getDeploymentTarget(targetId: string): Promise<DeploymentTarget> {
  return apiFetch<DeploymentTarget>(`/deployment-targets/${targetId}`);
}

export async function updateDeploymentTarget(
  targetId: string,
  body: {
    name?: string;
    config_json?: Record<string, unknown>;
    credentials_ref?: string | null;
    status?: string;
  },
): Promise<DeploymentTarget> {
  return apiFetch<DeploymentTarget>(`/deployment-targets/${targetId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteDeploymentTarget(
  targetId: string,
  options?: { force?: boolean },
): Promise<void> {
  const query = options?.force ? '?force=true' : '';
  return apiFetch<void>(`/deployment-targets/${targetId}${query}`, {
    method: 'DELETE',
  });
}
