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
  gridPositions,
  nodeWorkloadFromRuntime,
  readEditorPosition,
  runtimePrimaryIp,
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
import { applyTopologyTemplate } from './templates';

const CnsEditorNode = memo(function CnsEditorNode({
  data,
  selected,
}: NodeProps<Node<CnsFlowNodeData>>) {
  const wl = data.workload;
  const ring = selected
    ? 'ring-2 ring-sky-400 shadow-sky-500/20'
    : data.degraded
      ? 'ring-2 ring-amber-500 shadow-amber-500/25'
      : wl === 'running'
        ? 'ring-2 ring-emerald-500/60'
        : wl === 'stopped'
          ? 'ring-2 ring-red-500/70'
          : 'ring-2 ring-zinc-600';

  return (
    <div className={`min-w-[158px] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 shadow-xl ${ring}`}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-zinc-500 !bg-zinc-600" />
      <div className="text-[13px] font-semibold leading-tight text-zinc-50">{data.title}</div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{data.subtitle}</div>
      {data.intentIp ? (
        <div className="mt-1 font-mono text-[11px] text-slate-300">intent {data.intentIp}</div>
      ) : null}
      {data.runtimeIp ? (
        <div className="font-mono text-[11px] text-emerald-400/95">runtime {data.runtimeIp}</div>
      ) : null}
      <div className="mt-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide">
        <span
          className={
            wl === 'running'
              ? 'text-emerald-400'
              : wl === 'stopped'
                ? 'text-red-400'
                : 'text-zinc-500'
          }
        >
          {wl}
        </span>
        {data.degraded ? <span className="text-amber-400">degraded</span> : null}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-zinc-500 !bg-zinc-600" />
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
  onRefresh: () => Promise<void>;
}

function TopologyWorkspaceInner({
  topologyId,
  topology,
  nodes,
  links,
  runtime,
  onRefresh,
}: InnerProps) {
  const { fitView } = useReactFlow();
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node<CnsFlowNodeData>>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
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
    setRfNodes(topologyNodesToFlowNodes(nodes, runtime));
    setRfEdges(topologyLinksToFlowEdges(links, runtime?.deployment_status ?? null));
    queueMicrotask(() => fitView({ padding: 0.2, duration: 200 }));
  }, [sig, nodes, links, runtime, setRfNodes, setRfEdges, fitView]);

  /* Overlay runtime health without resetting drag positions. */
  useEffect(() => {
    setRfNodes((nds) =>
      nds.map((n) => {
        const wl = nodeWorkloadFromRuntime(n.id, runtime);
        const rip = runtimePrimaryIp(n.id, runtime);
        const d = n.data as CnsFlowNodeData;
        return {
          ...n,
          data: {
            ...d,
            workload: wl,
            runtimeIp: rip,
            degraded: wl === 'stopped',
          },
        };
      }),
    );
  }, [runtime, setRfNodes]);

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
      try {
        await fn();
        await onRefresh();
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
    if (!confirm('Delete all links and nodes in this topology?')) return;
    await run('clear', async () => {
      for (const l of links) {
        await topoApi.deleteLink(topologyId, l.id);
      }
      for (const n of nodes) {
        await topoApi.deleteNode(topologyId, n.id);
      }
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
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          {note}
        </div>
      )}
      <TopologyToolbar
        busy={busy}
        onAddHost={() => void addNodeOfType('host')}
        onAddService={() => void addNodeOfType('generic')}
        onAddRouter={() => void addNodeOfType('router')}
        onAddSwitch={() => void addNodeOfType('switch')}
        onAutoLayout={() => void autoLayout()}
        onSaveTopology={() => void savePositions()}
        onDeploy={() => run('deploy', () => deployTopology(topologyId))}
        onClear={() => void clearAll()}
        onFit={() => fitView({ padding: 0.2, duration: 250 })}
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
            label: 'Multi-tier web',
            run: () =>
              run('tpl-web', () =>
                applyTopologyTemplate(topologyId, 'web-tier'),
              ),
          },
          {
            id: 'lb',
            label: 'Load balancer',
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
            label: 'Mesh',
            run: () =>
              run('tpl-mesh', () =>
                applyTopologyTemplate(topologyId, 'mesh'),
              ),
          },
        ]}
      />

      <TopologyStudioLayout
        canvas={
          <div className="min-h-[520px] rounded-xl border border-zinc-200 bg-zinc-950 shadow-inner dark:border-zinc-700">
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={(c) => void onConnect(c)}
              onSelectionChange={onSelectionChange}
              deleteKeyCode={null}
              fitView
              snapToGrid
              snapGrid={[16, 16]}
              colorMode="dark"
              defaultEdgeOptions={{
                type: 'smoothstep',
                markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
              }}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} size={1} color="#334155" className="opacity-40" />
              <Controls
                className="rounded border border-zinc-600 bg-zinc-900 shadow-lg [&_button]:border-zinc-600 [&_button]:bg-zinc-800 [&_button]:fill-zinc-200"
                showInteractive={false}
              />
              <MiniMap
                className="rounded border border-zinc-600 bg-zinc-900/95 shadow-lg"
                maskColor="rgba(15,23,42,0.92)"
                nodeColor={(n) => {
                  if (n.type === 'cnsEditor') return '#0ea5e9';
                  return '#475569';
                }}
              />
              <Panel position="top-right" className="rounded-md bg-zinc-900/90 px-2 py-1 text-[10px] text-zinc-400">
                Del remove · ⌘S save · ⌘D duplicate · F fit
              </Panel>
            </ReactFlow>
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
