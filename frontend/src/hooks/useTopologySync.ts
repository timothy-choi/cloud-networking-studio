import { useMemo } from 'react';

import { topologySignature } from '../lib/topologySignature';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export function useTopologySync(nodes: TopologyNodeResponse[], links: TopologyLinkResponse[]) {
  const sig = useMemo(() => topologySignature(nodes, links), [nodes, links]);
  return { sig };
}
