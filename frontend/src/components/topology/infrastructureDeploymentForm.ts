export type InfrastructureCreateFormValues = {
  name: string;
  templateId: string;
  provider: string;
  region: string;
  vmCount: number;
};

export type InfrastructureCreateFormErrors = Partial<
  Record<'name' | 'templateId' | 'provider' | 'region' | 'vmCount', string>
>;

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
  return errors;
}

export function buildInfrastructureCreatePayload(values: InfrastructureCreateFormValues) {
  return {
    name: values.name.trim(),
    template_id: values.templateId,
    provider: values.provider,
    variables: { region: values.region.trim(), vm_count: values.vmCount },
  };
}

export function canShowApplyAction(status: string): boolean {
  return status === 'awaiting_confirmation';
}

export function canShowPlanAction(status: string): boolean {
  return status === 'pending' || status === 'failed';
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
  if (eventTypes.includes('validate_completed')) {
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
  if (status === 'awaiting_confirmation' || status === 'pending' || status === 'applying') {
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
