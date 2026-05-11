import { useCallback, useState } from 'react';
import { formatApiError } from '../api/client';
import { loadTopologyDetail, type TopologyDetailBundle } from '../services/topology.service';
import { usePolling } from './usePolling';

const DEFAULT_INTERVAL_MS = 4000;

export function useTopologyRuntime(
  topologyId: string | undefined,
  options?: { intervalMs?: number; enabled?: boolean },
) {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const enabled = options?.enabled ?? true;
  const active = Boolean(topologyId) && enabled;

  const [bundle, setBundle] = useState<TopologyDetailBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    if (!topologyId) return;
    try {
      setError(null);
      const data = await loadTopologyDetail(topologyId);
      setBundle(data);
      setLastUpdatedAt(Date.now());
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [topologyId]);

  usePolling(refetch, intervalMs, active);

  return {
    topology: bundle?.topology ?? null,
    nodes: bundle?.nodes ?? [],
    links: bundle?.links ?? [],
    runtime: bundle?.runtime ?? null,
    loading,
    error,
    refetch,
    lastUpdatedAt,
  };
}
