import { apiFetch } from './client';

export type InfrastructureDeploymentStatus =
  | 'pending'
  | 'validating'
  | 'validated'
  | 'planning'
  | 'awaiting_confirmation'
  | 'applying'
  | 'configuring'
  | 'succeeded'
  | 'configuration_failed'
  | 'configuration_timeout'
  | 'apply_partial'
  | 'registration_failed'
  | 'destroy_failed'
  | 'failed'
  | 'destroying'
  | 'destroyed';

export interface InfrastructureTemplate {
  template_id: string;
  provider: string;
  description: string;
  supported_providers: string[];
}

export interface InfrastructureDeployment {
  id: string;
  project_id: string;
  topology_id: string;
  name: string;
  stack_type: string;
  template_id: string;
  provider: string;
  status: InfrastructureDeploymentStatus;
  variables_json: Record<string, unknown>;
  plan_summary_json: Record<string, unknown> | null;
  outputs_json: Record<string, unknown>;
  inventory_json: Record<string, unknown>;
  state_metadata_json: Record<string, unknown>;
  events_json: Array<{ type: string; message?: string; timestamp?: string; metadata?: Record<string, unknown> }>;
  metrics_json: Record<string, unknown>;
  runtime_targets_json: Array<Record<string, unknown>>;
  error_message: string | null;
  credentials_ref: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  destroyed_at: string | null;
}

export interface InfrastructureExecution {
  id: string;
  infrastructure_deployment_id: string;
  execution_type: string;
  mode: string;
  status: string;
  runner_execution_id: string | null;
  logs: string | null;
  artifact_refs: Array<Record<string, unknown>>;
  duration_ms: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export async function listInfrastructureTemplates(): Promise<InfrastructureTemplate[]> {
  const res = await apiFetch<{ items: InfrastructureTemplate[] }>('/infrastructure/templates');
  return res.items;
}

export async function listInfrastructureDeployments(topologyId: string): Promise<InfrastructureDeployment[]> {
  const res = await apiFetch<{ items: InfrastructureDeployment[] }>(
    `/topologies/${topologyId}/infrastructure-deployments`,
  );
  return res.items;
}

export async function createInfrastructureDeployment(
  topologyId: string,
  body: {
    name: string;
    template_id: string;
    provider: string;
    variables?: Record<string, unknown>;
    credentials_ref?: string;
  },
): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/topologies/${topologyId}/infrastructure-deployments`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function validateInfrastructureDeployment(deploymentId: string): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}/validate`, {
    method: 'POST',
  });
}

export async function planInfrastructureDeployment(deploymentId: string): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}/plan`, {
    method: 'POST',
  });
}

export async function getInfrastructureDeployment(deploymentId: string): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}`);
}

export async function listInfrastructureExecutions(deploymentId: string): Promise<InfrastructureExecution[]> {
  const res = await apiFetch<{ items: InfrastructureExecution[] }>(
    `/infrastructure-deployments/${deploymentId}/executions`,
  );
  return res.items;
}

export async function confirmInfrastructureDeployment(
  deploymentId: string,
  body: {
    confirm?: boolean;
    confirmation_text?: string;
    unsafe_testing_override?: boolean;
  } = {},
): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({
      confirm: body.confirm ?? true,
      confirmation_text: body.confirmation_text,
      unsafe_testing_override: body.unsafe_testing_override ?? false,
    }),
  });
}

export async function retryInfrastructureConfiguration(deploymentId: string): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}/retry-configure`, {
    method: 'POST',
  });
}

export async function destroyInfrastructureDeployment(
  deploymentId: string,
  body: { confirmation_text?: string } = {},
): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(`/infrastructure-deployments/${deploymentId}/destroy`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function forceInfrastructureMetadataCleanup(
  deploymentId: string,
  confirmationText: string,
): Promise<InfrastructureDeployment> {
  return apiFetch<InfrastructureDeployment>(
    `/infrastructure-deployments/${deploymentId}/force-metadata-cleanup`,
    {
      method: 'POST',
      body: JSON.stringify({ confirmation_text: confirmationText }),
    },
  );
}
