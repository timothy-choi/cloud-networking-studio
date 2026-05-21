import { useEffect, useState } from 'react';

import { createTopology } from '../api/topologies';
import { cloneTemplate, listTemplates, type RuntimeTemplateSummary } from '../api/templates';
import { formatApiError } from '../api/client';
import type { TopologyCreate } from '../types/topology';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (topologyId: string) => void;
  /** Topologies are created inside this project. */
  projectId: string | null;
}

type CreateMode = 'blank' | 'template';

export function CreateBlankTopologyModal({ open, onClose, onCreated, projectId }: Props) {
  const [mode, setMode] = useState<CreateMode>('blank');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [runtimeTarget, setRuntimeTarget] = useState('docker');
  const [networkingMode, setNetworkingMode] = useState('docker_bridge');
  const [templates, setTemplates] = useState<RuntimeTemplateSummary[]>([]);
  const [templateId, setTemplateId] = useState('');
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open || mode !== 'template') return;
    let cancelled = false;
    setTemplatesLoading(true);
    void listTemplates(projectId ? { project_id: projectId } : undefined)
      .then((rows) => {
        if (cancelled) return;
        setTemplates(rows);
        if (rows.length && !templateId) {
          setTemplateId(rows[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) setTemplates([]);
      })
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, mode, projectId, templateId]);

  if (!open) return null;

  async function submitBlank() {
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
      resetForm();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitFromTemplate() {
    if (!templateId) {
      setErr('Select a template.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const topo = await cloneTemplate(templateId, {
        name: name.trim() === '' ? null : name.trim(),
        project_id: projectId,
      });
      onCreated(topo.id);
      onClose();
      resetForm();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  function resetForm() {
    setName('');
    setDescription('');
    setRuntimeTarget('docker');
    setNetworkingMode('docker_bridge');
    setMode('blank');
    setTemplateId('');
  }

  async function submit() {
    if (mode === 'template') {
      await submitFromTemplate();
    } else {
      await submitBlank();
    }
  }

  const selectedTemplate = templates.find((t) => t.id === templateId);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="blank-topo-title"
    >
      <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-700 dark:bg-zinc-900">
        <h2 id="blank-topo-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Create topology
        </h2>
        <p className="mt-1 text-sm text-cns-muted">
          Start blank or clone a saved template — existing topology builder, deploy, and Runtime Access flows are unchanged.
        </p>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
              mode === 'blank'
                ? 'border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900'
                : 'border-zinc-300 text-zinc-700 dark:border-zinc-600 dark:text-zinc-300'
            }`}
            onClick={() => setMode('blank')}
          >
            Start blank
          </button>
          <button
            type="button"
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
              mode === 'template'
                ? 'border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900'
                : 'border-zinc-300 text-zinc-700 dark:border-zinc-600 dark:text-zinc-300'
            }`}
            onClick={() => setMode('template')}
          >
            Start from template
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Name {mode === 'blank' ? <span className="text-red-600">*</span> : null}
            <input
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={mode === 'template' ? 'Optional override' : 'e.g. Edge lab east'}
              autoFocus
            />
          </label>

          {mode === 'blank' ? (
            <>
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
            </>
          ) : (
            <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
              Template
              <select
                className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                disabled={templatesLoading || templates.length === 0}
              >
                {templates.length === 0 ? (
                  <option value="">{templatesLoading ? 'Loading…' : 'No templates available'}</option>
                ) : (
                  templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.slug ? ` (${t.slug})` : ''}
                    </option>
                  ))
                )}
              </select>
              {selectedTemplate?.description ? (
                <span className="mt-1 block text-[11px] text-zinc-500">{selectedTemplate.description}</span>
              ) : null}
            </label>
          )}
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
            disabled={busy || (mode === 'template' && (!templateId || templates.length === 0))}
          >
            {busy ? 'Creating…' : 'Create and open editor'}
          </button>
        </div>
      </div>
    </div>
  );
}
