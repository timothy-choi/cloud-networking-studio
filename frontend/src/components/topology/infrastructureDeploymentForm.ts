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

export const REAL_CLOUD_PROVIDERS = new Set(['gcp', 'aws']);

export function isRealCloudProvider(provider: string): boolean {
  return REAL_CLOUD_PROVIDERS.has(provider);
}

export function isGcpDockerVmForm(templateId: string, provider: string): boolean {
  return templateId === 'docker-vm' && provider === 'gcp';
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
    allowedSshCidr: '0.0.0.0/0',
    allowedAppCidr: '0.0.0.0/0',
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

export function canShowApplyAction(status: string, provider: string): boolean {
  if (isRealCloudProvider(provider)) {
    return false;
  }
  return status === 'awaiting_confirmation';
}

export function applyDisabledReason(provider: string): string | null {
  if (isRealCloudProvider(provider)) {
    return 'Apply disabled: real cloud apply will be enabled in a later step.';
  }
  return null;
}

export function canShowDestroyAction(status: string, provider: string): boolean {
  if (isRealCloudProvider(provider)) {
    return status === 'succeeded';
  }
  return status === 'succeeded';
}

export function destroyDisabledReason(status: string, provider: string): string | null {
  if (isRealCloudProvider(provider) && status !== 'succeeded') {
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
  if (eventTypes.includes('apply_completed') || status === 'configuring' || status === 'succeeded') {
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
    return 'Use env:GOOGLE_APPLICATION_CREDENTIALS (service account file path on server) or env:GOOGLE_CREDENTIALS_JSON.';
  }
  if (provider === 'aws') {
    return 'Use env:AWS_PROFILE or env:AWS_ACCESS_KEY_ID (requires AWS_SECRET_ACCESS_KEY on server).';
  }
  return 'Not required for local/mock providers.';
}
