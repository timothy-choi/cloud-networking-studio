import { useState } from 'react';
import { formatApiError } from '../../api/client';
import { createTemplateFromTopology } from '../../api/templates';

export function SaveAsTemplateModal({
  topologyId,
  defaultName,
  onClose,
  onCreated,
}: {
  topologyId: string;
  defaultName: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('general');
  const [tagsRaw, setTagsRaw] = useState('');
  const [visibility, setVisibility] = useState<'private' | 'project'>('project');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    const tags = tagsRaw
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    setBusy(true);
    setErr(null);
    try {
      await createTemplateFromTopology(topologyId, {
        name: name.trim() || defaultName,
        description: description.trim() || null,
        category: category.trim() || 'general',
        tags,
        visibility,
      });
      onCreated();
      onClose();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-zinc-200 bg-white p-4 shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Save as template</h2>
        <p className="mt-1 text-xs text-cns-muted">
          Captures nodes, links, and runtime intent for this topology. Project templates are visible to all members;
          private templates are only visible to you.
        </p>
        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-cns-label">
            Name
            <input
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-cns-label">
            Description
            <textarea
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-cns-label">
            Category
            <input
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-cns-label">
            Tags (comma-separated)
            <input
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
              placeholder="e.g. demo, edge, k8s"
            />
          </label>
          <label className="block text-xs font-medium text-cns-label">
            Visibility
            <select
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as 'private' | 'project')}
            >
              <option value="project">Project (all members)</option>
              <option value="private">Private (only you)</option>
            </select>
          </label>
        </div>
        {err ? <p className="mt-3 text-sm text-red-700 dark:text-red-300">{err}</p> : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !name.trim()}
            className="rounded-lg border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-sm font-semibold text-emerald-900 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/50 dark:text-emerald-100"
            onClick={() => void submit()}
          >
            {busy ? 'Saving…' : 'Save template'}
          </button>
        </div>
      </div>
    </div>
  );
}
