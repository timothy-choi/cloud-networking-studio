import type { TrafficTestResponse } from '../types/traffic';
import type { FailureInjectionResponse } from '../types/failure';
import { apiFetch } from './client';
import type {
  TopologyCreate,
  TopologyLinkCreate,
  TopologyLinkResponse,
  TopologyLinkUpdate,
  TopologyNodeCreate,
  TopologyNodeResponse,
  TopologyNodeUpdate,
  TopologyResponse,
  TopologyUpdate,
} from '../types/topology';
import type { RuntimeTopologyResponse } from '../types/runtime';

export async function listTopologies(): Promise<TopologyResponse[]> {
  return apiFetch<TopologyResponse[]>('/topologies');
}

export async function getTopology(topologyId: string): Promise<TopologyResponse> {
  return apiFetch<TopologyResponse>(`/topologies/${topologyId}`);
}

export async function createTopology(body: TopologyCreate): Promise<TopologyResponse> {
  return apiFetch<TopologyResponse>('/topologies', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listNodes(topologyId: string): Promise<TopologyNodeResponse[]> {
  return apiFetch<TopologyNodeResponse[]>(`/topologies/${topologyId}/nodes`);
}

export async function createNode(
  topologyId: string,
  body: TopologyNodeCreate,
): Promise<TopologyNodeResponse> {
  return apiFetch<TopologyNodeResponse>(`/topologies/${topologyId}/nodes`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listLinks(topologyId: string): Promise<TopologyLinkResponse[]> {
  return apiFetch<TopologyLinkResponse[]>(`/topologies/${topologyId}/links`);
}

export async function createLink(
  topologyId: string,
  body: TopologyLinkCreate,
): Promise<TopologyLinkResponse> {
  return apiFetch<TopologyLinkResponse>(`/topologies/${topologyId}/links`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getTopologyRuntime(topologyId: string): Promise<RuntimeTopologyResponse> {
  return apiFetch<RuntimeTopologyResponse>(`/topologies/${topologyId}/runtime`);
}

export async function listTopologyTrafficTests(topologyId: string): Promise<TrafficTestResponse[]> {
  return apiFetch<TrafficTestResponse[]>(`/topologies/${topologyId}/traffic-tests`);
}

export async function listTopologyFailures(topologyId: string): Promise<FailureInjectionResponse[]> {
  return apiFetch<FailureInjectionResponse[]>(`/topologies/${topologyId}/failures`);
}

export async function runPingTest(
  topologyId: string,
  body: { source_node_id: string; target_node_id: string; count?: number },
): Promise<TrafficTestResponse> {
  return apiFetch<TrafficTestResponse>(`/topologies/${topologyId}/traffic-tests/ping`, {
    method: 'POST',
    body: JSON.stringify({
      source_node_id: body.source_node_id,
      target_node_id: body.target_node_id,
      count: body.count ?? 3,
    }),
  });
}

export async function runHttpTest(
  topologyId: string,
  body: { source_node_id: string; target_node_id: string; path?: string; port?: number },
): Promise<TrafficTestResponse> {
  return apiFetch<TrafficTestResponse>(`/topologies/${topologyId}/traffic-tests/http`, {
    method: 'POST',
    body: JSON.stringify({
      source_node_id: body.source_node_id,
      target_node_id: body.target_node_id,
      path: body.path ?? '/',
      port: body.port ?? 80,
    }),
  });
}

export async function injectStopNode(
  topologyId: string,
  body: { target_node_id: string; description?: string | null },
): Promise<unknown> {
  return apiFetch(`/topologies/${topologyId}/failures/stop-node`, {
    method: 'POST',
    body: JSON.stringify({
      target_node_id: body.target_node_id,
      description: body.description ?? null,
    }),
  });
}

export async function patchTopology(topologyId: string, body: TopologyUpdate): Promise<TopologyResponse> {
  return apiFetch<TopologyResponse>(`/topologies/${topologyId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function patchNode(
  topologyId: string,
  nodeId: string,
  body: TopologyNodeUpdate,
): Promise<TopologyNodeResponse> {
  return apiFetch<TopologyNodeResponse>(`/topologies/${topologyId}/nodes/${nodeId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteNode(topologyId: string, nodeId: string): Promise<void> {
  await apiFetch(`/topologies/${topologyId}/nodes/${nodeId}`, {
    method: 'DELETE',
  });
}

export async function patchLink(
  topologyId: string,
  linkId: string,
  body: TopologyLinkUpdate,
): Promise<TopologyLinkResponse> {
  return apiFetch<TopologyLinkResponse>(`/topologies/${topologyId}/links/${linkId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteLink(topologyId: string, linkId: string): Promise<void> {
  await apiFetch(`/topologies/${topologyId}/links/${linkId}`, {
    method: 'DELETE',
  });
}

/**
 * Creates a lab topology matching `scripts/demo_full_flow.sh` naming (host-a, service-b + random /24).
 * Returns the new topology id for navigation.
 */
export async function createDemoTopology(): Promise<{ topologyId: string }> {
  const tag = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
  const thirdOctet = 80 + Math.floor(Math.random() * 120);
  const cidr = `10.${thirdOctet}.0.0/24`;
  const hostIp = `10.${thirdOctet}.0.10`;
  const svcIp = `10.${thirdOctet}.0.20`;

  const topo = await createTopology({
    name: `CNS UI Demo ${tag}`,
    description: `frontend demo ${tag}`,
    runtime_target: 'docker',
    networking_mode: 'docker_bridge',
    status: 'draft',
    config: null,
  });

  const host = await createNode(topo.id, {
    name: 'host-a',
    node_type: 'host',
    image: 'alpine:latest',
    ip_address: hostIp,
    config: null,
  });

  const svc = await createNode(topo.id, {
    name: 'service-b',
    node_type: 'generic',
    image: 'nginx:alpine',
    ip_address: svcIp,
    config: null,
  });

  await createLink(topo.id, {
    source_node_id: host.id,
    target_node_id: svc.id,
    network_name: `demo-net-${thirdOctet}`,
    cidr,
    config: null,
  });

  return { topologyId: topo.id };
}
