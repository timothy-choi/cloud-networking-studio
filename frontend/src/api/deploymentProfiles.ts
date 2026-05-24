import { apiFetch } from './client';

export type DeploymentProfileType = 'dev' | 'staging' | 'prod_like' | 'custom';

export interface DeploymentProfile {
  id: string;
  topology_id: string;
  name: string;
  description: string | null;
  profile_type: DeploymentProfileType;
  config_json: Record<string, unknown>;
  is_default: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export async function listDeploymentProfiles(topologyId: string): Promise<DeploymentProfile[]> {
  const res = await apiFetch<{ items: DeploymentProfile[] }>(`/topologies/${topologyId}/profiles`);
  return res.items;
}

export async function createDeploymentProfile(
  topologyId: string,
  body: {
    name: string;
    description?: string;
    profile_type?: DeploymentProfileType;
    config_json?: Record<string, unknown>;
    is_default?: boolean;
  },
): Promise<DeploymentProfile> {
  return apiFetch<DeploymentProfile>(`/topologies/${topologyId}/profiles`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateDeploymentProfile(
  topologyId: string,
  profileId: string,
  body: Partial<{
    name: string;
    description: string;
    profile_type: DeploymentProfileType;
    config_json: Record<string, unknown>;
  }>,
): Promise<DeploymentProfile> {
  return apiFetch<DeploymentProfile>(`/topologies/${topologyId}/profiles/${profileId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteDeploymentProfile(topologyId: string, profileId: string): Promise<void> {
  await apiFetch(`/topologies/${topologyId}/profiles/${profileId}`, { method: 'DELETE' });
}

export async function setDefaultDeploymentProfile(
  topologyId: string,
  profileId: string,
): Promise<DeploymentProfile> {
  return apiFetch<DeploymentProfile>(`/topologies/${topologyId}/profiles/${profileId}/set-default`, {
    method: 'POST',
  });
}
