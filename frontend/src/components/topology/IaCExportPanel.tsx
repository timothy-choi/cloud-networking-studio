import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  downloadTopologyIacExport,
  fetchTopologyIacExportPreview,
  IAC_ARCHIVE_EXPORT,
  IAC_RUNTIME_EXPORTS,
  IAC_SKELETON_EXPORTS,
  type IaCExportOption,
  type PreviewArtifactId,
  type TopologyIacExportPreview,
  type TopologyIacExportKind,
} from '../../api/topologyExports';
import { Spinner } from '../Spinner';

function ExportCard({
  opt,
  busy,
  onDownload,
}: {
  opt: IaCExportOption;
  busy: boolean;
  onDownload: (kind: TopologyIacExportKind) => void;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-950/40">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{opt.label}</p>
        <p className="font-mono text-[10px] text-cns-muted">{opt.filename}</p>
        <p className="mt-0.5 text-[11px] text-cns-muted">{opt.description}</p>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={() => onDownload(opt.kind)}
        className="shrink-0 rounded border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
      >
        Download
      </button>
    </li>
  );
}

function severityClass(severity: string): string {
  if (severity === 'error') return 'text-red-800 dark:text-red-200';
  if (severity === 'warning') return 'text-amber-800 dark:text-amber-200';
  return 'text-sky-800 dark:text-sky-200';
}

export function IaCExportPanel({ topologyId }: { topologyId: string }) {
  const [preview, setPreview] = useState<TopologyIacExportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyKind, setBusyKind] = useState<TopologyIacExportKind | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [artifactId, setArtifactId] = useState<PreviewArtifactId>('docker-compose');

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setPreview(await fetchTopologyIacExportPreview(topologyId));
    } catch (e) {
      setPreview(null);
      setErr(e instanceof ApiError ? formatApiError(e) : 'Could not load IaC preview.');
    } finally {
      setLoading(false);
    }
  }, [topologyId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDownload(kind: TopologyIacExportKind) {
    setBusyKind(kind);
    setErr(null);
    try {
      await downloadTopologyIacExport(topologyId, kind);
    } catch (e) {
      setErr(e instanceof ApiError ? formatApiError(e) : 'Download failed.');
    } finally {
      setBusyKind(null);
    }
  }

  const busy = busyKind !== null;
  const previewText = useMemo(() => {
    if (!preview) return '';
    if (artifactId === 'docker-compose' || artifactId === 'kubernetes') {
      return preview.previews[artifactId] ?? '';
    }
    if (artifactId === 'terraform') {
      return [
        '# Terraform skeleton (zip contents)',
        ...preview.terraform_files.map((f) => `- ${f}`),
        '',
        ...preview.todo_notes.filter((t) => t.toLowerCase().includes('terraform')),
      ].join('\n');
    }
    if (artifactId === 'ansible') {
      return [
        '# Ansible skeleton (zip contents)',
        ...preview.ansible_files.map((f) => `- ${f}`),
        '',
        ...preview.todo_notes.filter((t) => t.toLowerCase().includes('ansible')),
      ].join('\n');
    }
    return ['# Full archive contents', ...preview.archive_files.map((f) => `- ${f}`)].join('\n');
  }, [preview, artifactId]);

  const selectedArtifact = preview?.artifacts.find((a) => a.id === artifactId);

  if (loading && !preview) {
    return (
      <div className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" />
        Loading IaC preview…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-amber-800/30 bg-amber-950/20 px-3 py-2 text-sm text-amber-100/90">
        <p>These files are generated from your CNS topology.</p>
        <p className="mt-1">Run them outside CNS in your own environment.</p>
        <p className="mt-1 font-medium text-amber-200/90">CNS does not execute these files yet.</p>
        <p className="mt-2 text-amber-100/80">
          Terraform and Ansible exports are skeletons you run outside CNS.
        </p>
      </div>

      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}

      {preview ? (
        <>
          {(preview.warnings.length > 0 ||
            preview.unsupported_features.length > 0 ||
            preview.todo_notes.length > 0) && (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">
                Validation &amp; notes
              </h3>
              {preview.warnings.length > 0 ? (
                <ul className="space-y-1 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 text-[11px] dark:border-zinc-700 dark:bg-zinc-950/40">
                  {preview.warnings.map((w, i) => (
                    <li key={`${w.code}-${i}`} className={severityClass(w.severity)}>
                      <span className="font-mono text-[10px] opacity-70">{w.code}</span> — {w.message}
                    </li>
                  ))}
                </ul>
              ) : null}
              {preview.unsupported_features.length > 0 ? (
                <div className="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-[11px] text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
                  <p className="font-medium">Unsupported in export</p>
                  <ul className="mt-1 list-disc pl-4">
                    {preview.unsupported_features.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {preview.todo_notes.length > 0 ? (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 text-[11px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950/40 dark:text-zinc-300">
                  <p className="font-medium">TODO notes</p>
                  <ul className="mt-1 list-disc pl-4">
                    {preview.todo_notes.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          )}

          <section className="space-y-2">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <label className="block text-[11px] text-cns-field-label">
                Preview artifact
                <select
                  className="mt-0.5 rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
                  value={artifactId}
                  onChange={(e) => setArtifactId(e.target.value as PreviewArtifactId)}
                >
                  {preview.artifacts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.category})
                    </option>
                  ))}
                </select>
              </label>
              {selectedArtifact ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDownload(selectedArtifact.id as TopologyIacExportKind)}
                  className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                >
                  {busyKind === selectedArtifact.id ? 'Downloading…' : `Download ${selectedArtifact.name}`}
                </button>
              ) : null}
            </div>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-950/90 p-3 font-mono text-[11px] text-zinc-100 dark:border-zinc-700">
              {previewText || 'No preview available.'}
            </pre>
          </section>
        </>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-cns-label">Full archive</p>
          <p className="font-mono text-[10px] text-cns-muted">{IAC_ARCHIVE_EXPORT.filename}</p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDownload('archive')}
          className="rounded-lg border border-emerald-700/40 bg-emerald-950/30 px-3 py-1.5 text-xs font-semibold text-emerald-100 hover:bg-emerald-900/40 disabled:opacity-50"
        >
          {busyKind === 'archive' ? 'Downloading…' : IAC_ARCHIVE_EXPORT.label}
        </button>
      </div>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Runtime blueprints</h3>
        <ul className="mt-2 space-y-2">
          {IAC_RUNTIME_EXPORTS.map((opt) => (
            <ExportCard key={opt.kind} opt={opt} busy={busy} onDownload={(k) => void onDownload(k)} />
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">
          IaC skeletons (outside CNS)
        </h3>
        <ul className="mt-2 space-y-2">
          {IAC_SKELETON_EXPORTS.map((opt) => (
            <ExportCard key={opt.kind} opt={opt} busy={busy} onDownload={(k) => void onDownload(k)} />
          ))}
        </ul>
      </section>

      <button
        type="button"
        onClick={() => void load()}
        disabled={loading}
        className="text-xs text-cns-muted underline hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        Refresh preview
      </button>
    </div>
  );
}
