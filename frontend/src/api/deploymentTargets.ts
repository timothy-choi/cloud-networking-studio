import { apiFetch } from './client';

export type DeploymentTargetType = 'remote_docker' | 'kubernetes' | 'terraform' | 'ansible';

export interface DeploymentTarget {
  id: string;
  project_id: string;
  name: string;
  target_type: DeploymentTargetType;
  config_json: Record<string, unknown>;
  credentials_ref: string | null;
  status: string;
  created_by_user_id: string | null;
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
