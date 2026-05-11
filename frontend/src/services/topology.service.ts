import * as topoApi from '../api/topologies';
import type { TopologyLinkResponse, TopologyNodeResponse, TopologyResponse } from '../types/topology';
import type { RuntimeTopologyResponse } from '../types/runtime';

export interface TopologyDetailBundle {
  topology: TopologyResponse;
  nodes: TopologyNodeResponse[];
  links: TopologyLinkResponse[];
  runtime: RuntimeTopologyResponse;
}

export async function loadTopologyDetail(topologyId: string): Promise<TopologyDetailBundle> {
  const [topology, nodes, links, runtime] = await Promise.all([
    topoApi.getTopology(topologyId),
    topoApi.listNodes(topologyId),
    topoApi.listLinks(topologyId),
    topoApi.getTopologyRuntime(topologyId),
  ]);
  return { topology, nodes, links, runtime };
}

export { createDemoTopology } from '../api/topologies';
