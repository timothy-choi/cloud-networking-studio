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
