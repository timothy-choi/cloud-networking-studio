import { apiFetch } from './client';

export interface TopologyNodeResourceBreakdown {
  node_id: string;
  name: string;
  node_type: string;
  cpu_request: number;
  memory_request_mb: number;
  disk_request_gb: number;
  replicas: number;
}

export interface TopologyResourceEstimate {
  total_cpu: number;
  total_memory_mb: number;
  total_disk_gb: number;
  total_replicas: number;
  node_count: number;
  workload_node_count: number;
  nodes: TopologyNodeResourceBreakdown[];
}

export type CapacityStatus = 'compatible' | 'warning' | 'insufficient_capacity';

export interface TopologyCapacityCheck {
  status: CapacityStatus;
  messages: string[];
  resource_estimate: TopologyResourceEstimate;
  selected_provider: string;
  selected_machine_type: string | null;
  available_memory_mb: number | null;
  available_cpu: number | null;
  required_memory_mb: number;
  required_cpu: number;
}

export interface InfrastructureRecommendations {
  resource_estimate: TopologyResourceEstimate;
  recommendations: Record<string, string[]>;
  suggested_template_id: string;
  suggested_provider: string;
  suggested_variables: Record<string, unknown>;
  rationale: string[];
}

export interface GenerateInfrastructureDeploymentResult {
  deployment: Record<string, unknown>;
  resource_estimate: TopologyResourceEstimate;
  recommendations: Record<string, string[]>;
  capacity_check: TopologyCapacityCheck;
}

export async function getTopologyResourceEstimate(topologyId: string): Promise<TopologyResourceEstimate> {
  return apiFetch<TopologyResourceEstimate>(`/topologies/${topologyId}/resource-estimate`);
}

export async function getTopologyInfrastructureRecommendations(
  topologyId: string,
): Promise<InfrastructureRecommendations> {
  return apiFetch<InfrastructureRecommendations>(`/topologies/${topologyId}/infrastructure-recommendations`);
}

export async function generateInfrastructureDeployment(
  topologyId: string,
  body: {
    name?: string;
    provider?: string;
    template_id?: string;
    machine_type?: string;
    credentials_ref?: string;
    variables?: Record<string, unknown>;
  },
): Promise<GenerateInfrastructureDeploymentResult> {
  return apiFetch<GenerateInfrastructureDeploymentResult>(
    `/topologies/${topologyId}/generate-infrastructure-deployment`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}
