export type InfrastructureCreateFormValues = {
  name: string;
  templateId: string;
  provider: string;
  region: string;
  vmCount: number;
  credentialsRef: string;
  // GCP docker-vm
  projectId: string;
  zone: string;
  machineType: string;
  networkName: string;
  instanceName: string;
  sshUser: string;
  allowedSshCidr: string;
  allowedAppCidr: string;
  tags: string;
};

export type InfrastructureCreateFormErrors = Partial<
  Record<
    | 'name'
    | 'templateId'
    | 'provider'
    | 'region'
    | 'vmCount'
    | 'credentialsRef'
    | 'projectId'
    | 'zone'
    | 'machineType'
    | 'networkName'
    | 'instanceName'
    | 'sshUser'
    | 'allowedSshCidr'
    | 'allowedAppCidr'
    | 'tags',
    string
  >
>;

export type ApplySafetyChecklistItem = {
  name: string;
  ok: boolean;
  warning?: boolean;
  message: string;
};

export type ApplySafetyChecklist = {
  passed?: boolean;
  items?: ApplySafetyChecklistItem[];
  apply_eligible?: boolean;
  cost_warning?: string | null;
};

export const REAL_CLOUD_PROVIDERS = new Set(['gcp', 'aws', 'azure']);

export function isRealCloudProvider(provider: string): boolean {
  return REAL_CLOUD_PROVIDERS.has(provider);
}

export function isGcpDockerVmDeployment(templateId: string, provider: string): boolean {
  return templateId === 'docker-vm' && provider === 'gcp';
}

export function isGcpDockerVmForm(templateId: string, provider: string): boolean {
  return isGcpDockerVmDeployment(templateId, provider);
}

export function defaultInfrastructureFormValues(): InfrastructureCreateFormValues {
  return {
    name: 'infra-stack',
    templateId: 'local-mock',
    provider: 'local',
    region: 'local',
    vmCount: 1,
    credentialsRef: '',
    projectId: '',
    zone: '',
    machineType: 'e2-medium',
    networkName: 'default',
    instanceName: 'cns-docker-vm',
    sshUser: 'ubuntu',
    allowedSshCidr: '203.0.113.0/24',
    allowedAppCidr: '203.0.113.0/24',
    tags: 'cns-docker-vm',
  };
}

export function validateInfrastructureCreateForm(
  values: InfrastructureCreateFormValues,
): InfrastructureCreateFormErrors {
  const errors: InfrastructureCreateFormErrors = {};
  if (!values.name.trim()) {
    errors.name = 'Deployment name is required';
  }
  if (!values.templateId.trim()) {
    errors.templateId = 'Template is required';
  }
  if (!values.provider.trim()) {
    errors.provider = 'Provider is required';
  }
  if (!values.region.trim()) {
    errors.region = 'Region is required';
  }
  if (!Number.isFinite(values.vmCount) || values.vmCount < 1 || values.vmCount > 10) {
    errors.vmCount = 'VM count must be between 1 and 10';
  }

  if (isRealCloudProvider(values.provider)) {
    if (!values.credentialsRef.trim()) {
      errors.credentialsRef = 'credentials_ref is required for cloud providers';
    }
  }

  if (isGcpDockerVmForm(values.templateId, values.provider)) {
    if (!values.projectId.trim()) errors.projectId = 'GCP project ID is required';
    if (!values.zone.trim()) errors.zone = 'Zone is required';
    if (!values.instanceName.trim()) errors.instanceName = 'Instance name is required';
    if (!values.allowedSshCidr.trim()) errors.allowedSshCidr = 'SSH CIDR is required';
    if (!values.allowedAppCidr.trim()) errors.allowedAppCidr = 'App CIDR is required';
  }

  return errors;
}

