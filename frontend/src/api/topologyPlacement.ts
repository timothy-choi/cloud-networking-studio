import { apiFetch } from './client';

export interface TopologyNodeResourceBreakdown {
  node_id: string;
  node_name: string;
  /** Canonical placement fields */
  resource_cpu: number;
  resource_memory_mb: number;
  resource_disk_gb: number;
  resource_source?: string;
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
  resource_source?: string;
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
  utilization?: {
    cpu_utilization?: number;
    memory_utilization?: number;
    disk_utilization?: number;
  };
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
  id?: string | null;
  provider: string;
  placement_mode?: string;
  recommended_host_count: number;
  host_count?: number;
  recommended_machine_type: string;
  machine_rationale: string;
  hosts: PlacementHost[];
  placements?: PlacementHost[];
  warnings: string[];
  exposed_ports: number[];
  suggested_template_id: string;
  constraints_used?: Array<Record<string, unknown>>;
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

export type RuntimeStrategyStatus = 'available' | 'planning_only' | 'future';
export type RuntimeHostModel = 'single_host' | 'multi_host' | 'cluster';

export interface RuntimeStrategy {
  id: string;
  display_name: string;
  status: RuntimeStrategyStatus;
  runtime_provider: string;
  host_model: RuntimeHostModel;
  deployment_model: string;
  supports_multi_host: boolean;
  supports_runtime_target_generation: boolean;
  supports_external_deployment: boolean;
  description: string;
}

export interface RuntimeRequirementItem {
  key: string;
  label: string;
  description: string;
  required: boolean;
}

export interface RuntimeStrategyCapabilities {
  runtime_target_generation: boolean;
  external_deployment: boolean;
  multi_host: boolean;
}

export interface RuntimeStrategyPlan {
  recommended_runtime_strategy: string;
  selected_runtime_strategy: string;
  runtime_strategy: RuntimeStrategy;
  capabilities: RuntimeStrategyCapabilities;
  runtime_target_requirements: RuntimeRequirementItem[];
  deployment_requirements: RuntimeRequirementItem[];
  unsupported_features: string[];
  can_generate_infrastructure: boolean;
  generation_block_reason?: string | null;
  host_count: number;
  placement_constraints_count: number;
}

export interface RuntimeStrategyCostSummary {
  id: string;
  display_name: string;
  status: RuntimeStrategyStatus;
  runtime_provider: string;
  host_model: RuntimeHostModel;
  deployment_model: string;
  host_count: number;
}

export interface CostCapacityAnalysis {
  cost_estimate: {
    provider: string;
    machine_type: string;
    host_count: number;
    estimated_monthly_cost: {
      low: number;
      high: number;
      currency: string;
    };
  };
  capacity: {
    cpu_utilization_percent: number;
    memory_utilization_percent: number;
    disk_utilization_percent: number;
  };
  headroom: {
    cpu_headroom_percent: number;
    memory_headroom_percent: number;
    disk_headroom_percent: number;
    remaining_cpu: number;
    remaining_memory_mb: number;
    remaining_disk_gb: number;
  };
  scaling_risk: {
    scaling_risk: 'LOW' | 'MEDIUM' | 'HIGH';
    reasons: string[];
  };
  alternatives: {
    cheaper_alternative?: string | null;
    safer_alternative?: string | null;
  };
  runtime_strategy?: RuntimeStrategyCostSummary | null;
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
  params?: { provider?: string; machine_type?: string; host_count?: number; placement_mode?: string },
): Promise<TopologyPlacementPlan> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  if (params?.placement_mode) qs.set('placement_mode', params.placement_mode);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<TopologyPlacementPlan>(`/topologies/${topologyId}/placement-plan${suffix}`);
}

export async function getTopologyStrategyRecommendation(
  topologyId: string,
  params?: { provider?: string; machine_type?: string; host_count?: number; placement_mode?: string },
): Promise<StrategyRecommendation> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  if (params?.placement_mode) qs.set('placement_mode', params.placement_mode);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<StrategyRecommendation>(`/topologies/${topologyId}/strategy-recommendation${suffix}`);
}

export async function getTopologyCostCapacityAnalysis(
  topologyId: string,
  params?: { provider?: string; machine_type?: string; host_count?: number; placement_mode?: string },
): Promise<CostCapacityAnalysis> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  if (params?.placement_mode) qs.set('placement_mode', params.placement_mode);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<CostCapacityAnalysis>(`/topologies/${topologyId}/cost-capacity-analysis${suffix}`);
}

