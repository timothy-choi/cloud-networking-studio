import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export interface DeployReadiness {
  /** False when the API would reject deploy (validation / duplicate active deploy is server-side only). */
  deployable: boolean;
  blockingReasons: string[];
  warnings: string[];
}

/**
 * Client-side checks aligned with backend `validate_topology_for_deploy`
 * (duplicate IPs, nodes, multi-node links). Warnings are UX-only.
 */
export function computeDeployReadiness(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
): DeployReadiness {
  const blockingReasons: string[] = [];
  const warnings: string[] = [];

  if (nodes.length === 0) {
    blockingReasons.push('Add at least one node before runtime deploy.');
  }
  if (nodes.length > 1 && links.length === 0) {
    blockingReasons.push('Multi-node topology needs at least one link before deploy.');
  }

  const trimmedIps = nodes.map((n) => (n.ip_address ?? '').trim()).filter(Boolean);
  const counts = new Map<string, number>();
  for (const ip of trimmedIps) {
    counts.set(ip, (counts.get(ip) ?? 0) + 1);
  }
  const dupIps = [...counts.entries()].filter(([, c]) => c > 1).map(([ip]) => ip);
  if (dupIps.length) {
    blockingReasons.push(`Duplicate intent IP addresses: ${dupIps.join(', ')}.`);
  }

  for (const n of nodes) {
    if (!(n.image ?? '').trim()) {
      warnings.push(`Node “${n.name}” has no container image — set one before deploy.`);
    }
  }

  if (nodes.length > 1) {
    const linksMissingCidr = links.filter((l) => !(l.cidr ?? '').trim());
    if (linksMissingCidr.length > 0) {
      warnings.push(
        'One or more links have no subnet CIDR — add CIDRs so intent IPs can be validated against a lab subnet.',
      );
    }
  }

  return {
    deployable: blockingReasons.length === 0,
    blockingReasons,
    warnings,
  };
}
