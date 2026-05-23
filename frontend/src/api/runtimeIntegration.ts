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

export type IntegrationServiceOutput = {
  name: string;
  runtime_name?: string | null;
  internal_url?: string | null;
  external_url?: string | null;
  preferred_url?: string | null;
  endpoint_scope: 'external' | 'internal_only' | string;
  url_note?: string | null;
  protocol?: string | null;
  port?: number | null;
  recommended_env_var: string;
  env_vars: Record<string, string>;
};

export type IntegrationOutputsBundle = {
  env: string;
  curl: string;
  bash: string;
  python: string;
  javascript: string;
  typescript: string;
  java: string;
  go: string;
  ruby: string;
  php: string;
  csharp: string;
  github_actions: string;
  docker_compose_env: string;
  kubernetes_configmap: string;
};

export type DeploymentIntegrationOutputsResponse = {
  deployment_id: string;
  topology_id: string;
  runtime_provider: string;
  namespace_or_network?: string | null;
  services: IntegrationServiceOutput[];
  outputs: IntegrationOutputsBundle;
  metadata?: Record<string, unknown>;
};

export type AppLanguageKey =
  | 'curl'
  | 'python'
  | 'javascript'
  | 'typescript'
  | 'java'
  | 'go'
  | 'ruby'
  | 'php'
  | 'csharp';

export const APP_LANGUAGE_OPTIONS: { id: AppLanguageKey; label: string }[] = [
  { id: 'curl', label: 'curl' },
  { id: 'python', label: 'Python' },
  { id: 'javascript', label: 'JavaScript' },
  { id: 'typescript', label: 'TypeScript' },
  { id: 'java', label: 'Java' },
  { id: 'go', label: 'Go' },
  { id: 'ruby', label: 'Ruby' },
  { id: 'php', label: 'PHP' },
  { id: 'csharp', label: 'C#' },
];

export function fetchDeploymentIntegration(deploymentId: string) {
  return apiFetch<DeploymentIntegrationResponse>(`/deployments/${deploymentId}/runtime/integration`);
}

export function fetchDeploymentRuntimeMapping(deploymentId: string) {
  return apiFetch<DeploymentRuntimeMappingResponse>(`/deployments/${deploymentId}/runtime/mapping`);
}

export function fetchDeploymentIntegrationOutputs(deploymentId: string) {
  return apiFetch<DeploymentIntegrationOutputsResponse>(
    `/deployments/${deploymentId}/integration-outputs`,
  );
}
