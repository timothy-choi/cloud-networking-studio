import { useCallback, useState } from 'react';
import { formatApiError } from '../api/client';
import { listTopologyFailures } from '../api/topologies';
import type { FailureInjectionResponse } from '../types/failure';
import { usePolling } from './usePolling';

const DEFAULT_INTERVAL_MS = 6000;

export function useFailures(topologyId: string | undefined, options?: { intervalMs?: number }) {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const active = Boolean(topologyId);

  const [failures, setFailures] = useState<FailureInjectionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    if (!topologyId) {
      setFailures([]);
      return;
    }
    try {
      const rows = await listTopologyFailures(topologyId);
      setFailures(rows);
      setLastUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    }
  }, [topologyId]);

  usePolling(refetch, intervalMs, active);

  return { failures, error, refetch, lastUpdatedAt };
}
