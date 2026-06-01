import { apiFetch } from './client';

export interface TopologyNodeResourceBreakdown {
  node_id: string;
  node_name: string;
  /** Canonical placement fields */
  resource_cpu: number;
  resource_memory_mb: number;
  resource_disk_gb: number;
  /** API aliases (same values as resource_*) */
  cpu?: number;
  memory_mb?: number;
  disk_gb?: number;
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
  machine_type: string;
  cpu_used: number;
  cpu_capacity: number;
  memory_used_mb: number;
  memory_capacity_mb: number;
  disk_used_gb: number;
  disk_capacity_gb: number;
  assigned_nodes: string[];
  assigned_node_details?: PlacementAssignedNode[];
  estimated_cpu_used?: number;
  estimated_memory_used_mb?: number;
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

export type DeploymentStrategyStatus = 'available' | 'planning_only' | 'future';

export interface DeploymentStrategy {
  id: string;
  display_name: string;
  status: DeploymentStrategyStatus;
  description: string;
  min_hosts: number;
  max_hosts: number;
  supports_multi_host: boolean;
  supports_stateful: boolean;
  supports_public_ingress: boolean;
  runtime_type: string;
  template_id: string;
}

export interface StrategyRecommendation {
  recommended_strategy: string;
  alternatives: string[];
  reasons: string[];
  warnings: string[];
  strategies: DeploymentStrategy[];
  recommended_strategy_detail?: DeploymentStrategy | null;
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

export async function getTopologyStrategyRecommendation(
  topologyId: string,
  params?: { provider?: string; machine_type?: string; host_count?: number },
): Promise<StrategyRecommendation> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<StrategyRecommendation>(`/topologies/${topologyId}/strategy-recommendation${suffix}`);
}

export function strategyStatusLabel(status: DeploymentStrategyStatus): string {
  if (status === 'available') return 'available';
  if (status === 'planning_only') return 'planning only';
  return 'future';
}

export function isStrategySelectable(status: DeploymentStrategyStatus): boolean {
  return status === 'available';
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

function nodeCpu(node: TopologyNodeResourceBreakdown): number {
  return node.cpu ?? node.resource_cpu;
}

function nodeMemoryMb(node: TopologyNodeResourceBreakdown): number {
  return node.memory_mb ?? node.resource_memory_mb;
}

function nodeDiskGb(node: TopologyNodeResourceBreakdown): number {
  return node.disk_gb ?? node.resource_disk_gb;
}

export function formatHostUtilization(host: PlacementHost): { cpu: string; memory: string; disk: string } {
  return {
    cpu: `${host.cpu_used} / ${host.cpu_capacity} vCPU`,
    memory: `${host.memory_used_mb} / ${host.memory_capacity_mb} MB`,
    disk: `${host.disk_used_gb} / ${host.disk_capacity_gb} GB`,
  };
}

export function formatNodeResourceLine(node: TopologyNodeResourceBreakdown): string {
  const name = node.node_name?.trim() || 'unnamed node';
  const replicasLabel = node.replicas === 1 ? '1 replica' : `${node.replicas} replicas`;
  return `${name}: ${nodeCpu(node)} CPU, ${nodeMemoryMb(node)} MB, ${nodeDiskGb(node)} GB disk, ${replicasLabel}`;
}
