import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatApiError } from '../api/client';
import { listProjects } from '../api/projects';
import type { ProjectResponse } from '../api/projects';
import { cloneTemplate, deleteTemplate, listTemplates, type RuntimeTemplateSummary } from '../api/templates';
import { SectionEmptyState } from '../components/SectionEmptyState';
import { Spinner } from '../components/Spinner';

function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { hour12: false, month: 'short', day: '2-digit' });
  } catch {
    return iso;
  }
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<RuntimeTemplateSummary[]>([]);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [cloneFor, setCloneFor] = useState<RuntimeTemplateSummary | null>(null);
  const [cloneName, setCloneName] = useState('');
  const [cloneProjectId, setCloneProjectId] = useState('');
  const [cloneBusy, setCloneBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [t, p] = await Promise.all([listTemplates(), listProjects()]);
      setItems(t);
      setProjects(p);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onClone() {
    if (!cloneFor || !cloneProjectId) return;
    setCloneBusy(true);
    setErr(null);
    try {
      const topo = await cloneTemplate(cloneFor.id, {
        name: cloneName.trim() || `${cloneFor.name} (copy)`,
        project_id: cloneProjectId,
      });
      setCloneFor(null);
      navigate(`/topologies/${topo.id}`);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setCloneBusy(false);
    }
  }

  async function onDelete(t: RuntimeTemplateSummary) {
    if (!t.can_delete) return;
    if (!window.confirm(`Delete template “${t.name}”?`)) return;
    setErr(null);
    try {
      await deleteTemplate(t.id);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
            ← Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Templates</h1>
          <p className="mt-1 max-w-2xl text-sm text-cns-muted">
            Reusable topology snapshots — including built-in starters — clone into a new draft topology in your project.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          {loading ? <Spinner className="h-4 w-4" /> : null}
          Refresh
        </button>
      </div>

      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-cns-muted">
          <Spinner className="h-5 w-5" />
          Loading…
        </div>
      ) : (
        <>
          {items.length === 0 ? (
            <SectionEmptyState
              title="No templates in the library"
              description="Templates capture a reusable topology snapshot (nodes, links, runtime target). Built-in starters ship with the API; create your own from an existing topology with “Save as template”."
              primaryAction={{ label: 'Back to dashboard', to: '/dashboard' }}
              secondaryHint={
                <span>
                  Open any topology, then use <strong className="font-semibold">Save as template</strong> to add a private or project-scoped pattern here.
                </span>
              }
            />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((t) => (
            <li
              key={t.id}
              className="flex flex-col rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">{t.name}</h2>
                {t.slug ? (
                  <span className="shrink-0 rounded bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-violet-900 dark:bg-violet-950 dark:text-violet-200">
                    Starter
                  </span>
                ) : null}
              </div>
              <p className="mt-1 line-clamp-3 text-sm text-cns-muted">{t.description || '—'}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="rounded bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {t.category}
                </span>
                <span className="rounded bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {t.visibility}
                </span>
              </div>
              {t.tags.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {t.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-zinc-200 px-2 py-0.5 text-[11px] text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
              <p className="mt-3 text-[11px] text-cns-muted">Updated {fmtWhen(t.updated_at)}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100"
                  onClick={() => {
                    setCloneFor(t);
                    setCloneName(`${t.name} (copy)`);
                    if (projects[0]?.id) setCloneProjectId(projects[0].id);
                  }}
                >
                  Create topology
                </button>
                {t.can_delete ? (
                  <button
                    type="button"
                    className="rounded-lg border border-red-300 px-3 py-1.5 text-xs text-red-800 dark:border-red-900 dark:text-red-300"
                    onClick={() => void onDelete(t)}
                  >
                    Delete
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
          )}
        </>
      )}

      {cloneFor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">New topology from template</h3>
            <p className="mt-1 text-xs text-cns-muted">Template: {cloneFor.name}</p>
            <label className="mt-3 block text-xs font-medium text-cns-label">
              Topology name
              <input
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
              />
            </label>
            <label className="mt-3 block text-xs font-medium text-cns-label">
              Project
              <select
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
                value={cloneProjectId}
                onChange={(e) => setCloneProjectId(e.target.value)}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-lg border px-3 py-1.5 text-sm" onClick={() => setCloneFor(null)}>
                Cancel
              </button>
              <button
                type="button"
                disabled={cloneBusy || !cloneProjectId}
                className="rounded-lg border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-sm font-semibold text-emerald-900 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/50 dark:text-emerald-100"
                onClick={() => void onClone()}
              >
                {cloneBusy ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
