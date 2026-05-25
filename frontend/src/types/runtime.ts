/** Live provider snapshot for topology-scoped runtime APIs. */

import type { DeploymentStatus } from './deployment';

export interface RuntimeNetworkResponse {
  network_id: string;
  name: string;
  driver: string;
  labels: Record<string, string>;
  scope?: string | null;
  subnet_hints: string[];
}

export interface RuntimeNetworkInterfaceResponse {
  docker_network: string;
  interface: string;
  ipv4: string;
  gateway?: string | null;
  logical_network?: string | null;
}

export interface RuntimeContainerResponse {
  container_id: string;
  short_id: string;
  name: string;
  image: string;
  status: string;
  state_status?: string | null;
  running: boolean;
  labels: Record<string, string>;
  node_id: string | null;
  intended_ip?: string | null;
  actual_runtime_ip?: string | null;
  ipv4_by_network: Record<string, string>;
  network_interfaces?: RuntimeNetworkInterfaceResponse[];
  routes_lines?: string[];
  interface_lines?: string[];
  ip_forward_enabled?: boolean | null;
  forwarding_role?: string | null;
}

export interface RuntimeTopologyResponse {
  topology_id: string;
  status?: string;
  resources?: RuntimeAccessResourceRow[];
  warning?: string | null;
  deployment_status: DeploymentStatus | null;
  latest_deployment_id: string | null;
  topology_sync_status?: string | null;
  runtime_provider: string;
  networks: RuntimeNetworkResponse[];
  containers: RuntimeContainerResponse[];
  node_runtime_mapping: Record<string, string>;
  container_states: Record<string, string>;
}

export interface ReconciliationResponse {
  deployment_id: string;
  topology_id: string;
  missing_network: boolean;
  missing_node_ids: string[];
  stopped_containers: { container_id: string; name: string }[];
  summary_lines: string[];
}

export interface HealingResponse {
  deployment_id: string;
  topology_id: string;
  reconciliation_missing_network: boolean;
  reconciliation_missing_node_ids: string[];
  reconciliation_stopped_count: number;
  restarted_containers: { container_id: string; name: string }[];
  skipped_missing_resources: string[];
  healing_errors: string[];
}

/** Aggregated health tier for UI badges (derived from runtime + topology). */
export type RuntimeHealthTier = 'healthy' | 'degraded' | 'failed' | 'idle';

/** Persisted / merged runtime access row (node, service, network, …). */
export type RuntimeAccessResourceRow = {
  id?: string;
  type: string;
  node_id?: string | null;
  service_id?: string | null;
  name: string;
  runtime_name: string;
  runtime_provider?: string;
  namespace_or_network?: string | null;
  status?: string | null;
  ports?: unknown;
  internal_url?: string | null;
  external_url?: string | null;
  metadata?: Record<string, string> | null;
};

export type RuntimeAccessEndpoint = {
  kind?: string;
  name?: string;
  internal_url?: string | null;
  external_url?: string | null;
};

/** Step 40: user-requested external reachability for one persisted service row. */
export type ServiceExposureRow = {
  id: string;
  deployment_id: string;
  runtime_resource_id: string;
  exposure_type: string;
  external_url?: string | null;
  external_host?: string | null;
  external_port?: number | null;
  status: string;
  expires_at?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
};

/** Full deployment runtime payload including integration instructions. */
export interface DeploymentRuntimeDetailResponse {
  deployment_id: string;
  topology_id: string;
  runtime_provider: string;
  deployment_status: DeploymentStatus;
  networks: RuntimeNetworkResponse[];
  containers: RuntimeContainerResponse[];
  node_runtime_mapping: Record<string, string>;
  container_states: Record<string, string>;
  status?: string | null;
  namespace_or_network?: string | null;
  nodes: RuntimeAccessResourceRow[];
  services: RuntimeAccessResourceRow[];
  endpoints: RuntimeAccessEndpoint[];
  instructions: Record<string, unknown> | null;
  exposures?: ServiceExposureRow[];
}
