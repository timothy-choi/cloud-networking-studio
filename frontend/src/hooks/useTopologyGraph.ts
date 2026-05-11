import { useMemo } from 'react';

import { topologyLinksToFlowEdges, topologyNodesToFlowNodes } from '../lib/flowTopology';
import type { RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export function useTopologyGraph(
  nodes: TopologyNodeResponse[],
  links: TopologyLinkResponse[],
  runtime: RuntimeTopologyResponse | null,
) {
  return useMemo(
    () => ({
      flowNodes: topologyNodesToFlowNodes(nodes, runtime),
      flowEdges: topologyLinksToFlowEdges(links, runtime?.deployment_status ?? null),
    }),
    [nodes, links, runtime],
  );
}
