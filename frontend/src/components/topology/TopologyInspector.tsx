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
  /** Used to label link endpoint fields with human-readable node names. */
  nodes?: TopologyNodeResponse[];
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
  sourceNodeName,
  targetNodeName,
  onPatchLink,
}: {
  link: TopologyLinkResponse;
  sourceNodeName?: string | null;
  targetNodeName?: string | null;
  onPatchLink: TopologyInspectorProps['onPatchLink'];
}) {
  const [linkName, setLinkName] = useState(link.network_name);
  const [cidr, setCidr] = useState(link.cidr ?? '');
  const [gateway, setGateway] = useState(link.gateway ?? '');
  const [vlanTag, setVlanTag] = useState(
    link.vlan_tag != null && link.vlan_tag !== undefined ? String(link.vlan_tag) : '',
  );
  const [srcEp, setSrcEp] = useState(link.source_endpoint_ip ?? '');
  const [tgtEp, setTgtEp] = useState(link.target_endpoint_ip ?? '');
  const [linkMetaJson, setLinkMetaJson] = useState(
    link.config && Object.keys(link.config).length ? JSON.stringify(link.config, null, 2) : '{}',
  );

  useEffect(() => {
    setLinkName(link.network_name);
    setCidr(link.cidr ?? '');
    setGateway(link.gateway ?? '');
    setVlanTag(link.vlan_tag != null && link.vlan_tag !== undefined ? String(link.vlan_tag) : '');
    setSrcEp(link.source_endpoint_ip ?? '');
    setTgtEp(link.target_endpoint_ip ?? '');
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
        const vlanTrim = vlanTag.trim();
        let vlanNum: number | null = null;
        if (vlanTrim !== '') {
          const n = Number(vlanTrim);
          if (!Number.isFinite(n) || n < 0 || n > 4094) {
            alert('VLAN tag must be empty or an integer 0–4094.');
            return;
          }
          vlanNum = n;
        }
        void onPatchLink({
          network_name: linkName,
          cidr: cidr.trim() === '' ? null : cidr,
          gateway: gateway.trim() === '' ? null : gateway.trim(),
          vlan_tag: vlanNum,
          source_endpoint_ip: srcEp.trim() === '' ? null : srcEp.trim(),
          target_endpoint_ip: tgtEp.trim() === '' ? null : tgtEp.trim(),
          config: cfg,
        });
      }}
    >
      {sourceNodeName || targetNodeName ? (
        <p className="rounded-md border border-zinc-700/80 bg-zinc-900/60 px-2 py-1.5 text-[10px] leading-snug text-zinc-300">
          On this segment, <span className="font-semibold text-zinc-100">source endpoint IP</span> belongs to{' '}
          <span className="font-mono text-sky-300/95">{sourceNodeName ?? 'source node'}</span> and{' '}
          <span className="font-semibold text-zinc-100">target endpoint IP</span> belongs to{' '}
          <span className="font-mono text-sky-300/95">{targetNodeName ?? 'target node'}</span>.
        </p>
      ) : null}
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
        Gateway (segment default route for leaves)
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={gateway}
          onChange={(ev) => setGateway(ev.target.value)}
          placeholder="10.1.0.1"
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        VLAN tag (optional, documentation)
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={vlanTag}
          onChange={(ev) => setVlanTag(ev.target.value)}
          placeholder="e.g. 100"
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Source endpoint IP
        <span className="mt-0.5 block font-normal normal-case text-[10px] text-zinc-500">
          Address of {sourceNodeName ?? 'the source node'} on this network
        </span>
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={srcEp}
          onChange={(ev) => setSrcEp(ev.target.value)}
        />
      </label>
      <label className="block text-[11px] text-cns-field-label">
        Target endpoint IP
        <span className="mt-0.5 block font-normal normal-case text-[10px] text-zinc-500">
          Address of {targetNodeName ?? 'the target node'} on this network
        </span>
        <input
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
          value={tgtEp}
          onChange={(ev) => setTgtEp(ev.target.value)}
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
  nodes = [],
  selectedNode,
  selectedLink,
  onPatchNode,
  onPatchLink,
  onRenameTopology,
}: TopologyInspectorProps) {
  const linkSrcName = selectedLink ? nodes.find((n) => n.id === selectedLink.source_node_id)?.name : null;
  const linkTgtName = selectedLink ? nodes.find((n) => n.id === selectedLink.target_node_id)?.name : null;
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
          <LinkEditForm
            key={selectedLink.id}
            link={selectedLink}
            sourceNodeName={linkSrcName}
            targetNodeName={linkTgtName}
            onPatchLink={onPatchLink}
          />
        )}
      </div>
    </div>
  );
}
