import { useEffect, useState } from 'react';

import type {
  TopologyLinkResponse,
  TopologyLinkUpdate,
  TopologyNodeResponse,
  TopologyNodeUpdate,
  TopologyResponse,
} from '../../types/topology';

export interface TopologyInspectorProps {
  topology: TopologyResponse | null;
  selectedNode: TopologyNodeResponse | null;
  selectedLink: TopologyLinkResponse | null;
  onPatchNode: (body: TopologyNodeUpdate) => Promise<void>;
  onPatchLink: (body: TopologyLinkUpdate) => Promise<void>;
  onRenameTopology: (name: string, description: string | null) => Promise<void>;
}

const NODE_TYPES = ['generic', 'host', 'router', 'switch', 'gateway'] as const;

function TopologyMetaForm({
  topology,
  onRenameTopology,
}: {
  topology: TopologyResponse;
  onRenameTopology: TopologyInspectorProps['onRenameTopology'];
}) {
  const [topoName, setTopoName] = useState(topology.name);
  const [topoDesc, setTopoDesc] = useState(topology.description ?? '');
  useEffect(() => {
    setTopoName(topology.name);
    setTopoDesc(topology.description ?? '');
  }, [topology.id, topology.name, topology.description]);
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        void onRenameTopology(topoName, topoDesc.trim() === '' ? null : topoDesc);
      }}
    >
      <label className="block text-[11px] text-cns-field-label">
        Name
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
          value={topoName}
          onChange={(ev) => setTopoName(ev.target.value)}
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Description
        <textarea
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
          rows={2}
          value={topoDesc}
          onChange={(ev) => setTopoDesc(ev.target.value)}
        />
      </label>
      <button
        type="submit"
        className="w-full rounded-md border border-sky-700/50 bg-sky-950/50 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-900/60"
      >
        Apply topology metadata
      </button>
    </form>
  );
}

function NodeEditForm({
  node,
  onPatchNode,
}: {
  node: TopologyNodeResponse;
  onPatchNode: TopologyInspectorProps['onPatchNode'];
}) {
  const [nodeName, setNodeName] = useState(node.name);
  const [nodeType, setNodeType] = useState<(typeof NODE_TYPES)[number]>(node.node_type);
  const [image, setImage] = useState(node.image ?? '');
  const [ip, setIp] = useState(node.ip_address ?? '');
  const [metaJson, setMetaJson] = useState(
    node.config && Object.keys(node.config).length ? JSON.stringify(node.config, null, 2) : '{}',
  );

  useEffect(() => {
    setNodeName(node.name);
    setNodeType(node.node_type);
    setImage(node.image ?? '');
    setIp(node.ip_address ?? '');
    setMetaJson(
      node.config && Object.keys(node.config).length ? JSON.stringify(node.config, null, 2) : '{}',
    );
  }, [node]);

  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        let extra: Record<string, unknown> | undefined;
        try {
          const parsed: unknown = JSON.parse(metaJson || '{}');
          extra = typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
        } catch {
          alert('Node metadata must be valid JSON.');
          return;
        }
        void onPatchNode({
          name: nodeName,
          node_type: nodeType,
          image: image.trim() === '' ? null : image,
          ip_address: ip.trim() === '' ? null : ip,
          config: extra,
        });
      }}
    >
      <label className="block text-[11px] text-cns-field-label">
        Name
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={nodeName}
          onChange={(ev) => setNodeName(ev.target.value)}
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Type
        <select
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
          value={nodeType}
          onChange={(ev) => setNodeType(ev.target.value as (typeof NODE_TYPES)[number])}
        >
          {NODE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Image
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={image}
          onChange={(ev) => setImage(ev.target.value)}
          placeholder="nginx:alpine"
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Intent IP
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={ip}
          onChange={(ev) => setIp(ev.target.value)}
          placeholder="10.0.0.10"
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Config JSON (includes editor layout keys)
        <textarea
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-[11px] leading-snug text-zinc-100"
          rows={5}
          value={metaJson}
          onChange={(ev) => setMetaJson(ev.target.value)}
        />
      </label>
      <button
        type="submit"
        className="w-full rounded-md border border-emerald-800/50 bg-emerald-950/40 px-3 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-900/50"
      >
        Apply node changes
      </button>
    </form>
  );
}

function LinkEditForm({
  link,
  onPatchLink,
}: {
  link: TopologyLinkResponse;
  onPatchLink: TopologyInspectorProps['onPatchLink'];
}) {
  const [linkName, setLinkName] = useState(link.network_name);
  const [cidr, setCidr] = useState(link.cidr ?? '');
  const [linkMetaJson, setLinkMetaJson] = useState(
    link.config && Object.keys(link.config).length ? JSON.stringify(link.config, null, 2) : '{}',
  );

  useEffect(() => {
    setLinkName(link.network_name);
    setCidr(link.cidr ?? '');
    setLinkMetaJson(
      link.config && Object.keys(link.config).length ? JSON.stringify(link.config, null, 2) : '{}',
    );
  }, [link]);

  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        let cfg: Record<string, unknown> | undefined;
        try {
          const parsed: unknown = JSON.parse(linkMetaJson || '{}');
          cfg = typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
        } catch {
          alert('Link metadata must be valid JSON.');
          return;
        }
        void onPatchLink({
          network_name: linkName,
          cidr: cidr.trim() === '' ? null : cidr,
          config: cfg,
        });
      }}
    >
      <label className="block text-[11px] text-cns-field-label">
        Network name
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={linkName}
          onChange={(ev) => setLinkName(ev.target.value)}
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Subnet CIDR
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={cidr}
          onChange={(ev) => setCidr(ev.target.value)}
          placeholder="10.0.1.0/24"
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Link metadata JSON
        <textarea
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-[11px] leading-snug text-zinc-100"
          rows={4}
          value={linkMetaJson}
          onChange={(ev) => setLinkMetaJson(ev.target.value)}
        />
      </label>
      <button
        type="submit"
        className="w-full rounded-md border border-violet-800/50 bg-violet-950/40 px-3 py-1.5 text-xs font-medium text-violet-100 hover:bg-violet-900/50"
      >
        Apply link changes
      </button>
    </form>
  );
}

export function TopologyInspector({
  topology,
  selectedNode,
  selectedLink,
  onPatchNode,
  onPatchLink,
  onRenameTopology,
}: TopologyInspectorProps) {
  return (
    <div className="space-y-3 rounded-xl border border-zinc-700/80 bg-zinc-950/80 p-4 shadow-inner">
      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-cns-inverse-muted">Topology</h3>
        {topology ? (
          <TopologyMetaForm key={topology.id} topology={topology} onRenameTopology={onRenameTopology} />
        ) : (
          <p className="mt-1 text-xs text-cns-inverse-label">No topology loaded.</p>
        )}
      </div>

      <div className="border-t border-zinc-800 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-cns-inverse-muted">Node</h3>
        {!selectedNode ? (
          <p className="mt-1 text-xs text-cns-inverse-label">Select a node on the canvas.</p>
        ) : (
          <NodeEditForm key={selectedNode.id} node={selectedNode} onPatchNode={onPatchNode} />
        )}
      </div>

      <div className="border-t border-zinc-800 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-cns-inverse-muted">Link</h3>
        {!selectedLink ? (
          <p className="mt-1 text-xs text-cns-inverse-label">Select a link on the canvas.</p>
        ) : (
          <LinkEditForm key={selectedLink.id} link={selectedLink} onPatchLink={onPatchLink} />
        )}
      </div>
    </div>
  );
}
