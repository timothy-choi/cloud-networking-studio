import { useCallback, useState } from 'react';

import { formatApiError } from '../api/client';
import { deployTopology } from '../api/deployments';

export function useDeploymentControls(
  topologyId: string | undefined,
  onAfter: () => Promise<void>,
) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const deploy = useCallback(async () => {
    if (!topologyId) return;
    setBusy(true);
    setNote(null);
    try {
      await deployTopology(topologyId);
      await onAfter();
    } catch (e) {
      setNote(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [topologyId, onAfter]);

  return { deployBusy: busy, deployNote: note, deploy, clearDeployNote: () => setNote(null) };
}
