import { apiFetch } from './client';

export type TopologyVersionSource = 'manual' | 'autosave' | 'rollback' | 'deploy';

export interface TopologyVersion {
  id: string;
  topology_id: string;
  version_number: number;
  name: string | null;
  description: string | null;
  source: TopologyVersionSource;
  parent_version_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface TopologyVersionDetail extends TopologyVersion {
  snapshot_json: Record<string, unknown>;
}

export interface TopologyVersionDiff {
  base_version_id: string;
  compare_version_id: string;
  diff: Record<string, unknown>;
}

export type RollbackMode = 'config_only' | 'rollback_and_destroy' | 'rollback_and_redeploy';

export interface RollbackImpactDeployment {
  id: string;
  status: string;
  topology_sync_status?: string | null;
}

export interface TopologyVersionRollbackImpact {
  active_deployment_count: number;
  active_deployments: RollbackImpactDeployment[];
  nodes_removed: string[];
  nodes_added: string[];
  services_removed: string[];
  removes_deployed_nodes: boolean;
  nodes_removed_from_runtime: string[];
  target_node_count: number;
  current_node_count: number;
  warning_message: string | null;
}

export interface TopologyVersionRollbackResult {
  version: TopologyVersion;
  mode: RollbackMode;
  message: string;
  impact: TopologyVersionRollbackImpact | null;
  destroyed_deployment_ids: string[];
  redeployed_deployment_id: string | null;
}

export async function listTopologyVersions(topologyId: string): Promise<TopologyVersion[]> {
  const res = await apiFetch<{ items: TopologyVersion[] }>(`/topologies/${topologyId}/versions`);
  return res.items;
}

export async function createTopologyVersion(
  topologyId: string,
  body?: { name?: string; description?: string },
): Promise<TopologyVersion> {
  return apiFetch<TopologyVersion>(`/topologies/${topologyId}/versions`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  });
}

export async function getTopologyVersion(
  topologyId: string,
  versionId: string,
): Promise<TopologyVersionDetail> {
  return apiFetch<TopologyVersionDetail>(`/topologies/${topologyId}/versions/${versionId}`);
}

export async function diffTopologyVersions(
  topologyId: string,
  versionId: string,
  againstVersionId: string,
): Promise<TopologyVersionDiff> {
  return apiFetch<TopologyVersionDiff>(
    `/topologies/${topologyId}/versions/${versionId}/diff?against=${encodeURIComponent(againstVersionId)}`,
  );
}

export async function getRollbackImpact(
  topologyId: string,
  versionId: string,
): Promise<TopologyVersionRollbackImpact> {
  return apiFetch<TopologyVersionRollbackImpact>(
    `/topologies/${topologyId}/versions/${versionId}/rollback-impact`,
  );
}

export async function rollbackTopologyVersion(
  topologyId: string,
  versionId: string,
  mode: RollbackMode = 'config_only',
): Promise<TopologyVersionRollbackResult> {
  return apiFetch(`/topologies/${topologyId}/versions/${versionId}/rollback`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}