export function buildInfrastructureCreatePayload(values: InfrastructureCreateFormValues) {
  const base = {
    name: values.name.trim(),
    template_id: values.templateId,
    provider: values.provider,
    variables: { region: values.region.trim(), vm_count: values.vmCount } as Record<string, unknown>,
  };

  if (isGcpDockerVmForm(values.templateId, values.provider)) {
    base.variables = {
      project_id: values.projectId.trim(),
      region: values.region.trim(),
      zone: values.zone.trim(),
      machine_type: values.machineType.trim() || 'e2-medium',
      network_name: values.networkName.trim() || 'default',
      instance_name: values.instanceName.trim(),
      ssh_user: values.sshUser.trim() || 'ubuntu',
      allowed_ssh_cidr: values.allowedSshCidr.trim(),
      allowed_app_cidr: values.allowedAppCidr.trim(),
      tags: values.tags.trim() || 'cns-docker-vm',
      vm_count: values.vmCount,
    };
  }

  const payload: {
    name: string;
    template_id: string;
    provider: string;
    variables: Record<string, unknown>;
    credentials_ref?: string;
  } = base;

  const credRef = (values.credentialsRef ?? '').trim();
  if (credRef) {
    payload.credentials_ref = credRef;
  }

  return payload;
}

export function extractApplySafetyChecklist(
  planSummary: Record<string, unknown> | null | undefined,
): ApplySafetyChecklist | null {
  const checklist = planSummary?.safety_checklist;
  if (!checklist || typeof checklist !== 'object') {
    return null;
  }
  return checklist as ApplySafetyChecklist;
}

export function hasTerraformApplyStarted(
  stateMetadata: Record<string, unknown> | null | undefined,
): boolean {
  const meta = stateMetadata ?? {};
  const phases = (meta.phases as Record<string, unknown> | undefined) ?? {};
  return Boolean(meta.terraform_apply_started || phases.terraform_apply_started);
}

export function hasTerraformApplyCompleted(
  stateMetadata: Record<string, unknown> | null | undefined,
): boolean {
  const meta = stateMetadata ?? {};
  const phases = (meta.phases as Record<string, unknown> | undefined) ?? {};
  return Boolean(
    meta.terraform_apply_completed ||
      phases.terraform_apply_completed ||
      meta.applied_at ||
      meta.apply_execution_id,
  );
}

export function hasTerraformResources(
  stateMetadata: Record<string, unknown> | null | undefined,
): boolean {
  return hasTerraformApplyStarted(stateMetadata) || hasTerraformApplyCompleted(stateMetadata);
}

export const RECOVERY_MESSAGE =
  'Terraform created cloud resources, but configuration did not finish. Retry configuration or destroy infrastructure.';

export type InfraPhaseChecklistItem = {
  name: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
};

export function extractPhaseChecklist(
  stateMetadata: Record<string, unknown> | null | undefined,
): InfraPhaseChecklistItem[] {
  const raw = stateMetadata?.phase_checklist;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter((item): item is InfraPhaseChecklistItem => typeof item === 'object' && item !== null)
    .map((item) => ({
      name: String(item.name ?? ''),
      label: String(item.label ?? ''),
      status: (['pending', 'running', 'completed', 'failed'].includes(String(item.status))
        ? item.status
        : 'pending') as InfraPhaseChecklistItem['status'],
    }));
}

export function extractRecoveryMessage(
  stateMetadata: Record<string, unknown> | null | undefined,
): string | null {
  const message = stateMetadata?.recovery_message;
  return typeof message === 'string' && message.trim() ? message : null;
}

export function canShowApplyAction(
  status: string,
  templateId: string,
  provider: string,
  planSummary: Record<string, unknown> | null | undefined,
  stateMetadata?: Record<string, unknown> | null,
): boolean {
  if (hasTerraformResources(stateMetadata)) {
    return false;
  }
  if (status !== 'awaiting_confirmation') {
    return false;
  }
  if (isGcpDockerVmDeployment(templateId, provider)) {
    const checklist = extractApplySafetyChecklist(planSummary);
    return checklist?.passed === true && planSummary?.apply_eligible === true;
  }
  if (isRealCloudProvider(provider)) {
    return false;
  }
  return true;
}

