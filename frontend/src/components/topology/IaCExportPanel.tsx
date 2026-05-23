import { useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  downloadTopologyIacExport,
  IAC_EXPORT_OPTIONS,
  type TopologyIacExportKind,
} from '../../api/topologyExports';

export function IaCExportPanel({ topologyId }: { topologyId: string }) {
  const [busy, setBusy] = useState<TopologyIacExportKind | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onDownload(kind: TopologyIacExportKind) {
    setBusy(kind);
    setErr(null);
    try {
      await downloadTopologyIacExport(topologyId, kind);
    } catch (e) {
      setErr(e instanceof ApiError ? formatApiError(e) : 'Download failed.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-800/30 bg-amber-950/20 px-3 py-2 text-sm text-amber-100/90">
        <p>These files are generated from your CNS topology.</p>
        <p className="mt-1">Run them outside CNS in your own environment.</p>
        <p className="mt-1 font-medium text-amber-200/90">CNS does not execute these files yet.</p>
      </div>

      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}

      <ul className="space-y-2">
        {IAC_EXPORT_OPTIONS.map((opt) => (
          <li
            key={opt.kind}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-950/40"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{opt.label}</p>
              <p className="font-mono text-[10px] text-cns-muted">{opt.filename}</p>
              <p className="mt-0.5 text-[11px] text-cns-muted">{opt.description}</p>
            </div>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void onDownload(opt.kind)}
              className="shrink-0 rounded border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              {busy === opt.kind ? 'Downloading…' : 'Download'}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
