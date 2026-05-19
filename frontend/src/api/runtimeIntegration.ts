import { apiFetch } from './client';

export type IntegrationSnippet = {
  id: string;
  title: string;
  language: string;
  content: string;
};

export type DeploymentIntegrationResponse = {
  deployment_id: string;
  topology_id: string;
  runtime_provider: string;
  namespace_or_network?: string | null;
  internal_endpoints: Record<string, unknown>[];
  exposed_endpoints: Record<string, unknown>[];
  env_vars: Record<string, string>;
  connect_your_app: Record<string, unknown>;
  snippets: IntegrationSnippet[];
  instructions: Record<string, unknown>;
};

export type RuntimeMappingRow = {
  topology_node_id?: string | null;
  topology_node_name?: string | null;
  resource_id?: string | null;
  resource_type?: string | null;
  runtime_name?: string | null;
  container_id?: string | null;
  pod_name?: string | null;
  internal_url?: string | null;
  external_url?: string | null;
  namespace_or_network?: string | null;
  status?: string | null;
};

export type DeploymentRuntimeMappingResponse = {
  deployment_id: string;
  topology_id: string;
  runtime_provider: string;
  rows: RuntimeMappingRow[];
};

export function fetchDeploymentIntegration(deploymentId: string) {
  return apiFetch<DeploymentIntegrationResponse>(`/deployments/${deploymentId}/runtime/integration`);
}

export function fetchDeploymentRuntimeMapping(deploymentId: string) {
  return apiFetch<DeploymentRuntimeMappingResponse>(`/deployments/${deploymentId}/runtime/mapping`);
}
