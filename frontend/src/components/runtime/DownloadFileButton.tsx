import { useState } from 'react';
import { ApiError, getApiBase, getStoredAccessToken } from '../../api/client';

async function fetchAuthenticatedBlob(url: string): Promise<Blob> {
  const token = getStoredAccessToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(String(detail));
    } catch {
      /* plain text error */
    }
    throw new ApiError(res.status, res.statusText, detail);
  }
  return res.blob();
}

export function triggerBlobDownload(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export function integrationOutputFileDownloadUrl(deploymentId: string, fileName: string) {
  return `${getApiBase()}/deployments/${deploymentId}/integration-outputs/files/${encodeURIComponent(fileName)}`;
}

export function integrationOutputArchiveDownloadUrl(deploymentId: string) {
  return `${getApiBase()}/deployments/${deploymentId}/integration-outputs/archive`;
}

export async function downloadIntegrationOutputFile(deploymentId: string, fileName: string) {
  const blob = await fetchAuthenticatedBlob(integrationOutputFileDownloadUrl(deploymentId, fileName));
  triggerBlobDownload(blob, fileName);
}

export async function downloadIntegrationOutputArchive(deploymentId: string) {
  const blob = await fetchAuthenticatedBlob(integrationOutputArchiveDownloadUrl(deploymentId));
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
      setErr(e instanceof ApiError ? `${e.status} ${e.statusText}` : 'Download failed');
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
