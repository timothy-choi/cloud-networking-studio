import { useCallback, useState } from 'react';
import { formatApiError } from '../api/client';
import { listTopologyTrafficTests } from '../api/topologies';
import type { TrafficTestResponse } from '../types/traffic';
import { usePolling } from './usePolling';

const DEFAULT_INTERVAL_MS = 6000;

export function useTrafficTests(topologyId: string | undefined, options?: { intervalMs?: number }) {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const active = Boolean(topologyId);

  const [tests, setTests] = useState<TrafficTestResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    if (!topologyId) {
      setTests([]);
      return;
    }
    try {
      const rows = await listTopologyTrafficTests(topologyId);
      setTests(rows);
      setLastUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    }
  }, [topologyId]);

  usePolling(refetch, intervalMs, active);

  return { trafficTests: tests, error, refetch, lastUpdatedAt };
}
