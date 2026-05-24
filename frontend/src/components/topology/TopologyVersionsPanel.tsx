import { useCallback, useEffect, useState } from 'react';
import {
  createTopologyVersion,
  diffTopologyVersions,
  listTopologyVersions,
  rollbackTopologyVersion,
  type TopologyVersion,
} from '../../api/topologyVersions';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';

function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}

function snapshotSummary(snapshot: Record<string, unknown> | undefined): string {
  const nodes = (snapshot?.nodes as unknown[]) ?? [];
  const links = (snapshot?.links as unknown[]) ?? [];
  return `${nodes.length} nodes · ${links.length} links`;
}

export function TopologyVersionsPanel({
  topologyId,
  readOnly,
  isOwner,
  onRollback,
}: {
  topologyId: string;
  readOnly?: boolean;
  isOwner?: boolean;
  onRollback?: () => void;
}) {
  const [versions, setVersions] = useState<TopologyVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [compareA, setCompareA] = useState<string>('');
  const [compareB, setCompareB] = useState<string>('');
  const [diffJson, setDiffJson] = useState<Record<string, unknown> | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setVersions(await listTopologyVersions(topologyId));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [topologyId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function onSaveVersion() {
    setBusy('save');
    try {
      await createTopologyVersion(topologyId, { name: 'Manual save' });
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function onCompare() {
    if (!compareA || !compareB || compareA === compareB) return;
    setBusy('diff');
    setDiffJson(null);
    try {
      const res = await diffTopologyVersions(topologyId, compareB, compareA);
      setDiffJson(res.diff);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function confirmRollback(versionId: string) {
    setBusy('rollback');
    try {
      await rollbackTopologyVersion(topologyId, versionId);
      setRollbackTarget(null);
      await reload();
      onRollback?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" /> Loading versions…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <ApiErrorDisplay error={error} /> : null}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={readOnly || busy !== null}
          onClick={() => void onSaveVersion()}
          className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Save version
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void reload()}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600"
        >
          Refresh
        </button>
      </div>

      {versions.length === 0 ? (
        <p className="text-sm text-cns-muted">No saved versions yet. Use Save version before major changes.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700">
          {versions.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <div>
                <span className="font-medium">v{v.version_number}</span>
                {v.name ? <span className="ml-2 text-cns-muted">{v.name}</span> : null}
                <div className="text-xs text-cns-muted">
                  {v.source} · {fmtWhen(v.created_at)}
                </div>
              </div>
              {isOwner ? (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => setRollbackTarget(v.id)}
                  className="rounded border border-amber-400 px-2 py-0.5 text-xs text-amber-900 dark:text-amber-200"
                >
                  Rollback
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {versions.length >= 2 ? (
        <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Compare versions</h4>
          <div className="mt-2 flex flex-wrap gap-2">
            <select
              className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              value={compareA}
              onChange={(e) => setCompareA(e.target.value)}
            >
              <option value="">Base (older)</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number} ({v.source})
                </option>
              ))}
            </select>
            <select
              className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              value={compareB}
              onChange={(e) => setCompareB(e.target.value)}
            >
              <option value="">Compare (newer)</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number} ({v.source})
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!compareA || !compareB || compareA === compareB || busy !== null}
              onClick={() => void onCompare()}
              className="rounded bg-zinc-800 px-3 py-1 text-sm text-white disabled:opacity-50"
            >
              Compare
            </button>
          </div>
          {diffJson ? (
            <pre className="mt-3 max-h-64 overflow-auto rounded bg-zinc-950 p-2 text-[11px] text-emerald-100">
              {JSON.stringify(diffJson, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}

      {rollbackTarget ? (
        <div
          role="dialog"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setRollbackTarget(null)}
        >
          <div
            className="max-w-md rounded-xl border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold">Confirm rollback</h3>
            <p className="mt-2 text-sm text-cns-muted">
              Restores the topology graph from this snapshot. Does not deploy automatically — run Deploy after
              rollback.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded border px-3 py-1 text-sm" onClick={() => setRollbackTarget(null)}>
                Cancel
              </button>
              <button
                type="button"
                disabled={busy !== null}
                className="rounded bg-amber-600 px-3 py-1 text-sm text-white"
                onClick={() => void confirmRollback(rollbackTarget)}
              >
                Rollback
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { snapshotSummary };
