import { memo, useEffect, useMemo } from 'react';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';

import { deploymentWorkloadLive, nodeWorkloadStatus } from '../lib/runtimeHealth';
import type { RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';

export type CnsNodeData = {
  title: string;
  subtitle: string;
  ip: string | null;
  status: 'running' | 'stopped' | 'unknown';
};

const CnsGraphNode = memo(function CnsGraphNode({ data }: NodeProps<Node<CnsNodeData>>) {
  const ring =
    data.status === 'running'
      ? 'shadow-emerald-500/20 ring-emerald-500/60'
      : data.status === 'stopped'
        ? 'shadow-red-500/25 ring-red-500/70'
        : 'ring-zinc-600';

  return (
    <div className={`min-w-[150px] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 shadow-xl ring-2 ${ring}`}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-zinc-500 !bg-zinc-600" />
      <div className="text-[13px] font-semibold leading-tight text-zinc-50">{data.title}</div>
      <div className="text-[10px] uppercase tracking-wide text-cns-graph-secondary">{data.subtitle}</div>
      {data.ip ? <div className="mt-1 font-mono text-[11px] text-emerald-400/95">{data.ip}</div> : null}
      <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-cns-graph-mono">{data.status}</div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-zinc-500 !bg-zinc-600" />
    </div>
  );
});

const nodeTypes = { cnsNode: CnsGraphNode };

interface TopologyGraphProps {
  nodes: TopologyNodeResponse[];
  links: TopologyLinkResponse[];
  runtime: RuntimeTopologyResponse | null;
}

export function TopologyGraph({ nodes: topoNodes, links, runtime }: TopologyGraphProps) {
  const deploymentStatus = runtime?.deployment_status ?? null;
  const animateEdges = deploymentWorkloadLive(deploymentStatus);

  const initialNodes = useMemo(() => {
    const n = topoNodes.length;
    return topoNodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(n, 1);
      const radius = 175;
      const x = 260 + radius * Math.cos(angle);
      const y = 220 + radius * Math.sin(angle);
      const ws = nodeWorkloadStatus(node.id, runtime);
      return {
        id: node.id,
        type: 'cnsNode',
        position: { x, y },
        data: {
          title: node.name,
          subtitle: node.node_type,
          ip: node.ip_address,
          status: ws,
        },
      } satisfies Node<CnsNodeData>;
    });
  }, [topoNodes, runtime]);

  const initialEdges = useMemo(
    () =>
      links.map((link) => ({
        id: link.id,
        source: link.source_node_id,
        target: link.target_node_id,
        label: link.cidr ?? link.network_name,
        animated: animateEdges,
        markerEnd: { type: MarkerType.ArrowClosed, color: animateEdges ? '#34d399' : '#71717a' },
        style: {
          stroke: animateEdges ? '#34d399' : '#52525b',
          strokeWidth: animateEdges ? 2 : 1.5,
        },
        labelStyle: { fill: '#d4d4d8', fontSize: 11 },
      })) satisfies Edge[],
    [links, animateEdges],
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
      <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-100/60 px-4 py-10 text-center text-sm text-cns-muted dark:border-zinc-700 dark:bg-zinc-900/40">
        No nodes in this topology yet.
      </div>
    );
  }

  return (
    <div className="h-[460px] w-full overflow-hidden rounded-lg border border-zinc-200 bg-zinc-950 shadow-inner dark:border-zinc-700">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
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
          nodeColor={(n) => (n.type === 'cnsNode' ? '#059669' : '#52525b')}
        />
      </ReactFlow>
    </div>
  );
}
