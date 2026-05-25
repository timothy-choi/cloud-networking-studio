import { useCallback, useEffect, useState } from 'react';

import {
  confirmInfrastructureDeployment,
  createInfrastructureDeployment,
  destroyInfrastructureDeployment,
  listInfrastructureDeployments,
  listInfrastructureExecutions,
  listInfrastructureTemplates,
  type InfrastructureDeployment,
  type InfrastructureExecution,
  type InfrastructureTemplate,
} from '../../api/infrastructureDeployments';
import { ApiErrorDisplay } from '../errors/ApiErrorDisplay';
import { Spinner } from '../Spinner';

function statusTone(status: string): string {
  if (status === 'succeeded') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'failed') return 'text-red-700 dark:text-red-400';
  if (status === 'awaiting_confirmation') return 'text-amber-700 dark:text-amber-400';
  if (status === 'destroyed') return 'text-cns-muted';
  return 'text-cns-muted';
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
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    const [tpls, deps] = await Promise.all([
      listInfrastructureTemplates(),
      listInfrastructureDeployments(topologyId),
    ]);
    setTemplates(tpls);
    setDeployments(deps);
    if (!selectedId && deps.length > 0) {
      setSelectedId(deps[0].id);
    }
  }, [topologyId, selectedId]);

  useEffect(() => {
    void load().catch(setError);
  }, [load]);

  const selected = deployments.find((d) => d.id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedId) {
      setExecutions([]);
      return;
    }
    void listInfrastructureExecutions(selectedId)
      .then(setExecutions)
      .catch(setError);
  }, [selectedId, deployments]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createInfrastructureDeployment(topologyId, {
        name,
        template_id: templateId,
        provider,
        variables: { region, vm_count: vmCount },
      });
      setSelectedId(created.id);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await confirmInfrastructureDeployment(selected.id);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleDestroy() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await destroyInfrastructureDeployment(selected.id);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const plan = selected?.plan_summary_json as Record<string, unknown> | null | undefined;

  return (
    <div className="space-y-4">
      {error ? <ApiErrorDisplay error={error} /> : null}

      <form onSubmit={handleCreate} className="space-y-3 rounded-lg border p-3 dark:border-zinc-700">
        <div className="text-sm font-medium">New infrastructure deployment</div>
        <div className="grid gap-2 md:grid-cols-2">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Deployment name"
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          />
          <select
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          >
            {templates.map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.template_id}
              </option>
            ))}
          </select>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          >
            {(templates.find((t) => t.template_id === templateId)?.supported_providers ?? ['local']).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Region"
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          />
          <input
            type="number"
            min={1}
            max={10}
            value={vmCount}
            onChange={(e) => setVmCount(Number(e.target.value))}
            placeholder="VM count"
            className="rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-cns-accent px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Validate + Plan'}
        </button>
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
                    onClick={() => setSelectedId(d.id)}
                    className={`w-full rounded border px-3 py-2 text-left text-sm dark:border-zinc-700 ${
                      selectedId === d.id ? 'border-cns-accent' : ''
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
                  {selected.template_id} · {selected.provider} · <span className={statusTone(selected.status)}>{selected.status}</span>
                </p>
                {plan ? (
                  <div className="mt-2 space-y-1 text-xs">
                    <div>VM count: {String(plan.vm_count ?? '—')}</div>
                    <div>Region: {String(plan.region ?? '—')}</div>
                    <div>Exposed ports: {Array.isArray(plan.exposed_ports) ? plan.exposed_ports.join(', ') : '—'}</div>
                  </div>
                ) : null}
                {selected.status === 'awaiting_confirmation' ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleConfirm()}
                    className="mt-3 rounded bg-amber-600 px-3 py-1 text-sm text-white disabled:opacity-50"
                  >
                    Confirm apply
                  </button>
                ) : null}
                {selected.status === 'succeeded' ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDestroy()}
                    className="mt-3 rounded border border-red-500 px-3 py-1 text-sm text-red-600 disabled:opacity-50"
                  >
                    Destroy infrastructure
                  </button>
                ) : null}
              </div>

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

              <div className="rounded-lg border p-3 dark:border-zinc-700">
                <div className="text-sm font-medium">Executions</div>
                {executions.length === 0 ? (
                  <p className="text-xs text-cns-muted">No executions recorded.</p>
                ) : (
                  <ul className="mt-2 space-y-2 text-xs">
                    {executions.map((ex) => (
                      <li key={ex.id} className="rounded border p-2 dark:border-zinc-700">
                        <div>
                          {ex.execution_type}/{ex.mode} · {ex.status}
                          {ex.duration_ms != null ? ` · ${ex.duration_ms}ms` : ''}
                        </div>
                        {ex.logs ? (
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-[11px] text-cns-muted">
                            {ex.logs.slice(0, 1200)}
                          </pre>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-cns-muted">Select a deployment to view details.</p>
          )}
        </div>
      </div>

      {busy ? (
        <p className="flex items-center gap-2 text-sm text-cns-muted">
          <Spinner className="h-4 w-4" /> Running infrastructure workflow…
        </p>
      ) : null}
    </div>
  );
}
