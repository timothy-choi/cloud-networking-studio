import '@xyflow/react/dist/style.css';
import { useEffect, useMemo } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  MarkerType,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from '@xyflow/react';

import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/api';

interface TopologyGraphProps {
  nodes: TopologyNodeResponse[];
  links: TopologyLinkResponse[];
}

export function TopologyGraph({ nodes: topoNodes, links }: TopologyGraphProps) {
  const initialNodes = useMemo(() => {
    const n = topoNodes.length;
    return topoNodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(n, 1);
      const radius = 160;
      const x = 240 + radius * Math.cos(angle);
      const y = 200 + radius * Math.sin(angle);
      const lines = [
        node.name,
        node.node_type,
        node.ip_address ? node.ip_address : undefined,
      ].filter(Boolean);
      return {
        id: node.id,
        position: { x, y },
        data: {
          label: lines.join('\n'),
        },
      };
    }) satisfies Node[];
  }, [topoNodes]);

  const initialEdges = useMemo(
    () =>
      links.map((link) => ({
        id: link.id,
        source: link.source_node_id,
        target: link.target_node_id,
        label: link.cidr ?? link.network_name,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#71717a' },
        style: { stroke: '#71717a', strokeWidth: 1.5 },
      })) satisfies Edge[],
    [links],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  if (topoNodes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-100/60 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-400">
        No nodes in this topology yet.
      </div>
    );
  }

  return (
    <div className="h-[440px] w-full overflow-hidden rounded-lg border border-zinc-200 bg-zinc-950 shadow-inner dark:border-zinc-700">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={18} size={1} color="#3f3f46" />
        <Controls
          className="rounded border border-zinc-600 bg-zinc-900 shadow-lg [&_button]:border-zinc-600 [&_button]:bg-zinc-800 [&_button]:fill-zinc-200 [&_button:hover]:bg-zinc-700"
          showInteractive={false}
        />
        <MiniMap
          className="rounded border border-zinc-600 bg-zinc-900/95 shadow-lg"
          maskColor="rgba(24,24,27,0.85)"
          nodeColor={() => '#52525b'}
        />
      </ReactFlow>
    </div>
  );
}
