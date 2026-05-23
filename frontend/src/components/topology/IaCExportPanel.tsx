import { useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  downloadTopologyIacExport,
  IAC_ARCHIVE_EXPORT,
  IAC_RUNTIME_EXPORTS,
  IAC_SKELETON_EXPORTS,
  type IaCExportOption,
  type TopologyIacExportKind,
} from '../../api/topologyExports';

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

export function IaCExportPanel({ topologyId }: { topologyId: string }) {
  const [busyKind, setBusyKind] = useState<TopologyIacExportKind | null>(null);
  const [err, setErr] = useState<string | null>(null);

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

      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}

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
        <p className="mt-1 text-[11px] text-cns-muted">
          Terraform and Ansible downloads are starter templates with TODO comments — not applied by CNS.
        </p>
        <ul className="mt-2 space-y-2">
          {IAC_SKELETON_EXPORTS.map((opt) => (
            <ExportCard key={opt.kind} opt={opt} busy={busy} onDownload={(k) => void onDownload(k)} />
          ))}
        </ul>
      </section>
    </div>
  );
}
