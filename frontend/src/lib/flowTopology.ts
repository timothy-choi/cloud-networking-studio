import { MarkerType as MT } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';

import { deploymentWorkloadLive } from './runtimeHealth';
import type { RuntimeTopologyResponse } from '../types/runtime';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../types/topology';
import { EDITOR_POSITION_KEY } from '../types/topology';

export type FlowWorkloadStatus = 'running' | 'stopped' | 'unknown';

/** Visual treatment for control-plane style graph nodes. */
export type NodeVisualState = 'running' | 'stopped' | 'unknown' | 'transition';

export interface CnsFlowNodeData extends Record<string, unknown> {
  topologyNodeId: string;
  title: string;
  subtitle: string;
  intentIp: string | null;
  runtimeIp: string | null;
  /** Docker / provider status string */
  statusLabel: string;
  visual: NodeVisualState;
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

export function deriveNodeRuntimePresentation(
  nodeId: string,
  runtime: RuntimeTopologyResponse | null,
  controllerBusy: string | null,
): Pick<CnsFlowNodeData, 'visual' | 'statusLabel' | 'runtimeIp' | 'workload' | 'degraded'> {
  const wl = nodeWorkloadFromRuntime(nodeId, runtime);
  const rip = runtimePrimaryIp(nodeId, runtime);
  const c = runtime?.containers?.find((x) => x.node_id === nodeId);
  const ds = runtime?.deployment_status ?? null;
  const inDeploy = ds === 'pending' || ds === 'provisioning';
  const busyOps = controllerBusy === 'reconcile' || controllerBusy === 'heal' || controllerBusy === 'deploy';

  const rawStatus = c
    ? String(c.state_status ?? c.status ?? (c.running ? 'running' : 'exited'))
    : inDeploy
      ? 'provisioning'
      : 'not deployed';

  if (c && !c.running) {
    return {
      visual: 'stopped',
      statusLabel: rawStatus,
      runtimeIp: rip,
      workload: 'stopped',
      degraded: true,
    };
  }

  if (c?.running) {
    if (inDeploy || busyOps) {
      return {
        visual: 'transition',
        statusLabel: busyOps ? `${rawStatus} · ${controllerBusy}…` : rawStatus,
        runtimeIp: rip,
        workload: 'running',
        degraded: false,
      };
    }
    return {
      visual: 'running',
      statusLabel: rawStatus,
      runtimeIp: rip,
      workload: 'running',
      degraded: false,
    };
  }

  if (inDeploy) {
    return {
      visual: 'transition',
      statusLabel: 'awaiting workload',
      runtimeIp: null,
      workload: 'unknown',
      degraded: false,
    };
  }

  if (busyOps) {
    return {
      visual: 'transition',
      statusLabel: controllerBusy ?? 'activity',
      runtimeIp: rip,
      workload: wl,
      degraded: false,
    };
  }

  return {
    visual: 'unknown',
    statusLabel: rawStatus,
    runtimeIp: rip,
    workload: wl,
    degraded: false,
  };
}

export function topologyNodesToFlowNodes(
  nodes: TopologyNodeResponse[],
  runtime: RuntimeTopologyResponse | null,
  controllerBusy: string | null = null,
): Node<CnsFlowNodeData>[] {
  const n = nodes.length;
  const radius = 240;
  return nodes.map((node, i) => {
    const pos = readEditorPosition(node.config);
    const angle = (2 * Math.PI * i) / Math.max(n, 1);
    const defaultPos = {
      x: 300 + radius * Math.cos(angle),
      y: 260 + radius * Math.sin(angle),
    };
    const pres = deriveNodeRuntimePresentation(node.id, runtime, controllerBusy);
    return {
      id: node.id,
      type: 'cnsEditor',
      position: pos ?? defaultPos,
      data: {
        topologyNodeId: node.id,
        title: node.name,
        subtitle: node.node_type,
        intentIp: node.ip_address,
        runtimeIp: pres.runtimeIp,
        statusLabel: pres.statusLabel,
        visual: pres.visual,
        workload: pres.workload,
        degraded: pres.degraded,
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
    markerEnd: { type: MT.ArrowClosed, color: animate ? '#34d399' : '#94a3b8' },
    style: {
      stroke: animate ? '#34d399' : '#64748b',
      strokeWidth: animate ? 2.25 : 2,
    },
    labelStyle: { fill: '#cbd5e1', fontSize: 12, fontWeight: 500 },
    labelBgStyle: { fill: '#0f172a', fillOpacity: 0.92 },
    labelBgPadding: [6, 4] as [number, number],
  }));
}

/** Simple grid layout — deterministic positions for auto-layout. */
export function gridPositions(
  ids: string[],
  cols = 4,
  cellX = 300,
  cellY = 210,
): Record<string, { x: number; y: number }> {
  const map: Record<string, { x: number; y: number }> = {};
  ids.forEach((id, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    map[id] = { x: 90 + col * cellX, y: 90 + row * cellY };
  });
  return map;
}
