import { useState } from 'react';

import { createTopology } from '../api/topologies';
import { formatApiError } from '../api/client';
import type { TopologyCreate } from '../types/topology';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (topologyId: string) => void;
  /** Topologies are created inside this project. */
  projectId: string | null;
}

export function CreateBlankTopologyModal({ open, onClose, onCreated, projectId }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [runtimeTarget, setRuntimeTarget] = useState('docker');
  const [networkingMode, setNetworkingMode] = useState('docker_bridge');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!open) return null;

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) {
      setErr('Enter a topology name.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const body: TopologyCreate = {
        name: trimmed,
        description: description.trim() === '' ? null : description.trim(),
        runtime_target: runtimeTarget.trim() || 'docker',
        networking_mode: networkingMode.trim() || 'docker_bridge',
        status: 'draft',
        config: null,
        ...(projectId ? { project_id: projectId } : {}),
      };
      const topo = await createTopology(body);
      onCreated(topo.id);
      onClose();
      setName('');
      setDescription('');
      setRuntimeTarget('docker');
      setNetworkingMode('docker_bridge');
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="blank-topo-title"
    >
      <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-700 dark:bg-zinc-900">
        <h2 id="blank-topo-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Create blank topology
        </h2>
        <p className="mt-1 text-sm text-cns-muted">
          Start with an empty graph. Add nodes and links in the editor, then save layout and deploy to your runtime.
        </p>

        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Name <span className="text-red-600">*</span>
            <input
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Edge lab east"
              autoFocus
            />
          </label>
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Description
            <textarea
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional notes for this environment"
            />
          </label>
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Runtime target
            <input
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={runtimeTarget}
              onChange={(e) => setRuntimeTarget(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Networking mode
            <input
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={networkingMode}
              onChange={(e) => setNetworkingMode(e.target.value)}
            />
          </label>
        </div>

        {err ? <p className="mt-3 text-sm text-red-600 dark:text-red-400">{err}</p> : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
            onClick={() => {
              onClose();
              setErr(null);
            }}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? 'Creating…' : 'Create and open editor'}
          </button>
        </div>
      </div>
    </div>
  );
}
