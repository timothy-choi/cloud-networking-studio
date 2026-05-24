import { useState } from 'react';

import { ApiError, apiFetchBlob, formatApiError, resolveApiUrl } from '../../api/client';

export function triggerBlobDownload(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export function integrationOutputFileDownloadUrl(deploymentId: string, fileName: string) {
  return resolveApiUrl(
    `/deployments/${deploymentId}/integration-outputs/files/${encodeURIComponent(fileName)}`,
  );
}

export function integrationOutputArchiveDownloadUrl(deploymentId: string) {
  return resolveApiUrl(`/deployments/${deploymentId}/integration-outputs/archive`);
}

export async function downloadIntegrationOutputFile(deploymentId: string, fileName: string) {
  const blob = await apiFetchBlob(
    `/deployments/${deploymentId}/integration-outputs/files/${encodeURIComponent(fileName)}`,
  );
  triggerBlobDownload(blob, fileName);
}

export async function downloadIntegrationOutputArchive(deploymentId: string) {
  const blob = await apiFetchBlob(`/deployments/${deploymentId}/integration-outputs/archive`);
  triggerBlobDownload(blob, 'cns-integration-outputs.zip');
}

export function DownloadFileButton({
  deploymentId,
  fileName,
  label = 'Download',
}: {
  deploymentId: string;
  fileName: string;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onDownload() {
    setBusy(true);
    setErr(null);
    try {
      await downloadIntegrationOutputFile(deploymentId, fileName);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.status} ${e.statusText}` : formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <button
        type="button"
        onClick={() => void onDownload()}
        disabled={busy}
        className="rounded border border-zinc-300 bg-white px-2 py-1 text-[10px] font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
      >
        {busy ? '…' : label}
      </button>
      {err ? <span className="text-[9px] text-red-600 dark:text-red-300">{err}</span> : null}
    </span>
  );
}
