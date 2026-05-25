import { useCallback, useEffect, useState } from 'react';

import {
  confirmInfrastructureDeployment,
  createInfrastructureDeployment,
  destroyInfrastructureDeployment,
  listInfrastructureDeployments,
  listInfrastructureExecutions,
  listInfrastructureTemplates,
  planInfrastructureDeployment,
  validateInfrastructureDeployment,
  type InfrastructureDeployment,
  type InfrastructureExecution,
  type InfrastructureTemplate,
} from '../../api/infrastructureDeployments';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';
import {
  buildInfrastructureCreatePayload,
  canShowApplyAction,
  canShowPlanAction,
  canShowValidateAction,
  validateInfrastructureCreateForm,
  type InfrastructureCreateFormErrors,
} from './infrastructureDeploymentForm';

function statusTone(status: string): string {
  if (status === 'succeeded') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'failed') return 'text-red-700 dark:text-red-400';
  if (status === 'awaiting_confirmation') return 'text-amber-700 dark:text-amber-400';
  if (status === 'destroyed') return 'text-cns-muted';
  return 'text-cns-muted';
}

export async function submitInfrastructureCreate(
  topologyId: string,
  values: {
    name: string;
    templateId: string;
    provider: string;
    region: string;
    vmCount: number;
  },
) {
  const errors = validateInfrastructureCreateForm(values);
  if (Object.keys(errors).length > 0) {
    throw Object.assign(new Error('Validation failed'), { fieldErrors: errors });
  }
  const created = await createInfrastructureDeployment(topologyId, buildInfrastructureCreatePayload(values));
  const deployments = await listInfrastructureDeployments(topologyId);
  return { created, deployments };
}

