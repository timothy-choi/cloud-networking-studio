import { apiFetch } from './client';

export type ExternalJobMode = 'validate' | 'plan' | 'apply' | 'destroy';
export type ExternalJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface ExternalDeploymentJob {
  id: string;
  project_id: string;
  topology_id: string;
  target_id: string;
  mode: ExternalJobMode;
  status: ExternalJobStatus;
  logs: string | null;
  artifact_refs: Array<Record<string, unknown>>;
  created_by_user_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExternalDeployment {
  id: string;
  project_id: string;
  topology_id: string;
  target_id: string;
  job_id: string | null;
  compose_project_name: string;
  remote_workdir: string;
  status: string;
  services_json: Array<Record<string, unknown>>;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  destroyed_at: string | null;
}

export async function listExternalDeploymentJobs(
  topologyId: string,
): Promise<ExternalDeploymentJob[]> {
  const res = await apiFetch<{ items: ExternalDeploymentJob[] }>(
    `/topologies/${topologyId}/external-deployment-jobs`,
  );
  return res.items;
}

export async function listExternalDeployments(
  topologyId: string,
): Promise<ExternalDeployment[]> {
  const res = await apiFetch<{ items: ExternalDeployment[] }>(
    `/topologies/${topologyId}/external-deployments`,
  );
  return res.items;
}

export async function createExternalDeploymentJob(
  topologyId: string,
  body: { target_id: string; mode: ExternalJobMode },
): Promise<ExternalDeploymentJob> {
  return apiFetch<ExternalDeploymentJob>(`/topologies/${topologyId}/external-deployment-jobs`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getExternalDeploymentJob(jobId: string): Promise<ExternalDeploymentJob> {
  return apiFetch<ExternalDeploymentJob>(`/external-deployment-jobs/${jobId}`);
}

export async function getExternalDeploymentJobLogs(
  jobId: string,
): Promise<{ job_id: string; status: string; logs: string }> {
  return apiFetch(`/external-deployment-jobs/${jobId}/logs`);
}
