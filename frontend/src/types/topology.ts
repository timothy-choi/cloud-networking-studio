/** Topology graph intent (nodes, links) persisted by the control plane. */

export type TopologyStatus = 'draft' | 'active' | 'archived';

export type NodeType = 'generic' | 'router' | 'switch' | 'host' | 'gateway';

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
  /** Owning project when using multi-tenant projects. */
  project_id?: string | null;
  /** Present on list/detail API responses. */
  node_count?: number | null;
  link_count?: number | null;
}

export interface TopologyCreate {
  name: string;
  description?: string | null;
  runtime_target: string;
  networking_mode: string;
  status?: TopologyStatus | null;
  config?: Record<string, unknown> | null;
  /** When omitted, the API uses your default/first project. */
  project_id?: string | null;
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
  gateway?: string | null;
  vlan_tag?: number | null;
  source_endpoint_ip?: string | null;
  target_endpoint_ip?: string | null;
  config: Record<string, unknown> | null;
}

export interface TopologyLinkCreate {
  source_node_id: string;
  target_node_id: string;
  network_name: string;
  cidr?: string | null;
  gateway?: string | null;
  vlan_tag?: number | null;
  source_endpoint_ip?: string | null;
  target_endpoint_ip?: string | null;
  config?: Record<string, unknown> | null;
}

/** Persisted in `TopologyNode.config.editor_position` for React Flow layout. */
export interface EditorPosition {
  x: number;
  y: number;
}

export interface TopologyUpdate {
  name?: string;
  description?: string | null;
  status?: TopologyStatus;
  runtime_target?: string;
  networking_mode?: string;
  config?: Record<string, unknown> | null;
}

export interface TopologyNodeUpdate {
  name?: string;
  node_type?: NodeType;
  image?: string | null;
  ip_address?: string | null;
  config?: Record<string, unknown> | null;
}

export interface TopologyLinkUpdate {
  network_name?: string;
  cidr?: string | null;
  gateway?: string | null;
  vlan_tag?: number | null;
  source_endpoint_ip?: string | null;
  target_endpoint_ip?: string | null;
  config?: Record<string, unknown> | null;
}

export const EDITOR_POSITION_KEY = 'editor_position' as const;
