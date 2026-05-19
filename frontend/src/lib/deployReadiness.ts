import type { NetworkAllocationMode } from './networkAllocation';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export interface DeployReadiness {
  /** False when the API would reject deploy (validation / duplicate active deploy is server-side only). */
  deployable: boolean;
  blockingReasons: string[];
  warnings: string[];
}

/** Undirected connected components among persisted nodes using links as edges. */
export function topologyLinkComponentCount(nodeIds: string[], links: TopologyLinkResponse[]): number {
  if (nodeIds.length === 0) return 0;
  const idSet = new Set(nodeIds);
  const adj = new Map<string, string[]>();
  for (const id of nodeIds) adj.set(id, []);
  for (const l of links) {
    if (!idSet.has(l.source_node_id) || !idSet.has(l.target_node_id)) continue;
    adj.get(l.source_node_id)!.push(l.target_node_id);
    adj.get(l.target_node_id)!.push(l.source_node_id);
  }
  const seen = new Set<string>();
  let comps = 0;
  for (const id of nodeIds) {
    if (seen.has(id)) continue;
    comps += 1;
    const stack = [id];
    seen.add(id);
    while (stack.length) {
      const u = stack.pop()!;
      for (const v of adj.get(u) ?? []) {
        if (!seen.has(v)) {
          seen.add(v);
          stack.push(v);
        }
      }
    }
  }
  return comps;
}

function isSegmentedMultinet(links: TopologyLinkResponse[]): boolean {
  if (links.length <= 1) return false;
  const names = new Set(links.map((l) => l.network_name));
  return names.size > 1;
}

/**
 * Client-side checks aligned with backend `validate_topology_for_deploy`
 * (duplicate IPs, islands, segmented CIDR / router rules). Warnings are UX-only.
 */
export function computeDeployReadiness(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
  networkAllocationMode: NetworkAllocationMode = 'managed',
): DeployReadiness {
  const blockingReasons: string[] = [];
  const warnings: string[] = [];
  const segmented = isSegmentedMultinet(links);

  if (nodes.length === 0) {
    blockingReasons.push('Add at least one node before runtime deploy.');
  }
  if (nodes.length > 1 && links.length === 0) {
    blockingReasons.push('Multi-node topology needs at least one link before deploy.');
  }

  if (nodes.length > 1 && links.length > 0) {
    for (const n of nodes) {
      if (!(n.ip_address ?? '').trim()) {
        blockingReasons.push(
          `Node “${n.name}” is missing an intent IP — required when multiple nodes are linked (set in the inspector).`,
        );
      }
    }
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
      if (segmented) {
        blockingReasons.push('Segmented multi-network mode requires a CIDR on every link.');
      } else {
        warnings.push(
          networkAllocationMode === 'intent'
            ? 'One or more links have no subnet CIDR — required for intent networking.'
            : 'One or more links have no subnet CIDR — optional in managed mode; add CIDRs to document your lab design.',
        );
      }
    }
  }

  if (nodes.length > 1 && links.length > 0) {
    const comps = topologyLinkComponentCount(
      nodes.map((n) => n.id),
      links,
    );
    if (comps > 1) {
      blockingReasons.push(
        `Topology graph has ${comps} disconnected islands — connect every node with links.`,
      );
    }
  }

  if (segmented) {
    const deg = (nid: string) =>
      links.filter((l) => l.source_node_id === nid || l.target_node_id === nid).length;
    for (const n of nodes) {
      if (n.node_type === 'router' && deg(n.id) < 2) {
        blockingReasons.push(
          `Router “${n.name}” must participate in at least two links for multi-segment routing.`,
        );
      }
    }
  }

  return {
    deployable: blockingReasons.length === 0,
    blockingReasons,
    warnings,
  };
}

export type IntentBadgeTone = 'neutral' | 'warn' | 'ok' | 'live' | 'bad';

export interface IntentBadge {
  id: string;
  label: string;
  tone: IntentBadgeTone;
}

/** Compact labels for the deployment sidebar (draft / gaps / deployable / deployed). */
export function computeIntentBadges(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
  topologyStatus: string | null | undefined,
  deploymentStatus: string | null | undefined,
): IntentBadge[] {
  const badges: IntentBadge[] = [];
  const st = (topologyStatus ?? 'draft').toLowerCase();
  if (st === 'draft') badges.push({ id: 'draft', label: 'Draft', tone: 'neutral' });
  else if (st === 'active') badges.push({ id: 'active', label: 'Active', tone: 'live' });
  else badges.push({ id: 'arch', label: 'Archived', tone: 'bad' });

  if (nodes.length > 1 && links.length === 0) {
    badges.push({ id: 'm-links', label: 'Missing links', tone: 'warn' });
  }
  const missingIp =
    nodes.length > 1 && links.length > 0 && nodes.some((n) => !(n.ip_address ?? '').trim());
  if (missingIp) {
    badges.push({ id: 'm-ip', label: 'Missing IPs', tone: 'warn' });
  }

  const r = computeDeployReadiness(nodes, links);
  const ds = deploymentStatus ?? null;
  if (ds === 'succeeded') {
    badges.push({ id: 'dep-ok', label: 'Deployed', tone: 'live' });
  } else if (ds === 'deploying' || ds === 'pending' || ds === 'stopping') {
    badges.push({
      id: 'dep-run',
      label: ds === 'deploying' ? 'Deploying…' : ds === 'pending' ? 'Deploy pending' : 'Stopping…',
      tone: 'live',
    });
  } else if (r.deployable) {
    badges.push({ id: 'go', label: 'Deployable', tone: 'ok' });
  } else {
    badges.push({ id: 'block', label: 'Not deployable', tone: 'bad' });
  }

  return badges;
}
