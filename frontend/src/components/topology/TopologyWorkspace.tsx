import type { Connection, Edge, Node } from '@xyflow/react';
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  Handle,
  type NodeProps,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { formatApiError } from '../../api/client';
import { deployTopology } from '../../api/deployments';
import * as topoApi from '../../api/topologies';
import { useTopologyEditor } from '../../hooks/useTopologyEditor';
import { useTopologySync } from '../../hooks/useTopologySync';
import { TopologyStudioLayout } from '../../layouts/TopologyStudioLayout';
import {
  type CnsFlowNodeData,
  deriveNodeRuntimePresentation,
  gridPositions,
  readEditorPosition,
  topologyLinksToFlowEdges,
  topologyNodesToFlowNodes,
} from '../../lib/flowTopology';
import type { RuntimeTopologyResponse } from '../../types/runtime';
import type {
  TopologyLinkResponse,
  TopologyNodeResponse,
  TopologyResponse,
} from '../../types/topology';
import { EDITOR_POSITION_KEY } from '../../types/topology';
import { DeploymentPlanningPanel } from './DeploymentPlanningPanel';
import { TopologyInspector } from './TopologyInspector';
import { TopologyToolbar } from './TopologyToolbar';
import { applyTopologyTemplate, resetTopologyToDemoLab } from './templates';

