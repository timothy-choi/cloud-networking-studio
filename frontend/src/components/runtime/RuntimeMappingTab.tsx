import { useCallback, useEffect, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  fetchDeploymentRuntimeMapping,
  type DeploymentRuntimeMappingResponse,
} from '../../api/runtimeIntegration';
import { Spinner } from '../Spinner';

export function RuntimeMappingTab({ deploymentId }: { deploymentId: string }) {
  const [data, setData] = useState<DeploymentRuntimeMappingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await fetchDeploymentRuntimeMapping(deploymentId));
    } catch (e) {
      setData(null);
      setErr(e instanceof ApiError ? formatApiError(e) : 'Could not load mapping.');
    } finally {
      setLoading(false);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" />
        Loading topology → runtime mapping…
      </div>
    );
  }
  if (err) return <p className="text-sm text-red-700 dark:text-red-300">{err}</p>;
  if (!data || data.rows.length === 0) {
    return <p className="text-sm text-cns-muted">No mapping rows yet. Deploy to link topology nodes to runtime resources.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-cns-muted">
        Each row links a <strong>topology node</strong> to its <strong>runtime resource</strong> (container, service, or pod).
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-xs uppercase tracking-wide text-cns-label dark:border-zinc-700">
              <th className="py-2 pr-3">Topology node</th>
              <th className="py-2 pr-3">Type</th>
              <th className="py-2 pr-3">Runtime name</th>
              <th className="py-2 pr-3">Container / pod</th>
              <th className="py-2 pr-3">Internal URL</th>
              <th className="py-2">Network / NS</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800">
                <td className="py-2 pr-3">
                  <div className="font-medium">{row.topology_node_name ?? '—'}</div>
                  <div className="font-mono text-[10px] text-cns-muted">{row.topology_node_id ?? ''}</div>
                </td>
                <td className="py-2 pr-3 text-xs">{row.resource_type ?? '—'}</td>
                <td className="py-2 pr-3 font-mono text-[11px]">{row.runtime_name ?? '—'}</td>
                <td className="py-2 pr-3 font-mono text-[11px]">
                  {row.container_id?.slice(0, 12) ?? row.pod_name ?? '—'}
                </td>
                <td className="py-2 pr-3 break-all font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                  {row.internal_url ?? '—'}
                </td>
                <td className="py-2 font-mono text-[11px]">{row.namespace_or_network ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
