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
  applyDisabledReason,
  buildInfrastructureCreatePayload,
  canShowApplyAction,
  canShowDestroyAction,
  canShowPlanAction,
  canShowValidateAction,
  credentialsRefHelpText,
  defaultInfrastructureFormValues,
  deriveConfigurationStatus,
  deriveTerraformStatus,
  destroyDisabledReason,
  extractApplySafetyChecklist,
  hasOpenInternetCidr,
  isGcpDockerVmDeployment,
  isGcpDockerVmForm,
  isMockInfrastructureDeployment,
  isRealCloudProvider,
  validateInfrastructureCreateForm,
  type InfrastructureCreateFormErrors,
  type InfrastructureCreateFormValues,
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
  values: InfrastructureCreateFormValues,
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
  onUseRuntimeTarget,
  onRuntimeTargetsChanged,
}: {
  topologyId: string;
  onUseRuntimeTarget?: (targetId: string) => void;
  onRuntimeTargetsChanged?: () => void;
}) {
  const [templates, setTemplates] = useState<InfrastructureTemplate[]>([]);
  const [deployments, setDeployments] = useState<InfrastructureDeployment[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [executions, setExecutions] = useState<InfrastructureExecution[]>([]);
  const defaults = defaultInfrastructureFormValues();
  const [name, setName] = useState(defaults.name);
  const [templateId, setTemplateId] = useState(defaults.templateId);
  const [provider, setProvider] = useState(defaults.provider);
  const [region, setRegion] = useState(defaults.region);
  const [vmCount, setVmCount] = useState(defaults.vmCount);
  const [credentialsRef, setCredentialsRef] = useState(defaults.credentialsRef);
  const [projectId, setProjectId] = useState(defaults.projectId);
  const [zone, setZone] = useState(defaults.zone);
  const [machineType, setMachineType] = useState(defaults.machineType);
  const [networkName, setNetworkName] = useState(defaults.networkName);
  const [instanceName, setInstanceName] = useState(defaults.instanceName);
  const [sshUser, setSshUser] = useState(defaults.sshUser);
  const [allowedSshCidr, setAllowedSshCidr] = useState(defaults.allowedSshCidr);
  const [allowedAppCidr, setAllowedAppCidr] = useState(defaults.allowedAppCidr);
  const [tags, setTags] = useState(defaults.tags);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<InfrastructureCreateFormErrors>({});
  const [showLogs, setShowLogs] = useState(false);
  const [applyConfirmText, setApplyConfirmText] = useState('');
  const [destroyConfirmText, setDestroyConfirmText] = useState('');
  const [unsafeTestingOverride, setUnsafeTestingOverride] = useState(false);
  const [showApplyDialog, setShowApplyDialog] = useState(false);
  const [showDestroyDialog, setShowDestroyDialog] = useState(false);

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
    const values: InfrastructureCreateFormValues = {
      name,
      templateId,
      provider,
      region,
      vmCount,
      credentialsRef,
      projectId,
      zone,
      machineType,
      networkName,
      instanceName,
      sshUser,
      allowedSshCidr,
      allowedAppCidr,
      tags,
    };
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
    const needsTypedConfirm = isGcpDockerVmDeployment(selected.template_id, selected.provider);
    if (needsTypedConfirm && applyConfirmText.trim() !== 'APPLY') {
      setError(new Error('Type APPLY to confirm real cloud apply.'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await confirmInfrastructureDeployment(selected.id, {
        confirmation_text: needsTypedConfirm ? applyConfirmText.trim() : undefined,
        unsafe_testing_override: needsTypedConfirm ? unsafeTestingOverride : undefined,
      });
      setDeployments((current) => current.map((d) => (d.id === updated.id ? updated : d)));
      await refreshExecutions(updated.id);
      setShowApplyDialog(false);
      setApplyConfirmText('');
      setUnsafeTestingOverride(false);
      onRuntimeTargetsChanged?.();
    } catch (err) {
      setError(err);
      await refreshDeployments(selected.id);
      await refreshExecutions(selected.id);
    } finally {
      setBusy(false);
    }
  }

  async function handleDestroy() {
    if (!selected) return;
    const needsTypedConfirm = isGcpDockerVmDeployment(selected.template_id, selected.provider);
    if (needsTypedConfirm && destroyConfirmText.trim() !== 'DESTROY') {
      setError(new Error('Type DESTROY to confirm infrastructure destroy.'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await destroyInfrastructureDeployment(selected.id, {
        confirmation_text: needsTypedConfirm ? destroyConfirmText.trim() : undefined,
      });
      setDeployments((current) => current.map((d) => (d.id === updated.id ? updated : d)));
      setShowDestroyDialog(false);
      setDestroyConfirmText('');
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const plan = selected?.plan_summary_json as Record<string, unknown> | null | undefined;
  const eventTypes = (selected?.events_json ?? []).map((ev) => ev.type);
  const terraformStatus = selected ? deriveTerraformStatus(selected.status, eventTypes) : null;
  const configurationStatus = selected ? deriveConfigurationStatus(selected.status, eventTypes) : null;
  const runtimeTargets = selected?.runtime_targets_json ?? [];
  const isMockDeployment = selected
    ? isMockInfrastructureDeployment(selected.template_id, selected.provider)
    : false;
  const isGcpDeployment = selected
    ? isGcpDockerVmDeployment(selected.template_id, selected.provider)
    : false;
  const safetyChecklist = extractApplySafetyChecklist(plan);
  const applyDisabled = selected
    ? applyDisabledReason(selected.status, selected.template_id, selected.provider, plan)
    : null;
  const destroyDisabled = selected
    ? destroyDisabledReason(selected.status, selected.provider, selected.template_id)
    : null;
  const showApplyButton = selected
    ? canShowApplyAction(selected.status, selected.template_id, selected.provider, plan)
    : false;
  const showDestroyButton = selected
    ? canShowDestroyAction(selected.status, selected.provider, selected.template_id)
    : false;
  const openCidrWarning =
    isGcpDeployment && hasOpenInternetCidr(selected?.variables_json as Record<string, unknown> | undefined);
  const showGcpFields = isGcpDockerVmForm(templateId, provider);
  const showCredentialsRef = isRealCloudProvider(provider);
  const targetSkipEvent = [...(selected?.events_json ?? [])]
    .reverse()
    .find(
      (ev) =>
        ev.type === 'runtime_target_creation_skipped' || ev.type === 'runtime_target_creation_failed',
    );
  const combinedLogs = executions
    .map((ex) => `[${ex.execution_type}/${ex.mode}] ${ex.logs ?? ''}`.trim())
    .filter(Boolean)
    .join('\n\n');

  return (
    <div className="space-y-4">
      {error ? <ApiErrorDisplay error={error} /> : null}

      <div className="rounded-lg border border-blue-200 bg-blue-50/80 px-3 py-2 text-xs text-blue-950 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-100">
        <strong>Infrastructure deployments</strong> use Terraform to provision cloud/VM/network resources,
        then Ansible to configure hosts. After apply completes, CNS can register{' '}
        <strong>runtime targets</strong> (<code className="font-mono">remote_docker</code>) for workload
        deployments in the External Deployments section.
      </div>

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
          {showGcpFields ? (
            <>
              <div>
                <input
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="GCP project ID"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
                {fieldErrors.projectId ? (
                  <p className="mt-1 text-xs text-red-600">{fieldErrors.projectId}</p>
                ) : null}
              </div>
              <div>
                <input
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                  placeholder="Zone (e.g. us-central1-a)"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
                {fieldErrors.zone ? <p className="mt-1 text-xs text-red-600">{fieldErrors.zone}</p> : null}
              </div>
              <div>
                <input
                  value={machineType}
                  onChange={(e) => setMachineType(e.target.value)}
                  placeholder="Machine type"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
              </div>
              <div>
                <input
                  value={networkName}
                  onChange={(e) => setNetworkName(e.target.value)}
                  placeholder="VPC network name"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
              </div>
              <div>
                <input
                  value={instanceName}
                  onChange={(e) => setInstanceName(e.target.value)}
                  placeholder="Instance name"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
                {fieldErrors.instanceName ? (
                  <p className="mt-1 text-xs text-red-600">{fieldErrors.instanceName}</p>
                ) : null}
              </div>
              <div>
                <input
                  value={sshUser}
                  onChange={(e) => setSshUser(e.target.value)}
                  placeholder="SSH user"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
              </div>
              <div>
                <input
                  value={allowedSshCidr}
                  onChange={(e) => setAllowedSshCidr(e.target.value)}
                  placeholder="Allowed SSH CIDR"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
                {fieldErrors.allowedSshCidr ? (
                  <p className="mt-1 text-xs text-red-600">{fieldErrors.allowedSshCidr}</p>
                ) : null}
              </div>
              <div>
                <input
                  value={allowedAppCidr}
                  onChange={(e) => setAllowedAppCidr(e.target.value)}
                  placeholder="Allowed app CIDR"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
                {fieldErrors.allowedAppCidr ? (
                  <p className="mt-1 text-xs text-red-600">{fieldErrors.allowedAppCidr}</p>
                ) : null}
              </div>
              <div>
                <input
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="Network tags (comma-separated)"
                  className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                />
              </div>
            </>
          ) : null}
          {showCredentialsRef ? (
            <div className="md:col-span-2">
              <input
                value={credentialsRef}
                onChange={(e) => setCredentialsRef(e.target.value)}
                placeholder="credentials_ref (e.g. env:GOOGLE_APPLICATION_CREDENTIALS)"
                className="w-full rounded border px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              />
              <p className="mt-1 text-xs text-cns-muted">{credentialsRefHelpText(provider)}</p>
              {fieldErrors.credentialsRef ? (
                <p className="mt-1 text-xs text-red-600">{fieldErrors.credentialsRef}</p>
              ) : null}
            </div>
          ) : null}
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
                    <div>Provider: {String(plan.provider ?? selected.provider)}</div>
                    <div>Template: {String(plan.template_id ?? selected.template_id)}</div>
                    <div>VM count: {String(plan.vm_count ?? '—')}</div>
                    <div>Region: {String(plan.region ?? '—')}</div>
                    <div>Zone: {String(plan.zone ?? '—')}</div>
                    <div>Machine type: {String(plan.machine_type ?? '—')}</div>
                    <div>
                      Exposed ports: {Array.isArray(plan.exposed_ports) ? plan.exposed_ports.join(', ') : '—'}
                    </div>
                    {Array.isArray(plan.firewall_rules) && plan.firewall_rules.length > 0 ? (
                      <div>Firewall rules: {(plan.firewall_rules as string[]).join(', ')}</div>
                    ) : null}
                    {plan.estimated_resources && typeof plan.estimated_resources === 'object' ? (
                      <div>
                        Estimated resources:{' '}
                        {Object.entries(plan.estimated_resources as Record<string, unknown>)
                          .map(([k, v]) => `${k}=${String(v)}`)
                          .join(', ')}
                      </div>
                    ) : null}
                    {Array.isArray(plan.warnings) && plan.warnings.length > 0 ? (
                      <div className="text-amber-700 dark:text-amber-300">
                        Warnings: {(plan.warnings as string[]).join(' · ')}
                      </div>
                    ) : null}
                    {plan.cost_warning ? (
                      <div className="font-medium text-amber-800 dark:text-amber-200">
                        {String(plan.cost_warning)}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {safetyChecklist?.items && safetyChecklist.items.length > 0 ? (
                  <div className="mt-3 rounded border border-amber-500/40 bg-amber-50/50 p-2 text-xs dark:border-amber-700/50 dark:bg-amber-950/20">
                    <div className="font-medium">Apply safety checklist</div>
                    <ul className="mt-2 space-y-1">
                      {safetyChecklist.items.map((item) => (
                        <li
                          key={item.name}
                          className={
                            item.warning
                              ? 'text-amber-800 dark:text-amber-200'
                              : item.ok
                                ? 'text-emerald-700 dark:text-emerald-400'
                                : 'text-red-700 dark:text-red-400'
                          }
                        >
                          {item.ok ? '✓' : item.warning ? '⚠' : '✗'} {item.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {openCidrWarning ? (
                  <p className="mt-2 text-xs text-amber-800 dark:text-amber-200">
                    Warning: open CIDR (0.0.0.0/0) detected. Apply requires explicit unsafe testing override.
                  </p>
                ) : null}
                {selected.outputs_json && Object.keys(selected.outputs_json).length > 0 ? (
                  <div className="mt-2 space-y-1 text-xs">
                    <div className="font-medium">Terraform outputs</div>
                    {selected.outputs_json.public_ip ? (
                      <div>Public IP: {String(selected.outputs_json.public_ip)}</div>
                    ) : null}
                    {selected.outputs_json.private_ip ? (
                      <div>Private IP: {String(selected.outputs_json.private_ip)}</div>
                    ) : null}
                    {selected.outputs_json.instance_name ? (
                      <div>Instance: {String(selected.outputs_json.instance_name)}</div>
                    ) : null}
                    {selected.outputs_json.zone ? <div>Zone: {String(selected.outputs_json.zone)}</div> : null}
                    {selected.outputs_json.network_name ? (
                      <div>Network: {String(selected.outputs_json.network_name)}</div>
                    ) : null}
                    {selected.outputs_json.ssh_user ? (
                      <div>SSH user: {String(selected.outputs_json.ssh_user)}</div>
                    ) : null}
                  </div>
                ) : null}
                {selected.credentials_ref ? (
                  <p className="mt-2 text-xs text-cns-muted">
                    credentials_ref: <code className="font-mono">{selected.credentials_ref}</code>
                  </p>
                ) : null}

                <div className="mt-3 grid gap-2 rounded border border-zinc-200 p-2 text-xs dark:border-zinc-700">
                  <div>
                    <span className="font-medium">Terraform:</span>{' '}
                    <span className={statusTone(terraformStatus === 'failed' ? 'failed' : 'succeeded')}>
                      {terraformStatus}
                    </span>
                  </div>
                  <div>
                    <span className="font-medium">Ansible / configuration:</span>{' '}
                    <span
                      className={statusTone(
                        configurationStatus === 'failed'
                          ? 'failed'
                          : configurationStatus === 'completed'
                            ? 'succeeded'
                            : configurationStatus === 'running'
                              ? 'awaiting_confirmation'
                              : 'pending',
                      )}
                    >
                      {configurationStatus}
                    </span>
                  </div>
                </div>

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
                  {showApplyButton ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (isGcpDeployment) {
                          setShowApplyDialog(true);
                        } else {
                          void handleConfirm();
                        }
                      }}
                      className="rounded bg-amber-600 px-3 py-1 text-xs text-white disabled:opacity-50"
                    >
                      Confirm apply
                    </button>
                  ) : applyDisabled && selected.status === 'awaiting_confirmation' ? (
                    <span className="rounded border border-amber-500/50 px-3 py-1 text-xs text-amber-700 dark:text-amber-300">
                      {applyDisabled}
                    </span>
                  ) : null}
                  {showDestroyButton ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (isGcpDeployment) {
                          setShowDestroyDialog(true);
                        } else {
                          void handleDestroy();
                        }
                      }}
                      className="rounded border border-red-500 px-3 py-1 text-xs text-red-600 disabled:opacity-50"
                    >
                      Destroy infrastructure
                    </button>
                  ) : destroyDisabled ? (
                    <span className="rounded border border-zinc-400/50 px-3 py-1 text-xs text-cns-muted">
                      {destroyDisabled}
                    </span>
                  ) : null}
                </div>
                {showApplyDialog && isGcpDeployment ? (
                  <div className="mt-3 space-y-2 rounded border border-amber-500/50 bg-amber-50/40 p-3 text-xs dark:border-amber-700/50 dark:bg-amber-950/20">
                    <p className="font-medium text-amber-900 dark:text-amber-100">
                      This may create billable cloud resources.
                    </p>
                    <p>Type <strong>APPLY</strong> to confirm Terraform apply using the stored plan.</p>
                    <input
                      value={applyConfirmText}
                      onChange={(e) => setApplyConfirmText(e.target.value)}
                      placeholder="Type APPLY"
                      className="w-full rounded border px-2 py-1 font-mono dark:border-zinc-600 dark:bg-zinc-900"
                    />
                    {openCidrWarning ? (
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={unsafeTestingOverride}
                          onChange={(e) => setUnsafeTestingOverride(e.target.checked)}
                        />
                        Allow open CIDR (0.0.0.0/0) for testing only
                      </label>
                    ) : null}
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy || applyConfirmText.trim() !== 'APPLY'}
                        onClick={() => void handleConfirm()}
                        className="rounded bg-amber-600 px-3 py-1 text-white disabled:opacity-50"
                      >
                        Apply infrastructure
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setShowApplyDialog(false);
                          setApplyConfirmText('');
                          setUnsafeTestingOverride(false);
                        }}
                        className="rounded border px-3 py-1 dark:border-zinc-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
                {showDestroyDialog && isGcpDeployment ? (
                  <div className="mt-3 space-y-2 rounded border border-red-500/50 bg-red-50/40 p-3 text-xs dark:border-red-800/50 dark:bg-red-950/20">
                    <p className="font-medium text-red-900 dark:text-red-100">
                      Destroy will remove GCP resources created by this deployment.
                    </p>
                    <p>Type <strong>DESTROY</strong> to confirm.</p>
                    <input
                      value={destroyConfirmText}
                      onChange={(e) => setDestroyConfirmText(e.target.value)}
                      placeholder="Type DESTROY"
                      className="w-full rounded border px-2 py-1 font-mono dark:border-zinc-600 dark:bg-zinc-900"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy || destroyConfirmText.trim() !== 'DESTROY'}
                        onClick={() => void handleDestroy()}
                        className="rounded border border-red-600 px-3 py-1 text-red-700 disabled:opacity-50 dark:text-red-300"
                      >
                        Destroy infrastructure
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setShowDestroyDialog(false);
                          setDestroyConfirmText('');
                        }}
                        className="rounded border px-3 py-1 dark:border-zinc-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
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
                <p className="mt-1 text-xs text-cns-muted">
                  After Terraform apply and Ansible configuration, registered targets can be used for
                  topology workload deployments.
                </p>
                {runtimeTargets.length === 0 ? (
                  <p className="mt-2 text-xs text-cns-muted">
                    {targetSkipEvent?.message
                      ? `No runtime target created: ${targetSkipEvent.message}`
                      : isMockDeployment
                        ? 'No runtime target created for mock deployment.'
                        : 'No runtime targets registered yet.'}
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2 text-xs">
                    {runtimeTargets.map((target) => {
                      const row = target as {
                        target_id?: string;
                        name?: string;
                        host?: string;
                        target_type?: string;
                        is_mock?: boolean;
                      };
                      return (
                        <li
                          key={row.target_id ?? row.name}
                          className="rounded border px-2 py-1 dark:border-zinc-700"
                        >
                          <div className="font-medium">{row.name ?? 'runtime target'}</div>
                          <div className="text-cns-muted">
                            {row.target_type ?? 'remote_docker'}
                            {row.host ? ` · ${row.host}` : ''}
                          </div>
                          {row.is_mock || isMockDeployment ? (
                            <div className="mt-1 text-amber-700 dark:text-amber-300">
                              Mock target — workflow testing only
                            </div>
                          ) : null}
                          {row.target_id && onUseRuntimeTarget ? (
                            <button
                              type="button"
                              className="mt-1 rounded bg-emerald-700 px-2 py-0.5 text-[11px] text-white"
                              onClick={() => onUseRuntimeTarget(row.target_id!)}
                            >
                              Use created target for topology deploy
                            </button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
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