export async function getTopologyMultiHostPlacementPlan(
  topologyId: string,
  params?: { provider?: string; machine_type?: string; host_count?: number; placement_mode?: string; persist?: boolean },
): Promise<TopologyPlacementPlan> {
  const qs = new URLSearchParams();
  if (params?.provider) qs.set('provider', params.provider);
  if (params?.machine_type) qs.set('machine_type', params.machine_type);
  if (params?.host_count != null) qs.set('host_count', String(params.host_count));
  if (params?.placement_mode) qs.set('placement_mode', params.placement_mode);
  if (params?.persist != null) qs.set('persist', String(params.persist));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<TopologyPlacementPlan>(`/topologies/${topologyId}/multi-host-placement-plan${suffix}`);
}

export interface PlacementConstraint {
  id: string;
  topology_id: string;
  constraint_type: 'same_host' | 'different_host' | 'preferred_host';
  node_a: string;
  node_b?: string | null;
  preferred_host?: number | null;
  created_at: string;
}

export async function listPlacementConstraints(topologyId: string): Promise<PlacementConstraint[]> {
  const res = await apiFetch<{ items: PlacementConstraint[] }>(`/topologies/${topologyId}/placement-constraints`);
  return res.items;
}

export async function createPlacementConstraint(
  topologyId: string,
  body: {
    constraint_type: PlacementConstraint['constraint_type'];
    node_a: string;
    node_b?: string | null;
    preferred_host?: number | null;
  },
): Promise<PlacementConstraint> {
  return apiFetch<PlacementConstraint>(`/topologies/${topologyId}/placement-constraints`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deletePlacementConstraint(topologyId: string, constraintId: string): Promise<void> {
  await apiFetch<void>(`/topologies/${topologyId}/placement-constraints/${constraintId}`, {
    method: 'DELETE',
  });
}

export function runtimeHostModelLabel(hostModel: RuntimeHostModel): string {
  if (hostModel === 'single_host') return 'single host';
  if (hostModel === 'multi_host') return 'multi host';
  return 'cluster';
}

export function runtimeDeploymentModelLabel(deploymentModel: string): string {
  if (deploymentModel === 'docker_compose') return 'Docker Compose';
  if (deploymentModel === 'multi_host_compose') return 'Multi-host Compose';
  if (deploymentModel === 'manifests_or_helm') return 'Manifests or Helm';
  return deploymentModel.replaceAll('_', ' ');
}

export function strategyStatusLabel(status: DeploymentStrategyStatus): string {
  if (status === 'available') return 'available';
  if (status === 'planning_only') return 'planning only';
  return 'future';
}

export function isStrategySelectable(status: DeploymentStrategyStatus): boolean {
  return status === 'available';
}

export interface RecommendedOverrides {
  machine_type?: string | null;
  strategy?: string | null;
  machine_type_valid: boolean;
  strategy_valid: boolean;
}

export interface AiInfrastructureAdvice {
  summary: string;
  risks: string[];
  suggestions: string[];
  recommended_overrides: RecommendedOverrides;
  explanation: string;
  advisor_mode: string;
  advisory_only: boolean;
}

export async function getAiInfrastructureAdvice(
  topologyId: string,
  body: {
    provider?: string;
    selected_strategy?: string;
    selected_machine_type?: string;
    credential_profile_id?: string;
  },
): Promise<AiInfrastructureAdvice> {
  return apiFetch<AiInfrastructureAdvice>(`/topologies/${topologyId}/ai-infrastructure-advice`, {
    debugLabel: 'ai-infrastructure-advice',
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export const APPLY_SAFE_MACHINE_TYPES = ['e2-micro', 'e2-small', 'e2-medium'] as const;

export function isApplySafeMachineType(machineType: string): boolean {
  return (APPLY_SAFE_MACHINE_TYPES as readonly string[]).includes(machineType.trim());
}

export async function generateInfrastructureDeployment(
  topologyId: string,
  body: {
    provider?: string;
    template_id?: string;
    machine_type?: string;
    host_count?: number;
    placement_mode?: string;
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
  const sourceLabel = node.resource_source ? `, source: ${node.resource_source}` : '';
  return `${name}: ${nodeCpu(node)} CPU, ${nodeMemoryMb(node)} MB, ${nodeDiskGb(node)} GB disk, ${replicasLabel}${sourceLabel}`;
}
