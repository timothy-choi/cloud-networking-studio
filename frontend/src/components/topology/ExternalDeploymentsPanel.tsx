import { useCallback, useEffect, useState } from 'react';

import {
  createDeploymentTarget,
  deleteDeploymentTarget,
  listDeploymentTargets,
  RUNTIME_DEPLOYMENT_TARGET_TYPES,
  updateDeploymentTarget,
  type DeploymentTarget,
} from '../../api/deploymentTargets';
import {
  createExternalDeploymentJob,
  listExternalDeploymentJobs,
  listExternalDeployments,
  type ExternalDeployment,
  type ExternalDeploymentJob,
  type ExternalJobMode,
} from '../../api/externalDeploymentJobs';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';
import {
  applyRemoteDockerTemplate,
  createBlankTargetFormState,
  parseTargetConfigJson,
  targetToFormState,
  type TargetFormMode,
  type TargetFormState,
} from './externalDeploymentTargetForm';
import {
  enabledWorkloadModes,
  isMockOrTestTarget,
  mockTargetLabel,
  workloadApplyDisabledReason,
} from './runtimeTargetHelpers';

const TARGET_TYPES = RUNTIME_DEPLOYMENT_TARGET_TYPES;
const HIGHLIGHT_MS = 3000;

function statusTone(status: string): string {
  if (status === 'succeeded' || status === 'active') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'failed') return 'text-red-700 dark:text-red-400';
  if (status === 'running') return 'text-amber-700 dark:text-amber-400';
  if (status === 'destroyed') return 'text-cns-muted';
  return 'text-cns-muted';
}