export function applyDisabledReason(
  status: string,
  templateId: string,
  provider: string,
  planSummary: Record<string, unknown> | null | undefined,
): string | null {
  if (status !== 'awaiting_confirmation') {
    return null;
  }
  if (isGcpDockerVmDeployment(templateId, provider)) {
    const checklist = extractApplySafetyChecklist(planSummary);
    if (!checklist) {
      return 'Run Plan first to generate a safety checklist.';
    }
    if (!checklist.passed) {
      const failed = (checklist.items ?? []).filter((item) => !item.ok && !item.warning);
      if (failed.length > 0) {
        return failed[0]?.message ?? 'Safety checks failed.';
      }
      return 'Safety checks failed.';
    }
    return null;
  }
  if (isRealCloudProvider(provider)) {
    return 'Apply disabled: real cloud apply is not enabled for this provider.';
  }
  return null;
}

export const POST_APPLY_DESTROYABLE_STATUSES = new Set([
  'succeeded',
  'configuration_failed',
  'registration_failed',
  'apply_partial',
  'configuration_timeout',
  'destroy_failed',
  'failed',
  'applying',
  'configuring',
]);

export function canDestroyInfrastructureDeployment(
  status: string,
  templateId: string,
  provider: string,
  stateMetadata: Record<string, unknown> | null | undefined,
): boolean {
  if (status === 'destroyed' || status === 'destroying') {
    return true;
  }
  if (isMockInfrastructureDeployment(templateId, provider)) {
    return status === 'succeeded';
  }
  if (!hasTerraformResources(stateMetadata)) {
    return false;
  }
  return POST_APPLY_DESTROYABLE_STATUSES.has(status) || hasTerraformApplyCompleted(stateMetadata);
}

export const CONFIGURATION_START_TIMEOUT_MS = 15_000;

export function hasConfigurationProgressStarted(
  stateMetadata: Record<string, unknown> | null | undefined,
  eventTypes: string[],
): boolean {
  const meta = stateMetadata ?? {};
  const phases = (meta.phases as Record<string, unknown> | undefined) ?? {};
  return (
    eventTypes.includes('ssh_readiness_started') ||
    eventTypes.includes('configure_started') ||
    Boolean(phases.ssh_readiness_started || phases.configuration_started)
  );
}

export function isConfigurationJobStuck(
  status: string,
  stateMetadata: Record<string, unknown> | null | undefined,
  eventTypes: string[],
  nowMs: number = Date.now(),
): boolean {
  if (!hasTerraformApplyCompleted(stateMetadata)) {
    return false;
  }
  if (status !== 'configuring' && status !== 'applying') {
    return false;
  }
  if (hasConfigurationProgressStarted(stateMetadata, eventTypes)) {
    return false;
  }
  const meta = stateMetadata ?? {};
  const queuedAt = meta.configuration_queued_at;
  if (!queuedAt && !eventTypes.includes('configuration_queued')) {
    return true;
  }
  if (!queuedAt) {
    return true;
  }
  const queuedMs = Date.parse(String(queuedAt));
  if (Number.isNaN(queuedMs)) {
    return true;
  }
  return nowMs - queuedMs >= CONFIGURATION_START_TIMEOUT_MS;
}

export function shouldPollInfrastructureDeployment(status: string): boolean {
  return status === 'configuring' || status === 'applying';
}

export function canShowRetryConfigurationAction(
  status: string,
  stateMetadata?: Record<string, unknown> | null,
  eventTypes: string[] = [],
  nowMs?: number,
): boolean {
  if (!hasTerraformApplyCompleted(stateMetadata)) {
    return false;
  }
  if (
    status === 'configuration_failed' ||
    status === 'registration_failed' ||
    status === 'apply_partial' ||
    status === 'configuration_timeout'
  ) {
    return true;
  }
  if (status === 'applying' || status === 'configuring') {
    return isConfigurationJobStuck(status, stateMetadata, eventTypes, nowMs);
  }
  return false;
}

