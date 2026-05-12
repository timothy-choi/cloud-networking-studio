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
  const inDeploy = ds === 'pending' || ds === 'deploying' || ds === 'stopping';
  const busyOps = controllerBusy === 'reconcile' || controllerBusy === 'heal' || controllerBusy === 'deploy';

  const rawStatus = c
    ? String(c.state_status ?? c.status ?? (c.running ? 'running' : 'exited'))
    : inDeploy
      ? 'deploying'
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

/** Edge / inspector label: logical net, subnet, optional gateway and VLAN. */
export function formatLinkEdgeLabel(link: TopologyLinkResponse): string {
  const lines: string[] = [link.network_name];
  const c = (link.cidr ?? '').trim();
  if (c) lines.push(c);
  const gw = (link.gateway ?? '').trim();
  if (gw) lines.push(`gw ${gw}`);
  if (link.vlan_tag != null && link.vlan_tag !== undefined) lines.push(`vlan ${link.vlan_tag}`);
  return lines.join('\n');
}

/** Stub link row for building a React Flow edge before the API returns a persisted id. */
export function stubLinkForFlow(
  id: string,
  sourceId: string,
  targetId: string,
  networkName: string,
  cidr: string | null,
): TopologyLinkResponse {
  return {
    id,
    topology_id: '',
    source_node_id: sourceId,
    target_node_id: targetId,
    network_name: networkName,
    cidr,
    gateway: null,
    vlan_tag: null,
    source_endpoint_ip: null,
    target_endpoint_ip: null,
    config: null,
  };
}

/** Next 10.x.0.0/24 for lab links — scans existing CIDRs and picks a free-ish octet (200–240). */
export function pickNextLinkCidr(links: TopologyLinkResponse[]): string {
  const re = /^10\.(\d+)\.0\.0\/24$/;
  let maxOct = 199;
  for (const l of links) {
    const c = l.cidr?.trim();
    if (!c) continue;
    const m = re.exec(c);
    if (m) {
      const n = Number(m[1]);
      if (Number.isFinite(n)) maxOct = Math.max(maxOct, n);
    }
  }
  const next = Math.min(Math.max(maxOct + 1, 200), 240);
  return `10.${next}.0.0/24`;
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
    label: formatLinkEdgeLabel(link),
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
