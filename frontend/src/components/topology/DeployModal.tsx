import { useEffect, useMemo, useState } from 'react';
import { listDeploymentProfiles, type DeploymentProfile } from '../../api/deploymentProfiles';
import { listTopologyVersions, type TopologyVersion } from '../../api/topologyVersions';
import type { NetworkAllocationMode } from '../../lib/networkAllocation';
import { NETWORK_ALLOCATION_HELP } from '../../lib/networkAllocation';
import { Spinner } from '../Spinner';

export type DeployModalSubmitOptions = {
  network_allocation_mode: NetworkAllocationMode;
  profile_id?: string;
  topology_version_id?: string;
};

export function DeployModal({
  open,
  onClose,
  onDeploy,
  topologyId,
  runtimeTarget,
  deployWarnings,
  blockingReasons,
  networkAllocationMode,
  onNetworkAllocationModeChange,
}: {
  open: boolean;
  onClose: () => void;
  onDeploy: (opts: DeployModalSubmitOptions) => Promise<void>;
  topologyId: string;
  runtimeTarget: string;
  deployWarnings: string[];
  blockingReasons: string[];
  networkAllocationMode: NetworkAllocationMode;
  onNetworkAllocationModeChange: (mode: NetworkAllocationMode) => void;
}) {
  const [profiles, setProfiles] = useState<DeploymentProfile[]>([]);
  const [versions, setVersions] = useState<TopologyVersion[]>([]);
  const [profileId, setProfileId] = useState<string>('');
  const [versionId, setVersionId] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoadErr(null);
    void Promise.all([listDeploymentProfiles(topologyId), listTopologyVersions(topologyId)])
      .then(([p, v]) => {
        setProfiles(p);
        setVersions(v);
        const def = p.find((x) => x.is_default);
        setProfileId(def?.id ?? '');
        setVersionId('');
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, [open, topologyId]);

  const selectedProfile = useMemo(
    () => profiles.find((p) => p.id === profileId) ?? null,
    [profiles, profileId],
  );

  const selectedVersion = useMemo(
    () => versions.find((v) => v.id === versionId) ?? null,
    [versions, versionId],
  );

  const prodLikeWarning =
    selectedProfile?.profile_type === 'prod_like'
      ? 'Prod-like profile: project owners will be notified when this deployment starts.'
      : null;

  if (!open) return null;

  const deployable = blockingReasons.length === 0;

  return (
    <div
      role="dialog"
      aria-modal
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Deploy topology</h2>
        <p className="mt-1 text-sm text-cns-muted">Review version, profile, and runtime settings before deploy.</p>

        {loadErr ? <p className="mt-2 text-sm text-red-600">{loadErr}</p> : null}

        {!deployable ? (
          <p className="mt-3 rounded border border-amber-500/50 bg-amber-50 p-2 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
            {blockingReasons.join(' ')}
          </p>
        ) : deployWarnings.length > 0 ? (
          <p className="mt-3 rounded border border-sky-500/40 bg-sky-50 p-2 text-sm dark:bg-sky-950/30">
            {deployWarnings.join(' ')}
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          <label className="block text-xs font-semibold uppercase text-cns-label">
            Topology version
            <select
              className="mt-1 w-full rounded border px-2 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
            >
              <option value="">Current (auto snapshot on deploy)</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number} — {v.source} {v.name ? `(${v.name})` : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-semibold uppercase text-cns-label">
            Deployment profile
            <select
              className="mt-1 w-full rounded border px-2 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
            >
              <option value="">None (base topology only)</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.profile_type}){p.is_default ? ' · default' : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-semibold uppercase text-cns-label">
            Network allocation
            <select
              className="mt-1 w-full rounded border px-2 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              value={networkAllocationMode}
              onChange={(e) => onNetworkAllocationModeChange(e.target.value as NetworkAllocationMode)}
            >
              <option value="managed">Managed</option>
              <option value="intent">Intent</option>
            </select>
            <span className="mt-1 block text-xs font-normal normal-case text-cns-muted">
              {NETWORK_ALLOCATION_HELP[networkAllocationMode]}
            </span>
          </label>
        </div>

        <dl className="mt-4 space-y-1 rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-950/50">
          <div className="flex justify-between gap-2">
            <dt className="text-cns-muted">Runtime</dt>
            <dd>{runtimeTarget}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-cns-muted">Version</dt>
            <dd>{selectedVersion ? `v${selectedVersion.version_number}` : 'Current'}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-cns-muted">Profile</dt>
            <dd>{selectedProfile?.name ?? 'None'}</dd>
          </div>
          {selectedProfile ? (
            <>
              <div className="flex justify-between gap-2">
                <dt className="text-cns-muted">TTL / cleanup</dt>
                <dd>
                  {String(selectedProfile.config_json?.ttl_hours ?? '—')}h /{' '}
                  {String(selectedProfile.config_json?.cleanup_policy ?? 'default')}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cns-muted">Expose policy</dt>
                <dd>{String(selectedProfile.config_json?.expose_policy ?? 'default')}</dd>
              </div>
            </>
          ) : null}
        </dl>

        {prodLikeWarning ? (
          <p className="mt-3 text-sm font-medium text-amber-800 dark:text-amber-200">{prodLikeWarning}</p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border px-4 py-2 text-sm">
            Cancel
          </button>
          <button
            type="button"
            disabled={!deployable || busy}
            onClick={() => {
              setBusy(true);
              void onDeploy({
                network_allocation_mode: networkAllocationMode,
                profile_id: profileId || undefined,
                topology_version_id: versionId || undefined,
              })
                .then(() => onClose())
                .finally(() => setBusy(false));
            }}
            className="flex items-center gap-2 rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? <Spinner className="h-4 w-4" /> : null}
            Deploy
          </button>
        </div>
      </div>
    </div>
  );
}
