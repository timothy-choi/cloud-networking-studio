import { useEffect, useState } from 'react';

import type { NodeType } from '../../types/topology';
import {
  buildNodeCreatePayload,
  emptyNodeRuntimeFields,
  validateNodeRuntimeFields,
  type NodeRuntimeFields,
} from '../../lib/nodeRuntimeConfig';
import { healthCheckToConfig, type HealthCheckFields } from '../../lib/healthCheckConfig';
import { HealthCheckFieldsForm, healthCheckFieldsFromRaw } from './HealthCheckFieldsForm';
import { ImageCapabilityHints } from './ImageCapabilityHints';
import {
  applyPreset,
  defaultImageForNodeType,
  defaultNamePrefix,
  NODE_PRESETS,
  type NodePreset,
} from '../../lib/nodePresets';

export interface AddNodeModalProps {
  open: boolean;
  initialNodeType: NodeType;
  onClose: () => void;
  onSubmit: (body: ReturnType<typeof buildNodeCreatePayload>) => Promise<void>;
}

const NODE_TYPES: NodeType[] = ['generic', 'host', 'router', 'switch', 'gateway'];

export function AddNodeModal({ open, initialNodeType, onClose, onSubmit }: AddNodeModalProps) {
  const [mode, setMode] = useState<'preset' | 'custom'>('preset');
  const [presetId, setPresetId] = useState(NODE_PRESETS[0]?.id ?? 'custom-blank');
  const [nodeType, setNodeType] = useState<NodeType>(initialNodeType);
  const [name, setName] = useState('');
  const [image, setImage] = useState('');
  const [intentIp, setIntentIp] = useState('');
  const [runtime, setRuntime] = useState<NodeRuntimeFields>(emptyNodeRuntimeFields());
  const [healthCheck, setHealthCheck] = useState<HealthCheckFields>(() =>
    healthCheckFieldsFromRaw(null, defaultImageForNodeType(initialNodeType) ?? ''),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setMode('preset');
    setPresetId(NODE_PRESETS[0]?.id ?? 'custom-blank');
    setNodeType(initialNodeType);
    setName(`${defaultNamePrefix(initialNodeType)}-${Math.random().toString(36).slice(2, 6)}`);
    setImage(defaultImageForNodeType(initialNodeType) ?? '');
    setIntentIp('');
    setRuntime(emptyNodeRuntimeFields());
    setHealthCheck(healthCheckFieldsFromRaw(null, defaultImageForNodeType(initialNodeType) ?? ''));
    setErr(null);
  }, [open, initialNodeType]);

  useEffect(() => {
    if (mode !== 'preset') return;
    const preset = NODE_PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    const applied = applyPreset(preset);
    setNodeType(applied.node_type);
    setImage(applied.image ?? '');
    setRuntime(applied.runtime);
    setHealthCheck(applied.healthCheck);
  }, [mode, presetId]);

  if (!open) return null;

  const selectedPreset = NODE_PRESETS.find((p) => p.id === presetId);

  async function submit() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setErr('Enter a node name.');
      return;
    }
    const validation = validateNodeRuntimeFields(runtime);
    if (validation) {
      setErr(validation);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const body = buildNodeCreatePayload({
        name: trimmedName,
        node_type: nodeType,
        image: image.trim() === '' ? null : image.trim(),
        ip_address: intentIp.trim() === '' ? null : intentIp.trim(),
        editorPosition: { x: 320 + Math.random() * 80, y: 220 + Math.random() * 80 },
        runtime,
        healthCheck: healthCheckToConfig(healthCheck),
      });
      await onSubmit(body);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not create node.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-node-title"
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-600 bg-zinc-900 p-5 shadow-2xl">
        <h2 id="add-node-title" className="text-lg font-semibold text-zinc-50">
          Add node
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          Start from preset or create custom node. Presets are editable defaults.
        </p>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
              mode === 'preset'
                ? 'border-sky-600 bg-sky-950/60 text-sky-100'
                : 'border-zinc-600 bg-zinc-950 text-zinc-300'
            }`}
            onClick={() => setMode('preset')}
          >
            Start from preset
          </button>
          <button
            type="button"
            className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
              mode === 'custom'
                ? 'border-sky-600 bg-sky-950/60 text-sky-100'
                : 'border-zinc-600 bg-zinc-950 text-zinc-300'
            }`}
            onClick={() => setMode('custom')}
          >
            Custom node
          </button>
        </div>

        {mode === 'preset' ? (
          <label className="mt-3 block text-[11px] text-cns-field-label">
            Preset
            <select
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
              value={presetId}
              onChange={(e) => setPresetId(e.target.value)}
            >
              {NODE_PRESETS.map((p: NodePreset) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
            {selectedPreset ? (
              <span className="mt-1 block text-[10px] text-zinc-500">{selectedPreset.description}</span>
            ) : null}
          </label>
        ) : null}

        <div className="mt-3 space-y-2">
          <label className="block text-[11px] text-cns-field-label">
            Name
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Type
            <select
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
              value={nodeType}
              onChange={(e) => setNodeType(e.target.value as NodeType)}
            >
              {NODE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Role label
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
              value={runtime.role_label}
              onChange={(e) => setRuntime((r) => ({ ...r, role_label: e.target.value }))}
              placeholder="e.g. web, api, segment_router"
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Image
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="nginx:alpine"
            />
          </label>
          <ImageCapabilityHints image={image} command={runtime.command} />
          <label className="block text-[11px] text-cns-field-label">
            Command
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={runtime.command}
              onChange={(e) => setRuntime((r) => ({ ...r, command: e.target.value }))}
              placeholder="sleep infinity"
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Intent IP
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={intentIp}
              onChange={(e) => setIntentIp(e.target.value)}
              placeholder="10.0.0.10"
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Ports JSON
            <textarea
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-[11px] text-zinc-100"
              rows={2}
              value={runtime.portsJson}
              onChange={(e) => setRuntime((r) => ({ ...r, portsJson: e.target.value }))}
              placeholder='[{"port":80,"target_port":80}]'
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Env JSON
            <textarea
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-[11px] text-zinc-100"
              rows={2}
              value={runtime.envJson}
              onChange={(e) => setRuntime((r) => ({ ...r, envJson: e.target.value }))}
              placeholder='{"APP_ENV":"lab"}'
            />
          </label>
          <label className="flex items-center gap-2 text-[11px] text-cns-field-label">
            <input
              type="checkbox"
              checked={runtime.terminal_enabled}
              onChange={(e) => setRuntime((r) => ({ ...r, terminal_enabled: e.target.checked }))}
            />
            Terminal enabled
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Bootstrap command (optional — not run unless you set command or pick a bootstrap preset)
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={runtime.bootstrap_command}
              onChange={(e) => setRuntime((r) => ({ ...r, bootstrap_command: e.target.value }))}
              placeholder="Reference only — copy into Command, or use Ubuntu/Alpine debug preset"
            />
          </label>
          <HealthCheckFieldsForm
            image={image}
            command={runtime.command}
            healthCheckRaw={null}
            value={healthCheck}
            onChange={setHealthCheck}
          />
          <label className="block text-[11px] text-cns-field-label">
            Notes
            <textarea
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
              rows={2}
              value={runtime.description}
              onChange={(e) => setRuntime((r) => ({ ...r, description: e.target.value }))}
            />
          </label>
        </div>

        {err ? <p className="mt-3 text-sm text-red-400">{err}</p> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-zinc-600 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? 'Adding…' : 'Add node'}
          </button>
        </div>
      </div>
    </div>
  );
}
