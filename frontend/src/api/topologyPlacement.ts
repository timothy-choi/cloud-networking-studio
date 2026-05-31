import { apiFetch } from './client';

export interface TopologyNodeResourceBreakdown {
  node_id: string;
  node_name: string;
  resource_cpu: number;
  resource_memory_mb: number;
  resource_disk_gb: number;
  replicas: number;
  node_role: string;
  exposure: string;
  stateful: boolean;
}

export interface PlacementAssignedNode {
  node_id: string;
  node_name: string;
  replica_index: number;
  display_name: string;
  resource_cpu: number;
  resource_memory_mb: number;
  resource_disk_gb: number;
  node_role: string;
  exposure: string;
  stateful: boolean;
  required_ports: number[];
}

export interface PlacementHost {
  host_index: number;
  estimated_cpu_used: number;
  estimated_memory_used_mb: number;
  assigned_nodes: PlacementAssignedNode[];
}

export interface TopologyResourceEstimate {
  total_cpu: number;
  total_memory_mb: number;
  total_disk_gb: number;
  total_replicas: number;
  node_count: number;
  workload_node_count: number;
  placement_unit_count: number;
  nodes: TopologyNodeResourceBreakdown[];
}

export interface TopologyPlacementPlan extends TopologyResourceEstimate {
  provider: string;
  recommended_host_count: number;
  recommended_machine_type: string;
  machine_rationale: string;
  hosts: PlacementHost[];
  warnings: string[];
  exposed_ports: number[];
  suggested_template_id: string;
}

export interface GenerateInfrastructureDeploymentResponse {
  deployment: Record<string, unknown>;
  placement_plan: TopologyPlacementPlan;
  capacity_check: {
    status: string;
    messages: string[];
    selected_machine_type?: string;
    recommended_host_count?: number;
  };
}

export async function getTopologyResourceEstimate(topologyId: string): Promise<TopologyResourceEstimate> {
  return apiFetch<TopologyResourceEstimate>(`/topologies/${topologyId}/resource-estimate`);
}

export async function getTopologyPlacementPlan(
  topologyId: string,
  params?: { provider?: string; machine_type?: string; host_count?: number },
): Promise<TopologyPlacementPlan> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<TopologyPlacementPlan>(`/topologies/${topologyId}/placement-plan${suffix}`);
}

export async function generateInfrastructureDeployment(
  topologyId: string,
  body: {
    provider?: string;
    template_id?: string;
    machine_type?: string;
    host_count?: number;
    credentials_ref?: string;
    name?: string;
    variables?: Record<string, unknown>;
  },
): Promise<GenerateInfrastructureDeploymentResponse> {
  return apiFetch<GenerateInfrastructureDeploymentResponse>(
    `/topologies/${topologyId}/generate-infrastructure-deployment`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}
