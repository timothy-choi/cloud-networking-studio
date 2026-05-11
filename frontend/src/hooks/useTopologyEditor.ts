import { useCallback, useState } from 'react';

import type { Edge, Node } from '@xyflow/react';

/** Selection wiring for React Flow editors (single node or edge). */
export function useTopologyEditor() {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const onSelectionChange = useCallback(
    ({ nodes: sn, edges: se }: { nodes: Node[]; edges: Edge[] }) => {
      setSelectedNodeId(sn.length === 1 ? sn[0].id : null);
      setSelectedEdgeId(se.length === 1 ? se[0].id : null);
    },
    [],
  );

  const clearSelection = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  return {
    selectedNodeId,
    selectedEdgeId,
    setSelectedNodeId,
    setSelectedEdgeId,
    onSelectionChange,
    clearSelection,
  };
}
