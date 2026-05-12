import type { TrafficTestResponse } from '../types/traffic';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export interface RoutedLabRoles {
  host: TopologyNodeResponse | null;
  router: TopologyNodeResponse | null;
  service: TopologyNodeResponse | null;
  /** Host + router + service with ≥2 distinct link networks and router on ≥1 link. */
  isRoutedLike: boolean;
}

/**
 * Heuristic for “routed lab” UX (template + manual designs): host, router, generic service,
 * multiple L2 segments, router participates in the graph.
 */
export function inferRoutedLabRoles(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
): RoutedLabRoles {
  const host = nodes.find((n) => n.node_type === 'host') ?? null;
  const router = nodes.find((n) => n.node_type === 'router') ?? null;
  const service = nodes.find((n) => n.node_type === 'generic') ?? null;
  const distinctNets = new Set(links.map((l) => l.network_name.trim()).filter(Boolean));
  const routerTouched = links.some(
    (l) => l.source_node_id === router?.id || l.target_node_id === router?.id,
  );
  const isRoutedLike = Boolean(
    host && router && service && links.length >= 2 && distinctNets.size >= 2 && routerTouched,
  );
  return { host, router, service, isRoutedLike };
}

/** Latest traffic test for a directed pair (by `created_at`). */
export function latestTrafficBetweenSorted(
  tests: TrafficTestResponse[],
  sourceId: string,
  targetId: string,
  type: 'ping' | 'http',
): TrafficTestResponse | null {
  const hits = tests.filter(
    (t) =>
      t.test_type === type &&
      t.source_node_id === sourceId &&
      t.target_node_id === targetId,
  );
  if (!hits.length) return null;
  return [...hits].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] ?? null;
}

export function scanDeploymentEventsForRoutedIssues(messages: string[]): {
  leafRouteValidationFailed: boolean;
  dot254Gateway: boolean;
  netAdminOrCapHint: boolean;
  routeTableMismatchHint: boolean;
} {
  let leafRouteValidationFailed = false;
  let dot254Gateway = false;
  let netAdminOrCapHint = false;
  let routeTableMismatchHint = false;
  for (const raw of messages) {
    const m = raw.toLowerCase();
    if (m.includes('leaf route validation failed')) leafRouteValidationFailed = true;
    if (m.includes('*.254') || m.includes('10.72.0.254') || m.includes('10.73.0.254')) dot254Gateway = true;
    if (
      m.includes('route table mismatch') ||
      (m.includes('mismatch') && (m.includes('route') || m.includes('routing table')))
    ) {
      routeTableMismatchHint = true;
    }
    if (
      m.includes('net_admin') ||
      m.includes('cap_add') ||
      (m.includes('operation not permitted') && m.includes('route')) ||
      m.includes('requires cap_net_admin')
    ) {
      netAdminOrCapHint = true;
    }
  }
  return { leafRouteValidationFailed, dot254Gateway, netAdminOrCapHint, routeTableMismatchHint };
}
