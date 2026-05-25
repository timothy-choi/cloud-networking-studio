import { useCallback, useEffect, useState } from 'react';
import {
  createDeploymentProfile,
  deleteDeploymentProfile,
  listDeploymentProfiles,
  setDefaultDeploymentProfile,
  type DeploymentProfile,
  type DeploymentProfileType,
} from '../../api/deploymentProfiles';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';

const PROFILE_TYPES: DeploymentProfileType[] = ['dev', 'staging', 'prod_like', 'custom'];

export function DeploymentProfilesPanel({
  topologyId,
  readOnly,
  isOwner,
}: {
  topologyId: string;
  readOnly?: boolean;
  isOwner?: boolean;
}) {
  const [profiles, setProfiles] = useState<DeploymentProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState('');
  const [profileType, setProfileType] = useState<DeploymentProfileType>('dev');
  const [envJson, setEnvJson] = useState('{}');

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProfiles(await listDeploymentProfiles(topologyId));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [topologyId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      let config_json: Record<string, unknown> = {};
      try {
        config_json = JSON.parse(envJson || '{}') as Record<string, unknown>;
      } catch {
        setError(new Error('Config JSON must be valid JSON'));
        return;
      }
      await createDeploymentProfile(topologyId, {
        name: name.trim(),
        profile_type: profileType,
        config_json,
      });
      setFormOpen(false);
      setName('');
      setEnvJson('{}');
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" /> Loading profiles…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <ApiErrorDisplay error={error} /> : null}
      {!readOnly ? (
        <button
          type="button"
          onClick={() => setFormOpen((v) => !v)}
          className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          {formOpen ? 'Cancel' : 'New profile'}
        </button>
      ) : null}

      {formOpen ? (
        <form onSubmit={(e) => void onCreate(e)} className="space-y-3 rounded-lg border p-3 dark:border-zinc-700">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Profile name"
            className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          />
          <select
            value={profileType}
            onChange={(e) => setProfileType(e.target.value as DeploymentProfileType)}
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          >
            {PROFILE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <textarea
            value={envJson}
            onChange={(e) => setEnvJson(e.target.value)}
            rows={4}
            className="w-full rounded border px-2 py-1 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
            placeholder='{"env_overrides":{"node-a":{"API_KEY":"secret"}}}'
          />
          <p className="text-xs text-cns-muted">Secrets are masked in diffs and audit logs.</p>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-emerald-700 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            Create profile
          </button>
        </form>
      ) : null}

      {profiles.length === 0 ? (
        <p className="text-sm text-cns-muted">No deployment profiles. Create dev/staging/prod-like overrides for deploy.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-lg border dark:divide-zinc-700 dark:border-zinc-700">
          {profiles.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <div>
                <span className="font-medium">{p.name}</span>
                {p.is_default ? (
                  <span className="ml-2 rounded bg-emerald-100 px-1 text-xs text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100">
                    default
                  </span>
                ) : null}
                <div className="text-xs text-cns-muted">{p.profile_type}</div>
              </div>
              {isOwner ? (
                <div className="flex gap-2">
                  {!p.is_default ? (
                    <button
                      type="button"
                      className="text-xs underline"
                      onClick={() =>
                        void setDefaultDeploymentProfile(topologyId, p.id).then(() => reload())
                      }
                    >
                      Set default
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="text-xs text-red-600"
                    onClick={() =>
                      void deleteDeploymentProfile(topologyId, p.id).then(() => reload())
                    }
                  >
                    Delete
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