function TargetFormFields({
  form,
  setForm,
  mode,
  busy,
  onSubmit,
  onCancel,
}: {
  form: TargetFormState;
  setForm: React.Dispatch<React.SetStateAction<TargetFormState>>;
  mode: 'create' | 'edit';
  busy: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-lg border p-3 dark:border-zinc-700">
      <div className="text-sm font-medium">{mode === 'create' ? 'New runtime target' : 'Edit runtime target'}</div>
      <input
        required
        value={form.name}
        onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
        placeholder="Target name"
        className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
      />
      {mode === 'create' ? (
        <select
          value={form.targetType}
          onChange={(e) =>
            setForm((current) => ({ ...current, targetType: e.target.value as typeof current.targetType }))
          }
          className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
        >
          {TARGET_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      ) : (
        <p className="text-xs text-cns-muted">
          Target type: <code className="font-mono">{form.targetType}</code> (immutable)
        </p>
      )}
      <select
        value={form.status}
        onChange={(e) => setForm((current) => ({ ...current, status: e.target.value }))}
        className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
      >
        <option value="active">active</option>
        <option value="disabled">disabled</option>
      </select>
      <input
        value={form.credentialsRef}
        onChange={(e) => setForm((current) => ({ ...current, credentialsRef: e.target.value }))}
        placeholder="credentials_ref (env:VAR_NAME or dev:default)"
        className="w-full rounded border px-2 py-1 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
      />
      <textarea
        value={form.configJson}
        onChange={(e) => setForm((current) => ({ ...current, configJson: e.target.value }))}
        rows={6}
        placeholder='{"host":"203.0.113.10"}'
        className="w-full rounded border px-2 py-1 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
      />
      {mode === 'create' && form.targetType === 'remote_docker' ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => setForm((current) => applyRemoteDockerTemplate(current))}
          className="rounded border px-3 py-1 text-xs disabled:opacity-50"
        >
          Insert remote_docker template
        </button>
      ) : null}
      <p className="text-xs text-cns-muted">
        SSH private keys are never stored in the database. Set{' '}
        <code className="font-mono">credentials_ref</code> to a server-side secret pointer.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-emerald-700 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {mode === 'create' ? 'Create runtime target' : 'Save changes'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onCancel}
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function ExternalDeploymentsPanel({
  topologyId,
  projectId,
  readOnly,
  preselectedTargetId,
  highlightTargetId,
  onHighlightDone,
  selectedFromInfra,
  onSelectedFromInfraAck,
  refreshToken,
}: {
  topologyId: string;
  projectId: string;
  readOnly?: boolean;
  preselectedTargetId?: string | null;
  highlightTargetId?: string | null;
  onHighlightDone?: () => void;
  selectedFromInfra?: boolean;
  onSelectedFromInfraAck?: () => void;
  refreshToken?: number;
}) {
  const [tab, setTab] = useState<'targets' | 'jobs' | 'deployments'>('targets');
  const [targets, setTargets] = useState<DeploymentTarget[]>([]);
  const [jobs, setJobs] = useState<ExternalDeploymentJob[]>([]);
  const [deployments, setDeployments] = useState<ExternalDeployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [targetFormMode, setTargetFormMode] = useState<TargetFormMode>('closed');
  const [editingTargetId, setEditingTargetId] = useState<string | null>(null);
  const [targetForm, setTargetForm] = useState<TargetFormState>(createBlankTargetFormState);
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [highlightedTargetId, setHighlightedTargetId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<ExternalDeploymentJob | null>(null);
  const [applyConfirmOpen, setApplyConfirmOpen] = useState(false);
  const [deleteConfirmTarget, setDeleteConfirmTarget] = useState<DeploymentTarget | null>(null);

  const selectedTarget = targets.find((t) => t.id === selectedTargetId);
  const enabledModes = enabledWorkloadModes(selectedTarget ?? null);
  const applyDisabledReason = workloadApplyDisabledReason(selectedTarget ?? null);
  const activeDeployment = deployments.find((d) => d.status === 'active');

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, j, d] = await Promise.all([
        listDeploymentTargets(projectId),
        listExternalDeploymentJobs(topologyId),
        listExternalDeployments(topologyId),
      ]);
      setTargets(t);
      setJobs(j);
      setDeployments(d);
      setSelectedTargetId((current) => {
        if (preselectedTargetId && t.some((row) => row.id === preselectedTargetId)) {
          return preselectedTargetId;
        }
        if (current && t.some((row) => row.id === current)) {
          return current;
        }
        return t[0]?.id ?? '';
      });
      setSelectedJob((current) => {
        if (!current) return current;
        return j.find((row) => row.id === current.id) ?? current;
      });
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [projectId, topologyId, preselectedTargetId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (preselectedTargetId) {
      setSelectedTargetId(preselectedTargetId);
      setTab('jobs');
    }
  }, [preselectedTargetId]);

  useEffect(() => {
    if (refreshToken != null && refreshToken > 0) {
      void reload();
    }
  }, [refreshToken, reload]);

  useEffect(() => {
    if (!highlightTargetId) return;
    setHighlightedTargetId(highlightTargetId);
    setTab('jobs');
    const timer = window.setTimeout(() => {
      setHighlightedTargetId(null);
      onHighlightDone?.();
    }, HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [highlightTargetId, onHighlightDone]);

  function closeTargetForm() {
    setTargetFormMode('closed');
    setEditingTargetId(null);
    setTargetForm(createBlankTargetFormState());
  }

  function openCreateTargetForm() {
    if (targetFormMode === 'create') {
      closeTargetForm();
      return;
    }
    setTargetFormMode('create');
    setEditingTargetId(null);
    setTargetForm(createBlankTargetFormState());
  }

  function openEditTargetForm(target: DeploymentTarget) {
    setTargetFormMode('edit');
    setEditingTargetId(target.id);
    setTargetForm(targetToFormState(target));
  }

  async function onCreateTarget(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      let parsed: Record<string, unknown>;
      try {
        parsed = parseTargetConfigJson(targetForm.configJson);
      } catch {
        setError(new Error('Config JSON must be valid JSON'));
        return;
      }
      await createDeploymentTarget(projectId, {
        name: targetForm.name.trim(),
        target_type: targetForm.targetType,
        config_json: parsed,
        credentials_ref: targetForm.credentialsRef.trim() || null,
        status: targetForm.status,
      });
      closeTargetForm();
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onUpdateTarget(e: React.FormEvent) {
    e.preventDefault();
    if (!editingTargetId) return;
    setBusy(true);
    try {
      let parsed: Record<string, unknown>;
      try {
        parsed = parseTargetConfigJson(targetForm.configJson);
      } catch {
        setError(new Error('Config JSON must be valid JSON'));
        return;
      }
      await updateDeploymentTarget(editingTargetId, {
        name: targetForm.name.trim(),
        config_json: parsed,
        credentials_ref: targetForm.credentialsRef.trim() || null,
        status: targetForm.status,
      });
      closeTargetForm();
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteTarget(target: DeploymentTarget) {
    const hasActive = deployments.some((d) => d.status === 'active' && d.target_id === target.id);
    setDeleteConfirmTarget(null);
    setBusy(true);
    setError(null);
    try {
      if (hasActive) {
        setError(
          new Error(
            'Cannot delete this runtime target while it has active workload deployments. Destroy them first.',
          ),
        );
        return;
      }
      await deleteDeploymentTarget(target.id);
      if (selectedTargetId === target.id) {
        setSelectedTargetId('');
      }
      await reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function targetRowClass(targetId: string): string {
    return highlightedTargetId === targetId
      ? 'ring-2 ring-emerald-600 bg-emerald-50/70 dark:bg-emerald-950/20'
      : selectedTargetId === targetId
        ? 'ring-1 ring-zinc-400 dark:ring-zinc-500'
        : '';
  }

  async function onCreateJob(mode: ExternalJobMode) {
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
      if (mode === 'apply' || mode === 'destroy') {
        setApplyConfirmOpen(false);
      }
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
        <strong>Workload deployments</strong> push this topology to a <strong>runtime target</strong>{' '}
        (where containers run). Use <strong>validate → plan → apply → destroy</strong> against a{' '}
        <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/40">remote_docker</code>{' '}
        host. Terraform and Ansible provision/configure infrastructure in{' '}
        <strong>Infrastructure Deployments</strong>, not here.
      </div>

      {error ? <ApiErrorDisplay error={error} /> : null}

      {selectedFromInfra ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-950 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-100">
          <span>Selected target from infrastructure deployment</span>
          {onSelectedFromInfraAck ? (
            <button
              type="button"
              onClick={onSelectedFromInfraAck}
              className="rounded border border-emerald-300 px-2 py-0.5 text-[11px] dark:border-emerald-700"
            >
              Dismiss
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(['targets', 'jobs', 'deployments'] as const).map((id) => (
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
            {id === 'targets' ? 'Runtime Targets' : id === 'jobs' ? 'Workload Jobs' : 'Workload Deployments'}
          </button>
        ))}
      </div>

      {tab === 'targets' ? (
        <div className="space-y-3">
          {!readOnly ? (
            <button
              type="button"
              onClick={openCreateTargetForm}
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              {targetFormMode === 'create' ? 'Cancel' : 'New runtime target'}
            </button>
          ) : null}

          {targetFormMode === 'create' ? (
            <TargetFormFields
              form={targetForm}
              setForm={setTargetForm}
              mode="create"
              busy={busy}
              onSubmit={(e) => void onCreateTarget(e)}
              onCancel={closeTargetForm}
            />
          ) : null}

          {targetFormMode === 'edit' ? (
            <TargetFormFields
              form={targetForm}
              setForm={setTargetForm}
              mode="edit"
              busy={busy}
              onSubmit={(e) => void onUpdateTarget(e)}
              onCancel={closeTargetForm}
            />
          ) : null}

          {targets.length === 0 ? (
            <p className="text-sm text-cns-muted">No runtime targets yet.</p>
          ) : (
            <ul className="divide-y divide-zinc-200 rounded-lg border dark:divide-zinc-700 dark:border-zinc-700">
              {targets.map((t) => (
                <li
                  key={t.id}
                  className={`flex items-start justify-between gap-2 px-3 py-2 text-sm transition-colors ${targetRowClass(t.id)}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{t.name}</div>
                    <div className="text-xs text-cns-muted">
                      {t.target_type} · {t.status}
                      {t.credentials_ref ? ` · ref ${t.credentials_ref}` : ''}
                      {t.infrastructure_deployment_id ? ' · from infra deployment' : ''}
                    </div>
                    {mockTargetLabel(t) ? (
                      <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">{mockTargetLabel(t)}</div>
                    ) : null}
                    {workloadApplyDisabledReason(t) ? (
                      <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                        {workloadApplyDisabledReason(t)}
                      </div>
                    ) : null}
                  </div>
                  {!readOnly ? (
                    <div className="flex shrink-0 flex-col gap-1">
                      <button
                        type="button"
                        disabled={busy || targetFormMode === 'edit'}
                        onClick={() => {
                          setSelectedTargetId(t.id);
                          setTab('jobs');
                        }}
                        className="rounded border px-2 py-0.5 text-xs disabled:opacity-50"
                      >
                        Use for deploy
                      </button>
                      <button
                        type="button"
                        disabled={busy || targetFormMode === 'edit'}
                        onClick={() => openEditTargetForm(t)}
                        className="rounded border px-2 py-0.5 text-xs disabled:opacity-50"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={busy || targetFormMode === 'edit'}
                        onClick={() => setDeleteConfirmTarget(t)}
                        className="rounded border border-red-400 px-2 py-0.5 text-xs text-red-700 disabled:opacity-50 dark:text-red-300"
                      >
                        Delete
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}

          {deleteConfirmTarget ? (
            <div className="rounded-lg border border-red-200 bg-red-50/60 p-3 text-xs dark:border-red-900/50 dark:bg-red-950/20">
              <p className="font-medium text-red-900 dark:text-red-100">
                Delete runtime target &quot;{deleteConfirmTarget.name}&quot;?
              </p>
              {deleteConfirmTarget.infrastructure_deployment_id ? (
                <p className="mt-1 text-red-800 dark:text-red-200">
                  This removes the CNS target record only. The infrastructure deployment is not destroyed.
                </p>
              ) : null}
              {deployments.some(
                (d) => d.status === 'active' && d.target_id === deleteConfirmTarget.id,
              ) ? (
                <p className="mt-1 text-red-800 dark:text-red-200">
                  Active workload deployments exist on this target. Destroy them before deleting.
                </p>
              ) : null}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDeleteTarget(deleteConfirmTarget)}
                  className="rounded bg-red-700 px-3 py-1 text-white disabled:opacity-50"
                >
                  Confirm delete
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteConfirmTarget(null)}
                  className="rounded border px-3 py-1"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : tab === 'jobs' ? (
        <div className="space-y-3">
          {!readOnly ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-xs text-cns-muted">
                  Runtime target
                  <select
                    value={selectedTargetId}
                    onChange={(e) => setSelectedTargetId(e.target.value)}
                    className={`ml-2 rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900 ${targetRowClass(selectedTargetId)}`}
                  >
                    <option value="">Select runtime target</option>
                    {targets.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} ({t.target_type}
                        {isMockOrTestTarget(t) ? ', mock' : ''})
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  disabled={busy || !selectedTargetId || !enabledModes.includes('validate')}
                  onClick={() => void onCreateJob('validate')}
                  className="rounded bg-zinc-800 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-zinc-200 dark:text-zinc-900"
                >
                  Run validate
                </button>
                <button
                  type="button"
                  disabled={busy || !selectedTargetId || !enabledModes.includes('plan')}
                  onClick={() => void onCreateJob('plan')}
                  className="rounded bg-emerald-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  Run plan
                </button>
                <button
                  type="button"
                  disabled={busy || !selectedTargetId || !enabledModes.includes('apply')}
                  title={applyDisabledReason ?? undefined}
                  onClick={() => setApplyConfirmOpen(true)}
                  className="rounded bg-blue-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  Apply
                </button>
                <button
                  type="button"
                  disabled={
                    busy ||
                    !selectedTargetId ||
                    !enabledModes.includes('destroy') ||
                    !activeDeployment ||
                    activeDeployment.target_id !== selectedTargetId
                  }
                  title={applyDisabledReason ?? undefined}
                  onClick={() => void onCreateJob('destroy')}
                  className="rounded bg-red-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  Destroy
                </button>
              </div>
              {applyDisabledReason && selectedTarget ? (
                <p className="text-xs text-amber-700 dark:text-amber-300">{applyDisabledReason}</p>
              ) : null}
              {applyConfirmOpen ? (
                <div className="rounded-lg border border-red-200 bg-red-50/60 p-3 text-xs dark:border-red-900/50 dark:bg-red-950/20">
                  <p className="font-medium text-red-900 dark:text-red-100">
                    Apply will SSH to the remote Docker host and run{' '}
                    <code className="font-mono">docker compose up -d</code> outside CNS runtime.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onCreateJob('apply')}
                      className="rounded bg-red-700 px-3 py-1 text-white disabled:opacity-50"
                    >
                      Confirm apply
                    </button>
                    <button
                      type="button"
                      onClick={() => setApplyConfirmOpen(false)}
                      className="rounded border px-3 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
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
      ) : (
        <div className="space-y-3">
          {deployments.length === 0 ? (
            <p className="text-sm text-cns-muted">No external deployments recorded yet.</p>
          ) : (
            <ul className="divide-y divide-zinc-200 rounded-lg border dark:divide-zinc-700 dark:border-zinc-700">
              {deployments.map((d) => (
                <li key={d.id} className="space-y-1 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{d.compose_project_name}</span>
                    <span className={statusTone(d.status)}>{d.status}</span>
                  </div>
                  <div className="text-xs text-cns-muted">
                    Remote workdir: <code className="font-mono">{d.remote_workdir}</code>
                  </div>
                  <div className="text-xs text-cns-muted">
                    Services: {(d.services_json ?? []).map((s) => String(s.name ?? '')).join(', ') || '—'}
                  </div>
                  <div className="text-xs text-cns-muted">
                    Created {new Date(d.created_at).toLocaleString()}
                    {d.destroyed_at ? ` · destroyed ${new Date(d.destroyed_at).toLocaleString()}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
