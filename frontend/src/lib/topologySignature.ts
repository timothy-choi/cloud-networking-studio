import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

/** Stable fingerprint of persisted topology graph for React Flow resync. */
export function topologySignature(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
): string {
  const ns = nodes
    .map(
      (n) =>
        `${n.id}:${n.name}:${n.node_type}:${n.image ?? ''}:${n.ip_address ?? ''}:${JSON.stringify(n.config ?? {})}`,
    )
    .sort()
    .join('|');
  const ls = links
    .map(
      (l) =>
        `${l.id}:${l.source_node_id}:${l.target_node_id}:${l.network_name}:${l.cidr ?? ''}:${l.gateway ?? ''}:${l.vlan_tag ?? ''}:${l.source_endpoint_ip ?? ''}:${l.target_endpoint_ip ?? ''}`,
    )
    .sort()
    .join('|');
  return `${ns}__${ls}`;
}
