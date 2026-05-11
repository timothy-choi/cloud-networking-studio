import { MarkerType as MT } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';

import { deploymentWorkloadLive } from './runtimeHealth';
import type { RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';
import { EDITOR_POSITION_KEY } from '../types/topology';

export type FlowWorkloadStatus = 'running' | 'stopped' | 'unknown';

export interface CnsFlowNodeData extends Record<string, unknown> {
  topologyNodeId: string;
  title: string;
  subtitle: string;
  intentIp: string | null;
  runtimeIp: string | null;
  workload: FlowWorkloadStatus;
  degraded: boolean;
}

export function readEditorPosition(config: Record<string, unknown> | null): { x: number; y: number } | null {
  if (!config || typeof config !== 'object') return null;
  const raw = config[EDITOR_POSITION_KEY];
  if (!raw || typeof raw !== 'object') return null;
  const x = (raw as { x?: unknown }).x;
  const y = (raw as { y?: unknown }).y;
  if (typeof x !== 'number' || typeof y !== 'number') return null;
  return { x, y };
}

export function nodeWorkloadFromRuntime(
  nodeId: string,
  runtime: RuntimeTopologyResponse | null,
): FlowWorkloadStatus {
  if (!runtime?.containers?.length) return 'unknown';
  const c = runtime.containers.find((x) => x.node_id === nodeId);
  if (!c) return 'unknown';
  return c.running ? 'running' : 'stopped';
}

export function runtimePrimaryIp(nodeId: string, runtime: RuntimeTopologyResponse | null): string | null {
  if (!runtime?.containers?.length) return null;
  const c = runtime.containers.find((x) => x.node_id === nodeId);
  if (!c?.ipv4_by_network) return null;
  const vals = Object.values(c.ipv4_by_network);
  return vals[0] ?? null;
}

export function topologyNodesToFlowNodes(
  nodes: TopologyNodeResponse[],
  runtime: RuntimeTopologyResponse | null,
): Node<CnsFlowNodeData>[] {
  const n = nodes.length;
  return nodes.map((node, i) => {
    const pos = readEditorPosition(node.config);
    const angle = (2 * Math.PI * i) / Math.max(n, 1);
    const radius = 200;
    const defaultPos = {
      x: 280 + radius * Math.cos(angle),
      y: 240 + radius * Math.sin(angle),
    };
    const wl = nodeWorkloadFromRuntime(node.id, runtime);
    const rip = runtimePrimaryIp(node.id, runtime);
    const degraded = wl === 'stopped';
    return {
      id: node.id,
      type: 'cnsEditor',
      position: pos ?? defaultPos,
      data: {
        topologyNodeId: node.id,
        title: node.name,
        subtitle: node.node_type,
        intentIp: node.ip_address,
        runtimeIp: rip,
        workload: wl,
        degraded,
      },
    };
  });
}

export function topologyLinksToFlowEdges(
  links: TopologyLinkResponse[],
  deploymentStatus: RuntimeTopologyResponse['deployment_status'],
): Edge[] {
  const animate = deploymentWorkloadLive(deploymentStatus ?? null);
  return links.map((link) => ({
    id: link.id,
    source: link.source_node_id,
    target: link.target_node_id,
    label: link.cidr ?? link.network_name,
    type: 'smoothstep',
    animated: animate,
    markerEnd: { type: MT.ArrowClosed, color: animate ? '#34d399' : '#71717a' },
    style: {
      stroke: animate ? '#34d399' : '#64748b',
      strokeWidth: animate ? 2 : 1.5,
    },
    labelStyle: { fill: '#94a3b8', fontSize: 11 },
    labelBgStyle: { fill: '#0f172a', fillOpacity: 0.85 },
  }));
}

/** Simple grid layout — deterministic positions for auto-layout. */
export function gridPositions(
  ids: string[],
  cols = 3,
  cellX = 260,
  cellY = 180,
): Record<string, { x: number; y: number }> {
  const map: Record<string, { x: number; y: number }> = {};
  ids.forEach((id, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    map[id] = { x: 80 + col * cellX, y: 80 + row * cellY };
  });
  return map;
}
