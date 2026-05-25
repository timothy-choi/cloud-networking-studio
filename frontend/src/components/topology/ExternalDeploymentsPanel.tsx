import { useCallback, useEffect, useState } from 'react';

import {
  createDeploymentTarget,
  listDeploymentTargets,
  type DeploymentTarget,
  type DeploymentTargetType,
} from '../../api/deploymentTargets';
import {
  createExternalDeploymentJob,
  listExternalDeploymentJobs,
  type ExternalDeploymentJob,
} from '../../api/externalDeploymentJobs';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';

const TARGET_TYPES: DeploymentTargetType[] = [
  'remote_docker',
  'kubernetes',
  'terraform',
  'ansible',
];

function statusTone(status: string): string {
  if (status === 'succeeded') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'failed') return 'text-red-700 dark:text-red-400';
  if (status === 'running') return 'text-amber-700 dark:text-amber-400';
  return 'text-cns-muted';
}

export function ExternalDeploymentsPanel({
  topologyId,
  projectId,
  readOnly,
}: {
  topologyId: string;
  projectId: string;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<'targets' | 'jobs'>('targets');
  const [targets, setTargets] = useState<DeploymentTarget[]>([]);
  const [jobs, setJobs] = useState<ExternalDeploymentJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [targetFormOpen, setTargetFormOpen] = useState(false);
  const [targetName, setTargetName] = useState('');
  const [targetType, setTargetType] = useState<DeploymentTargetType>('remote_docker');
  const [configJson, setConfigJson] = useState('{"host":"docker.example.com"}');
  const [credentialsRef, setCredentialsRef] = useState('vault://cns/staging/docker');
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [selectedJob, setSelectedJob] = useState<ExternalDeploymentJob | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, j] = await Promise.all([
        listDeploymentTargets(projectId),
        listExternalDeploymentJobs(topologyId),
      ]);
      setTargets(t);
      setJobs(j);
      if (!selectedTargetId && t.length > 0) {
        setSelectedTargetId(t[0].id);
      }
      setSelectedJob((current) => {
        if (!current) return current;
        return j.find((row) => row.id === current.id) ?? current;
      });
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [projectId, topologyId, selectedTargetId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function onCreateTarget(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = JSON.parse(configJson || '{}') as Record<string, unknown>;
      } catch {
        setError(new Error('Config JSON must be valid JSON'));
        return;
      }
      await createDeploymentTarget(projectId, {
        name: targetName.trim(),
        target_type: targetType,
        config_json: parsed,
        credentials_ref: credentialsRef.trim() || null,
      });
      setTargetFormOpen(false);
      setTargetName('');
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onCreateJob(mode: 'validate' | 'plan') {
    if (!selectedTargetId) {
      setError(new Error('Select a deployment target first'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await createExternalDeploymentJob(topologyId, {
        target_id: selectedTargetId,
        mode,
      });
      setSelectedJob(job);
      setTab('jobs');
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading && targets.length === 0 && jobs.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" /> Loading external deployments…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-100">
        External deployment jobs prepare remote/cloud targets safely. Step 57A supports{' '}
        <strong>validate</strong> and <strong>plan</strong> only — apply/destroy are not enabled yet
        and do not run Terraform, Ansible, or shell commands.
      </div>

      {error ? <ApiErrorDisplay error={error} /> : null}

      <div className="flex flex-wrap gap-2">
        {(['targets', 'jobs'] as const).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded-md px-3 py-1 text-xs font-medium ${
              tab === id
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'border border-zinc-300 bg-white text-zinc-700 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200'
            }`}
          >
            {id === 'targets' ? 'Targets' : 'Jobs'}
          </button>
        ))}
      </div>

      {tab === 'targets' ? (
        <div className="space-y-3">
          {!readOnly ? (
            <button
              type="button"
              onClick={() => setTargetFormOpen((v) => !v)}
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              {targetFormOpen ? 'Cancel' : 'New target'}
            </button>
          ) : null}

          {targetFormOpen ? (
            <form
              onSubmit={(e) => void onCreateTarget(e)}
              className="space-y-3 rounded-lg border p-3 dark:border-zinc-700"
            >
              <input
                required
                value={targetName}
                onChange={(e) => setTargetName(e.target.value)}
                placeholder="Target name"
                className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              />
              <select
                value={targetType}
                onChange={(e) => setTargetType(e.target.value as DeploymentTargetType)}
                className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              >
                {TARGET_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                value={credentialsRef}
                onChange={(e) => setCredentialsRef(e.target.value)}
                placeholder="credentials_ref (placeholder only, e.g. vault://...)"
                className="w-full rounded border px-2 py-1 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
              />
              <textarea
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
                rows={4}
                className="w-full rounded border px-2 py-1 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
              />
              <p className="text-xs text-cns-muted">
                Secrets are not stored in the database. Use credentials_ref as an external secret pointer.
              </p>
              <button
                type="submit"
                disabled={busy}
                className="rounded bg-emerald-700 px-3 py-1 text-sm text-white disabled:opacity-50"
              >
                Create target
              </button>
            </form>
          ) : null}

          {targets.length === 0 ? (
            <p className="text-sm text-cns-muted">No deployment targets yet.</p>
          ) : (
            <ul className="divide-y divide-zinc-200 rounded-lg border dark:divide-zinc-700 dark:border-zinc-700">
              {targets.map((t) => (
                <li key={t.id} className="px-3 py-2 text-sm">
                  <div className="font-medium">{t.name}</div>
                  <div className="text-xs text-cns-muted">
                    {t.target_type} · {t.status}
                    {t.credentials_ref ? ` · ref ${t.credentials_ref}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {!readOnly ? (
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-cns-muted">
                Target
                <select
                  value={selectedTargetId}
                  onChange={(e) => setSelectedTargetId(e.target.value)}
                  className="ml-2 rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                >
                  <option value="">Select target</option>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.target_type})
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={busy || !selectedTargetId}
                onClick={() => void onCreateJob('validate')}
                className="rounded bg-zinc-800 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-zinc-200 dark:text-zinc-900"
              >
                Run validate
              </button>
              <button
                type="button"
                disabled={busy || !selectedTargetId}
                onClick={() => void onCreateJob('plan')}
                className="rounded bg-emerald-700 px-3 py-1 text-xs text-white disabled:opacity-50"
              >
                Run plan
              </button>
              <button
                type="button"
                disabled
                title="Apply is not enabled in Step 57A"
                className="cursor-not-allowed rounded border px-3 py-1 text-xs text-cns-muted opacity-60"
              >
                Apply (disabled)
              </button>
            </div>
          ) : null}

          {jobs.length === 0 ? (
            <p className="text-sm text-cns-muted">No external deployment jobs yet.</p>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              <ul className="divide-y divide-zinc-200 rounded-lg border dark:divide-zinc-700 dark:border-zinc-700">
                {jobs.map((j) => (
                  <li key={j.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedJob(j)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-900/50"
                    >
                      <span>
                        {j.mode} · {new Date(j.created_at).toLocaleString()}
                      </span>
                      <span className={statusTone(j.status)}>{j.status}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {selectedJob ? (
                <div className="rounded-lg border p-3 text-xs dark:border-zinc-700">
                  <div className="font-medium">
                    Job {selectedJob.id.slice(0, 8)} · {selectedJob.mode} ·{' '}
                    <span className={statusTone(selectedJob.status)}>{selectedJob.status}</span>
                  </div>
                  {selectedJob.artifact_refs?.length ? (
                    <div className="mt-2 text-cns-muted">
                      Artifacts: {JSON.stringify(selectedJob.artifact_refs)}
                    </div>
                  ) : null}
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2 font-mono text-[11px] dark:bg-zinc-900/60">
                    {selectedJob.logs || '(no logs)'}
                  </pre>
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
