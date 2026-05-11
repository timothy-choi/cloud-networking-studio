import { useCallback, useState } from 'react';
import { formatApiError } from '../api/client';
import { listDeploymentEvents } from '../api/deployments';
import type { DeploymentEventResponse } from '../types/deployment';
import { usePolling } from './usePolling';

const DEFAULT_INTERVAL_MS = 3500;

export function useDeploymentEvents(
  deploymentId: string | null | undefined,
  options?: { intervalMs?: number },
) {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const active = Boolean(deploymentId);

  const [events, setEvents] = useState<DeploymentEventResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    if (!deploymentId) {
      setEvents([]);
      setError(null);
      return;
    }
    try {
      const rows = await listDeploymentEvents(deploymentId);
      setEvents(rows);
      setLastUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    }
  }, [deploymentId]);

  usePolling(refetch, intervalMs, active);

  return { events, error, refetch, lastUpdatedAt };
}