export function InfrastructureDeploymentsPanel({
  topologyId,
}: {
  topologyId: string;
}) {
  const [templates, setTemplates] = useState<InfrastructureTemplate[]>([]);
  const [deployments, setDeployments] = useState<InfrastructureDeployment[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [executions, setExecutions] = useState<InfrastructureExecution[]>([]);
  const [name, setName] = useState('infra-stack');
  const [templateId, setTemplateId] = useState('local-mock');
  const [provider, setProvider] = useState('local');
  const [region, setRegion] = useState('local');
  const [vmCount, setVmCount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<InfrastructureCreateFormErrors>({});
  const [showLogs, setShowLogs] = useState(false);

  const refreshDeployments = useCallback(
    async (selectId?: string) => {
      const deps = await listInfrastructureDeployments(topologyId);
      setDeployments(deps);
      if (selectId) {
        setSelectedId(selectId);
      } else if (!selectedId && deps.length > 0) {
        setSelectedId(deps[0].id);
      }
      return deps;
    },
    [topologyId, selectedId],
  );

  const load = useCallback(async () => {
    setError(null);
    const tpls = await listInfrastructureTemplates();
    setTemplates(tpls);
    if (tpls.length > 0 && !tpls.some((t) => t.template_id === templateId)) {
      setTemplateId(tpls[0].template_id);
    }
    await refreshDeployments();
  }, [refreshDeployments, templateId]);

  useEffect(() => {
    void load().catch(setError);
  }, [load]);

  const selected = deployments.find((d) => d.id === selectedId) ?? null;

  const refreshExecutions = useCallback(async (deploymentId: string) => {
    const items = await listInfrastructureExecutions(deploymentId);
    setExecutions(items);
    return items;
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setExecutions([]);
      return;
    }
    void refreshExecutions(selectedId).catch(setError);
  }, [selectedId, deployments, refreshExecutions]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const values = { name, templateId, provider, region, vmCount };
    const errors = validateInfrastructureCreateForm(values);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }

    setCreating(true);
    setBusy(true);
    setError(null);
    try {
      const { created, deployments: nextDeployments } = await submitInfrastructureCreate(topologyId, values);
      setDeployments(nextDeployments);
      setSelectedId(created.id);
      setShowLogs(false);
    } catch (err) {
      const maybeFieldErrors = (err as { fieldErrors?: InfrastructureCreateFormErrors }).fieldErrors;
      if (maybeFieldErrors) {
        setFieldErrors(maybeFieldErrors);
      } else {
        setError(err);
      }
    } finally {
      setCreating(false);
      setBusy(false);
    }
  }

  async function runAction(action: () => Promise<InfrastructureDeployment>) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      setDeployments((current) => current.map((d) => (d.id === updated.id ? updated : d)));
      await refreshExecutions(updated.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleValidate() {
    if (!selected) return;
    await runAction(() => validateInfrastructureDeployment(selected.id));
  }

  async function handlePlan() {
    if (!selected) return;
    await runAction(() => planInfrastructureDeployment(selected.id));
  }

  async function handleConfirm() {
    if (!selected) return;
    await runAction(() => confirmInfrastructureDeployment(selected.id));
    await refreshDeployments(selected.id);
  }

  async function handleDestroy() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await destroyInfrastructureDeployment(selected.id);
      setDeployments((current) => current.map((d) => (d.id === updated.id ? updated : d)));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const plan = selected?.plan_summary_json as Record<string, unknown> | null | undefined;
  const combinedLogs = executions
    .map((ex) => `[${ex.execution_type}/${ex.mode}] ${ex.logs ?? ''}`.trim())
    .filter(Boolean)
    .join('\n\n');

  return (
    <div className="space-y-4">
      {error ? <ApiErrorDisplay error={error} /> : null}

      <form onSubmit={handleCreate} className="space-y-3 rounded-lg border p-3 dark:border-zinc-700">
        <div className="text-sm font-medium">New infrastructure deployment</div>
        <div className="grid gap-2 md:grid-cols-2">
          <div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Deployment name"
              aria-invalid={Boolean(fieldErrors.name)}
              className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            />
            {fieldErrors.name ? <p className="mt-1 text-xs text-red-600">{fieldErrors.name}</p> : null}
          </div>
          <div>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.template_id}
                </option>
              ))}
            </select>
            {fieldErrors.templateId ? (
              <p className="mt-1 text-xs text-red-600">{fieldErrors.templateId}</p>
            ) : null}
          </div>
          <div>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              {(templates.find((t) => t.template_id === templateId)?.supported_providers ?? ['local']).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            {fieldErrors.provider ? <p className="mt-1 text-xs text-red-600">{fieldErrors.provider}</p> : null}
          </div>
          <div>
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="Region"
              className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            />
            {fieldErrors.region ? <p className="mt-1 text-xs text-red-600">{fieldErrors.region}</p> : null}
          </div>
          <div>
            <input
              type="number"
              min={1}
              max={10}
              value={vmCount}
              onChange={(e) => setVmCount(Number(e.target.value))}
              placeholder="VM count"
              className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            />
            {fieldErrors.vmCount ? <p className="mt-1 text-xs text-red-600">{fieldErrors.vmCount}</p> : null}
          </div>
        </div>
        <div className="pt-1">
          <button
            type="submit"
            disabled={creating || busy}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {creating ? 'Creating…' : 'Create Infrastructure Deployment'}
          </button>
        </div>
      </form>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <div className="text-sm font-medium">Deployments</div>
          {deployments.length === 0 ? (
            <p className="text-sm text-cns-muted">No infrastructure deployments yet.</p>
          ) : (
            <ul className="space-y-2">
              {deployments.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(d.id);
                      setShowLogs(false);
                    }}
                    className={`w-full rounded border px-3 py-2 text-left text-sm dark:border-zinc-700 ${
                      selectedId === d.id ? 'border-emerald-600 ring-1 ring-emerald-600/30' : ''
                    }`}
                  >
                    <div className="font-medium">{d.name}</div>
                    <div className={`text-xs ${statusTone(d.status)}`}>{d.status}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-3">
          {selected ? (
            <>
              <div className="rounded-lg border p-3 dark:border-zinc-700">
                <div className="text-sm font-medium">Deployment detail</div>
                <p className="text-xs text-cns-muted">
                  {selected.template_id} · {selected.provider} ·{' '}
                  <span className={statusTone(selected.status)}>{selected.status}</span>
                </p>
                {selected.error_message ? (
                  <p className="mt-2 text-xs text-red-600">{selected.error_message}</p>
                ) : null}
                {plan ? (
                  <div className="mt-2 space-y-1 text-xs">
                    <div>VM count: {String(plan.vm_count ?? '—')}</div>
                    <div>Region: {String(plan.region ?? '—')}</div>
                    <div>
                      Exposed ports: {Array.isArray(plan.exposed_ports) ? plan.exposed_ports.join(', ') : '—'}
                    </div>
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap gap-2">
                  {canShowValidateAction(selected.status) ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleValidate()}
                      className="rounded bg-zinc-800 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-zinc-200 dark:text-zinc-900"
                    >
                      Validate
                    </button>
                  ) : null}
                  {canShowPlanAction(selected.status) ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handlePlan()}
                      className="rounded bg-blue-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                    >
                      Plan
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setShowLogs((current) => !current)}
                    className="rounded border px-3 py-1 text-xs dark:border-zinc-600"
                  >
                    View Logs
                  </button>
                  {canShowApplyAction(selected.status) ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleConfirm()}
                      className="rounded bg-amber-600 px-3 py-1 text-xs text-white disabled:opacity-50"
                    >
                      Confirm apply
                    </button>
                  ) : null}
                  {selected.status === 'succeeded' ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleDestroy()}
                      className="rounded border border-red-500 px-3 py-1 text-xs text-red-600 disabled:opacity-50"
                    >
                      Destroy infrastructure
                    </button>
                  ) : null}
                </div>
              </div>

              {showLogs ? (
                <div className="rounded-lg border p-3 dark:border-zinc-700">
                  <div className="text-sm font-medium">Execution logs</div>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2 font-mono text-[11px] dark:bg-zinc-900/60">
                    {combinedLogs || 'No logs recorded yet. Run Validate or Plan first.'}
                  </pre>
                </div>
              ) : null}

              <div className="rounded-lg border p-3 dark:border-zinc-700">
                <div className="text-sm font-medium">Event timeline</div>
                <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-xs">
                  {(selected.events_json ?? []).map((ev, idx) => (
                    <li key={`${ev.type}-${idx}`}>
                      <span className="font-mono">{ev.type}</span>
                      {ev.message ? `: ${ev.message}` : ''}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg border p-3 dark:border-zinc-700">
                <div className="text-sm font-medium">Runtime targets created</div>
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-zinc-950 p-2 text-xs text-zinc-100">
                  {JSON.stringify(selected.runtime_targets_json ?? [], null, 2)}
                </pre>
              </div>
            </>
          ) : (
            <p className="text-sm text-cns-muted">Select a deployment to view details and run actions.</p>
          )}
        </div>
      </div>

      {busy ? (
        <p className="flex items-center gap-2 text-sm text-cns-muted">
          <Spinner className="h-4 w-4" /> Working…
        </p>
      ) : null}
    </div>
  );
}