export function canShowForceMetadataCleanupAction(
  status: string,
  stateMetadata?: Record<string, unknown> | null,
): boolean {
  if (!hasTerraformResources(stateMetadata)) {
    return false;
  }
  const meta = stateMetadata ?? {};
  const hasWorkspace = Boolean(meta.workspace_id || meta.plan_file || meta.terraform_workspace_path);
  return !hasWorkspace && status !== 'destroyed' && status !== 'destroying';
}

export function canShowDestroyAction(
  status: string,
  templateId: string,
  provider: string,
  stateMetadata?: Record<string, unknown> | null,
): boolean {
  return canDestroyInfrastructureDeployment(status, templateId, provider, stateMetadata);
}

export function destroyDisabledReason(
  status: string,
  templateId: string,
  provider: string,
  stateMetadata?: Record<string, unknown> | null,
): string | null {
  if (canDestroyInfrastructureDeployment(status, templateId, provider, stateMetadata)) {
    return null;
  }
  if (isGcpDockerVmDeployment(templateId, provider)) {
    return 'Nothing to destroy: deployment has not been applied.';
  }
  if (isRealCloudProvider(provider)) {
    return 'Nothing to destroy: plan-only deployment.';
  }
  return null;
}

export function canShowPlanAction(status: string): boolean {
  return status === 'validated' || status === 'pending' || status === 'failed';
}

export function canShowValidateAction(status: string): boolean {
  return status === 'pending' || status === 'failed';
}

export function deriveTerraformStatus(
  status: string,
  eventTypes: string[],
): string {
  if (
    eventTypes.includes('apply_completed') ||
    status === 'configuring' ||
    status === 'succeeded' ||
    status === 'configuration_failed' ||
    status === 'configuration_timeout' ||
    status === 'apply_partial' ||
    status === 'registration_failed'
  ) {
    return 'applied';
  }
  if (status === 'applying' || eventTypes.includes('apply_started')) {
    return 'applying';
  }
  if (status === 'awaiting_confirmation' || eventTypes.includes('plan_completed')) {
    return 'planned (awaiting confirmation)';
  }
  if (status === 'validated' || eventTypes.includes('validate_completed')) {
    return 'validated';
  }
  if (status === 'failed') {
    return 'failed';
  }
  return 'pending';
}

export function deriveConfigurationStatus(
  status: string,
  eventTypes: string[],
): string {
  if (status === 'configuration_failed' || status === 'configuration_timeout' || eventTypes.includes('configure_failed')) {
    return 'failed';
  }
  if (status === 'registration_failed' || eventTypes.includes('registration_failed')) {
    return 'registration_failed';
  }
  if (eventTypes.includes('runtime_ready') || status === 'succeeded') {
    return 'completed';
  }
  if (status === 'configuring' || eventTypes.includes('configure_started')) {
    return eventTypes.includes('configure_completed') ? 'completed' : 'running';
  }
  if (status === 'awaiting_confirmation' || status === 'pending' || status === 'applying' || status === 'validated') {
    return 'not started';
  }
  if (status === 'failed') {
    return 'failed';
  }
  return 'pending';
}

export function isMockInfrastructureDeployment(templateId: string, provider: string): boolean {
  return templateId === 'local-mock' || provider === 'local' || provider === 'mock';
}

export function credentialsRefHelpText(provider: string): string {
  if (provider === 'gcp') {
    return 'Select a credential profile, or enter a platform-admin ref such as env:GOOGLE_APPLICATION_CREDENTIALS.';
  }
  if (provider === 'aws') {
    return 'Select a credential profile, or enter env:AWS_PROFILE / env:AWS_ACCESS_KEY_ID for platform-managed credentials.';
  }
  if (provider === 'azure') {
    return 'Select an Azure credential profile (credential:<profile_id>).';
  }
  return 'Not required for local/mock providers.';
}

export function hasOpenInternetCidr(variables: Record<string, unknown> | undefined): boolean {
  const ssh = String(variables?.allowed_ssh_cidr ?? '').trim();
  const app = String(variables?.allowed_app_cidr ?? '').trim();
  return ssh === '0.0.0.0/0' || app === '0.0.0.0/0';
}