const CnsEditorNode = memo(function CnsEditorNode({
  data,
  selected,
}: NodeProps<Node<CnsFlowNodeData>>) {
  const v = data.visual;
  const accent =
    selected
      ? 'ring-2 ring-sky-400 ring-offset-2 ring-offset-zinc-950'
      : v === 'running'
        ? 'shadow-[0_0_26px_rgba(34,197,94,0.38)] ring-1 ring-emerald-500/75'
        : v === 'stopped'
          ? 'shadow-[0_0_28px_rgba(239,68,68,0.48)] ring-1 ring-red-500/80'
          : v === 'transition'
            ? 'shadow-[0_0_24px_rgba(245,158,11,0.42)] ring-1 ring-amber-400/75'
            : 'ring-1 ring-zinc-600';

  return (
    <div
      className={`min-w-[200px] max-w-[280px] rounded-xl border border-zinc-700/90 bg-zinc-950/95 px-4 py-3 shadow-xl backdrop-blur-sm ${accent}`}
    >
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-zinc-500 !bg-zinc-700" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold leading-snug tracking-tight text-zinc-50">{data.title}</div>
          <div className="mt-0.5 text-[11px] font-semibold uppercase tracking-wide text-cns-graph-secondary">{data.subtitle}</div>
        </div>
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${
            v === 'running'
              ? 'bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)]'
              : v === 'stopped'
                ? 'bg-red-500 shadow-[0_0_10px_rgba(248,113,113,0.9)]'
                : v === 'transition'
                  ? 'bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.85)]'
                  : 'bg-zinc-500'
          }`}
          title="runtime state"
        />
      </div>
      <div className="mt-2 space-y-1 border-t border-zinc-800/80 pt-2 text-[12px] leading-snug">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-cns-graph-secondary">container</span>
          <span className="font-medium text-zinc-100">{data.statusLabel}</span>
        </div>
        {data.runtimeIp ? (
          <div className="font-mono text-[12px] font-medium text-emerald-400/95">{data.runtimeIp}</div>
        ) : null}
        {data.intentIp ? (
          <div className="font-mono text-[11px] text-cns-graph-mono">intent {data.intentIp}</div>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-zinc-500 !bg-zinc-700" />
    </div>
  );
});

const nodeTypes = { cnsEditor: CnsEditorNode };

interface InnerProps {
  topologyId: string;
  topology: TopologyResponse | null;
  nodes: TopologyNodeResponse[];
  links: TopologyLinkResponse[];
  runtime: RuntimeTopologyResponse | null;
  /** Runtime controls busy label from parent (reconcile/heal/deploy) for graph overlays. */
  controllerBusy?: string | null;
  /** Detail-page action in flight — disables topology toolbar while reconcile/heal/deploy run. */
  globalBusy?: boolean;
  onRefresh: () => Promise<void>;
}

function TopologyWorkspaceInner({
  topologyId,
  topology,
  nodes,
  links,
  runtime,
  controllerBusy = null,
  globalBusy = false,
  onRefresh,
}: InnerProps) {
  const { fitView } = useReactFlow();
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node<CnsFlowNodeData>>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const { selectedNodeId, selectedEdgeId, setSelectedNodeId, setSelectedEdgeId, onSelectionChange } =
    useTopologyEditor();

  const { sig } = useTopologySync(nodes, links);
  const prevSig = useRef<string>('');

  /* Full rebuild when persisted graph changes (API). */
  useEffect(() => {
    if (sig === prevSig.current && prevSig.current !== '') {
      return;
    }
    prevSig.current = sig;
    setRfNodes(topologyNodesToFlowNodes(nodes, runtime, null));
    setRfEdges(topologyLinksToFlowEdges(links, runtime?.deployment_status ?? null));
    queueMicrotask(() => fitView({ padding: 0.18, duration: 280 }));
  }, [sig, nodes, links, runtime, setRfNodes, setRfEdges, fitView]);

  /* Overlay runtime + controller activity without resetting drag positions. */
  useEffect(() => {
    setRfNodes((nds) =>
      nds.map((n) => {
        const pres = deriveNodeRuntimePresentation(n.id, runtime, controllerBusy);
        const d = n.data as CnsFlowNodeData;
        return {
          ...n,
          data: {
            ...d,
            ...pres,
          },
        };
      }),
    );
  }, [runtime, controllerBusy, setRfNodes]);

  useEffect(() => {
    setRfEdges((eds) =>
      eds.map((e) => {
        const animate = topologyLinksToFlowEdges(
          links.filter((l) => l.id === e.id),
          runtime?.deployment_status ?? null,
        );
        const neo = animate[0];
        return neo
          ? {
              ...e,
              animated: neo.animated,
              style: neo.style,
              markerEnd: neo.markerEnd,
            }
          : e;
      }),
    );
  }, [runtime?.deployment_status, links, setRfEdges]);

  const selectedNode = useMemo(
    () => (selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) ?? null : null),
    [nodes, selectedNodeId],
  );
  const selectedLink = useMemo(
    () => (selectedEdgeId ? links.find((l) => l.id === selectedEdgeId) ?? null : null),
    [links, selectedEdgeId],
  );

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setBusy(label);
      setNote(null);
      setSuccessMsg(null);
      try {
        await fn();
        await onRefresh();
        setSuccessMsg(`${label.replace(/-/g, ' ')} completed`);
        window.setTimeout(() => setSuccessMsg(null), 4500);
      } catch (e) {
        setNote(formatApiError(e));
      } finally {
        setBusy(null);
      }
    },
    [onRefresh],
  );

  const savePositions = useCallback(async () => {
    await run('save-positions', async () => {
      for (const n of rfNodes) {
        const pos = n.position;
        await topoApi.patchNode(topologyId, n.id, {
          config: { [EDITOR_POSITION_KEY]: { x: pos.x, y: pos.y } },
        });
      }
    });
  }, [rfNodes, run, topologyId]);

  const onConnect = useCallback(
    async (c: Connection) => {
      if (!c.source || !c.target) return;
      const exists = links.some(
        (l) =>
          (l.source_node_id === c.source && l.target_node_id === c.target) ||
          (l.source_node_id === c.target && l.target_node_id === c.source),
      );
      if (exists) {
        setNote('Link already exists between these nodes.');
        return;
      }
      await run('connect', async () => {
        await topoApi.createLink(topologyId, {
          source_node_id: c.source,
          target_node_id: c.target,
          network_name: `net-${Date.now().toString(36)}`,
          cidr: '10.250.0.0/24',
          config: null,
        });
      });
    },
    [links, topologyId, run],
  );

  const addNodeOfType = async (nodeType: TopologyNodeResponse['node_type']) => {
    const defaults: Record<string, { image: string | null }> = {
      host: { image: 'alpine:latest' },
      generic: { image: 'nginx:alpine' },
      router: { image: 'alpine:latest' },
      switch: { image: 'alpine:latest' },
      gateway: { image: 'alpine:latest' },
    };
    await run('add-node', async () => {
      await topoApi.createNode(topologyId, {
        name: `${nodeType}-${Math.random().toString(36).slice(2, 6)}`,
        node_type: nodeType,
        image: defaults[nodeType]?.image ?? null,
        ip_address: null,
        config: {
          [EDITOR_POSITION_KEY]: { x: 320 + Math.random() * 80, y: 220 + Math.random() * 80 },
        },
      });
    });
  };

  const autoLayout = async () => {
    const pos = gridPositions(nodes.map((n) => n.id));
    await run('layout', async () => {
      for (const n of nodes) {
        const p = pos[n.id];
        if (!p) continue;
        await topoApi.patchNode(topologyId, n.id, {
          config: { [EDITOR_POSITION_KEY]: { x: p.x, y: p.y } },
        });
      }
    });
  };

  const clearAll = async () => {
    const ok = window.confirm(
      'Remove every link and node in this topology? This cannot be undone.\n\nClick OK to continue.',
    );
    if (!ok) return;
    await run('clear', async () => {
      for (const l of links) {
        await topoApi.deleteLink(topologyId, l.id);
      }
      for (const n of nodes) {
        await topoApi.deleteNode(topologyId, n.id);
      }
    });
  };

  const resetDemoLab = async () => {
    const ok = window.confirm(
      'Replace this topology with the compact demo lab (host-a, service-b, one link)? All current nodes and links will be removed.',
    );
    if (!ok) return;
    await run('reset-lab', async () => {
      await resetTopologyToDemoLab(topologyId);
    });
  };

  const deleteSelection = useCallback(async () => {
    if (selectedEdgeId) {
      const eid = selectedEdgeId;
      setSelectedEdgeId(null);
      await run('delete-link', async () => {
        await topoApi.deleteLink(topologyId, eid);
      });
      return;
    }
    if (selectedNodeId) {
      const nid = selectedNodeId;
      setSelectedNodeId(null);
      await run('delete-node', async () => {
        await topoApi.deleteNode(topologyId, nid);
      });
    }
  }, [run, selectedEdgeId, selectedNodeId, setSelectedEdgeId, setSelectedNodeId, topologyId]);

  const duplicateSelection = useCallback(async () => {
    if (!selectedNodeId) return;
    const src = nodes.find((n) => n.id === selectedNodeId);
    if (!src) return;
    const pos = readEditorPosition(src.config) ?? { x: 300, y: 220 };
    await run('dup', async () => {
      await topoApi.createNode(topologyId, {
        name: `${src.name}-copy`,
        node_type: src.node_type,
        image: src.image,
        ip_address: null,
        config: {
          ...(src.config ?? {}),
          [EDITOR_POSITION_KEY]: { x: pos.x + 40, y: pos.y + 40 },
        },
      });
    });
  }, [nodes, run, selectedNodeId, topologyId]);

  const kbRef = useRef({
    savePositions: async () => {},
    deleteSelection: async () => {},
    duplicateSelection: async () => {},
  });

  useLayoutEffect(() => {
    kbRef.current = { savePositions, deleteSelection, duplicateSelection };
  }, [savePositions, deleteSelection, duplicateSelection]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement ||
        (t instanceof HTMLElement && t.isContentEditable)
      ) {
        return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        void kbRef.current.deleteSelection();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void kbRef.current.savePositions();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        void kbRef.current.duplicateSelection();
      }
      if (e.key.toLowerCase() === 'f' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        fitView({ padding: 0.2, duration: 250 });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fitView]);

  return (
    <div className="flex flex-col gap-3">
      {note && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-950 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100">
          {note}
        </div>
      )}
      {successMsg && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          {successMsg}
        </div>
      )}
      <TopologyToolbar
        busy={busy}
        locked={globalBusy}
        nodeCount={nodes.length}
        hasSelection={Boolean(selectedNodeId || selectedEdgeId)}
        onAddHost={() => void addNodeOfType('host')}
        onAddService={() => void addNodeOfType('generic')}
        onAddRouter={() => void addNodeOfType('router')}
        onAddSwitch={() => void addNodeOfType('switch')}
        onAutoLayout={() => void autoLayout()}
        onSaveTopology={() => void savePositions()}
        onDeploy={() => run('deploy', () => deployTopology(topologyId))}
        onClear={() => void clearAll()}
        onResetDemoLab={() => void resetDemoLab()}
        onDeleteSelection={() => void deleteSelection()}
        onFit={() => fitView({ padding: 0.18, duration: 280 })}
        templates={[
          {
            id: 'client-server',
            label: 'Client / server',
            run: () =>
              run('tpl-cs', () =>
                applyTopologyTemplate(topologyId, 'client-server'),
              ),
          },
          {
            id: 'web-tier',
            label: 'Three-tier web app',
            run: () =>
              run('tpl-web', () =>
                applyTopologyTemplate(topologyId, 'web-tier'),
              ),
          },
          {
            id: 'lb',
            label: 'LB + two services',
            run: () =>
              run('tpl-lb', () =>
                applyTopologyTemplate(topologyId, 'load-balancer'),
              ),
          },
          {
            id: 'rs',
            label: 'Router / switch',
            run: () =>
              run('tpl-rs', () =>
                applyTopologyTemplate(topologyId, 'router-switch'),
              ),
          },
          {
            id: 'mesh',
            label: 'Service mesh',
            run: () =>
              run('tpl-mesh', () =>
                applyTopologyTemplate(topologyId, 'mesh'),
              ),
          },
        ]}
      />

      <TopologyStudioLayout
        canvas={
          <div className="relative flex w-full flex-col overflow-visible rounded-xl border border-zinc-200 bg-zinc-950 shadow-inner dark:border-zinc-700">
            {/* Explicit height + xyflow base CSS (.react-flow, viewport, pane) so pan/zoom/drag work */}
            <div className="relative min-h-[520px] h-[clamp(600px,62vh,880px)] w-full min-w-0 md:min-h-[600px]">
              <ReactFlow
                className="h-full w-full"
                nodes={rfNodes}
                edges={rfEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={(c) => void onConnect(c)}
                onSelectionChange={onSelectionChange}
                nodesDraggable
                nodesConnectable
                elementsSelectable
                selectNodesOnDrag={false}
                panOnDrag
                zoomOnScroll
                zoomOnPinch
                deleteKeyCode={null}
                fitView
                snapToGrid
                snapGrid={[20, 20]}
                minZoom={0.15}
                maxZoom={1.85}
                colorMode="dark"
                defaultEdgeOptions={{
                  type: 'smoothstep',
                  markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
                }}
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={24} size={1} color="#334155" className="opacity-35" />
                <Controls
                  position="bottom-left"
                  className="m-2 rounded border border-zinc-600 bg-zinc-900/95 shadow-lg backdrop-blur-sm [&_button]:border-zinc-600 [&_button]:bg-zinc-800 [&_button]:fill-zinc-200"
                  showInteractive={false}
                />
                <MiniMap
                  position="bottom-right"
                  className="m-2 !max-h-[100px] !max-w-[132px] rounded-md border border-zinc-700/50 bg-zinc-950/70 opacity-60 shadow-md"
                  maskColor="rgba(15,23,42,0.45)"
                  zoomable
                  pannable
                  nodeStrokeWidth={2}
                  nodeColor={(n) => {
                    const v = (n.data as CnsFlowNodeData | undefined)?.visual;
                    if (v === 'running') return '#22c55e';
                    if (v === 'stopped') return '#ef4444';
                    if (v === 'transition') return '#f59e0b';
                    return '#64748b';
                  }}
                />
                <Panel
                  position="top-right"
                  className="m-2 max-w-[14rem] rounded-md bg-zinc-950/85 px-2 py-1 text-[10px] leading-tight text-cns-inverse-muted shadow-md backdrop-blur-sm"
                >
                  Del remove · ⌘S save · ⌘D duplicate · F fit
                </Panel>
              </ReactFlow>
            </div>
            <p className="border-t border-zinc-700/80 px-3 py-2 text-center text-[11px] leading-snug text-cns-muted">
              Drag nodes to reposition · Scroll or pinch to zoom · Drag the empty canvas to pan
            </p>
          </div>
        }
        sidebar={
          <>
            <TopologyInspector
              topology={topology}
              selectedNode={selectedNode}
              selectedLink={selectedLink}
              onPatchNode={(body) =>
                selectedNodeId
                  ? run('patch-node', () => topoApi.patchNode(topologyId, selectedNodeId, body))
                  : Promise.resolve()
              }
              onPatchLink={(body) =>
                selectedEdgeId
                  ? run('patch-link', () => topoApi.patchLink(topologyId, selectedEdgeId, body))
                  : Promise.resolve()
              }
              onRenameTopology={(name, description) =>
                run('rename', () =>
                  topoApi.patchTopology(topologyId, {
                    name,
                    description,
                  }),
                )
              }
            />
            <DeploymentPlanningPanel
              nodes={nodes}
              links={links}
              topologyStatus={topology?.status ?? null}
              deploymentStatus={runtime?.deployment_status ?? null}
            />
          </>
        }
      />
    </div>
  );
}

export type TopologyWorkspaceProps = InnerProps;

export function TopologyWorkspace(props: TopologyWorkspaceProps) {
  return (
    <ReactFlowProvider>
      <TopologyWorkspaceInner {...props} />
    </ReactFlowProvider>
  );
}
