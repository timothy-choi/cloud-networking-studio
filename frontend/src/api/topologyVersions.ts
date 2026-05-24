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

export async function rollbackTopologyVersion(
  topologyId: string,
  versionId: string,
): Promise<{ version: TopologyVersion; message: string }> {
  return apiFetch(`/topologies/${topologyId}/versions/${versionId}/rollback`, {
    method: 'POST',
  });
}
