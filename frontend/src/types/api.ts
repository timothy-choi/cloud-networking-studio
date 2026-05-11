/** Mirrors backend Pydantic/OpenAPI shapes used by the UI (subset). */

export type TopologyStatus = 'draft' | 'active' | 'archived';

export type NodeType = 'generic' | 'router' | 'switch' | 'host' | 'gateway';

export type DeploymentStatus =
  | 'pending'
  | 'provisioning'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'stopped';

export type DeploymentEventLevel = 'debug' | 'info' | 'warning' | 'error';

export interface TopologyResponse {
  id: string;
  name: string;
  description: string | null;
  status: TopologyStatus;
  runtime_target: string;
  networking_mode: string;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface TopologyCreate {
  name: string;
  description?: string | null;
  runtime_target: string;
  networking_mode: string;
  status?: TopologyStatus | null;
  config?: Record<string, unknown> | null;
}

export interface TopologyNodeResponse {
  id: string;
  topology_id: string;
  name: string;
  node_type: NodeType;
  image: string | null;
  ip_address: string | null;
  config: Record<string, unknown> | null;
}

export interface TopologyNodeCreate {
  name: string;
  node_type: NodeType;
  image?: string | null;
  ip_address?: string | null;
  config?: Record<string, unknown> | null;
}

export interface TopologyLinkResponse {
  id: string;
  topology_id: string;
  source_node_id: string;
  target_node_id: string;
  network_name: string;
  cidr: string | null;
  config: Record<string, unknown> | null;
}

export interface TopologyLinkCreate {
  source_node_id: string;
  target_node_id: string;
  network_name: string;
  cidr?: string | null;
  config?: Record<string, unknown> | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface ControllerStatusResponse {
  controller_mode: string;
  managed_deployments_count: number;
  active_deployments_count: number;
  supported_providers: string[];
  last_run_timestamp: string | null;
  health_summary: string;
}

export interface DeploymentEventResponse {
  id: string;
  deployment_id: string;
  level: DeploymentEventLevel;
  message: string;
  created_at: string;
}

export interface DeploymentResponse {
  id: string;
  topology_id: string;
  status: DeploymentStatus;
  runtime_target: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  events: DeploymentEventResponse[];
}

export interface RuntimeNetworkResponse {
  network_id: string;
  name: string;
  driver: string;
  labels: Record<string, string>;
  scope?: string | null;
  subnet_hints: string[];
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
  ipv4_by_network: Record<string, string>;
}

export interface RuntimeTopologyResponse {
  topology_id: string;
  deployment_status: DeploymentStatus | null;
  latest_deployment_id: string | null;
  runtime_provider: string;
  networks: RuntimeNetworkResponse[];
  containers: RuntimeContainerResponse[];
  node_runtime_mapping: Record<string, string>;
  container_states: Record<string, string>;
}

export interface TrafficTestResponse {
  id: string;
  topology_id: string;
  deployment_id: string | null;
  source_node_id: string;
  target_node_id: string | null;
  test_type: 'ping' | 'http';
  status: string;
  command: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: {
    stdout: string;
    stderr: string;
    exit_code: number;
    success: boolean;
    latency_ms: number | null;
  } | null;
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
