import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as infraApi from '../../api/infrastructureDeployments';
import {
  applyDisabledReason,
  buildInfrastructureCreatePayload,
  canShowApplyAction,
  canShowDestroyAction,
  canShowPlanAction,
  canShowRetryConfigurationAction,
  canShowValidateAction,
  credentialsRefHelpText,
  destroyDisabledReason,
  deriveConfigurationStatus,
  deriveTerraformStatus,
  extractApplySafetyChecklist,
  hasOpenInternetCidr,
  hasTerraformApplyCompleted,
  validateInfrastructureCreateForm,
} from './infrastructureDeploymentForm';
import { InfrastructureDeploymentsPanel, submitInfrastructureCreate } from './InfrastructureDeploymentsPanel';

vi.mock('../../api/infrastructureDeployments', () => ({
  listInfrastructureTemplates: vi.fn().mockResolvedValue([
    {
      template_id: 'local-mock',
      provider: 'local-mock',
      description: 'Mock template',
      supported_providers: ['local', 'mock'],
    },
  ]),
  listInfrastructureDeployments: vi.fn(),
  listInfrastructureExecutions: vi.fn().mockResolvedValue([]),
  createInfrastructureDeployment: vi.fn(),
  validateInfrastructureDeployment: vi.fn(),
  planInfrastructureDeployment: vi.fn(),
  confirmInfrastructureDeployment: vi.fn(),
  destroyInfrastructureDeployment: vi.fn(),
}));

const sampleDeployment: infraApi.InfrastructureDeployment = {
  id: 'dep-new',
  project_id: 'p1',
  topology_id: 'topo-1',
  name: 'lab-infra',
  stack_type: 'terraform_ansible',
  template_id: 'local-mock',
  provider: 'local',
  status: 'pending',
  variables_json: {},
  plan_summary_json: null,
  outputs_json: {},
  inventory_json: {},
  state_metadata_json: {},
  events_json: [],
  metrics_json: {},
  runtime_targets_json: [],
  error_message: null,
  credentials_ref: null,
  confirmed_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  destroyed_at: null,
};

const gcpPlanSummary = {
  provider: 'gcp',
  template_id: 'docker-vm',
  apply_eligible: true,
  cost_warning: 'This may create billable cloud resources.',
  safety_checklist: {
    passed: true,
    items: [
      { name: 'provider_template', ok: true, message: 'Provider/template must be gcp + docker-vm' },
      { name: 'cost_warning', ok: true, warning: true, message: 'This may create billable cloud resources.' },
    ],
  },
};

describe('infrastructureDeploymentForm', () => {
  it('requires name, template, provider, region, and vm count', () => {
    const errors = validateInfrastructureCreateForm({
      name: '',
      templateId: '',
      provider: '',
      region: '',
      vmCount: 0,
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
    });
    expect(errors.name).toBeTruthy();
    expect(errors.templateId).toBeTruthy();
    expect(errors.provider).toBeTruthy();
    expect(errors.region).toBeTruthy();
    expect(errors.vmCount).toBeTruthy();
  });

  it('builds create payload from form values', () => {
    expect(
      buildInfrastructureCreatePayload({
        name: ' lab ',
        templateId: 'local-mock',
        provider: 'local',
        region: 'us-east-1',
        vmCount: 2,
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
      }),
    ).toEqual({
      name: 'lab',
      template_id: 'local-mock',
      provider: 'local',
      variables: { region: 'us-east-1', vm_count: 2 },
    });
  });

  it('shows apply only after plan reaches awaiting_confirmation for mock providers', () => {
    expect(canShowApplyAction('pending', 'local-mock', 'local', null)).toBe(false);
    expect(canShowApplyAction('awaiting_confirmation', 'local-mock', 'local', null)).toBe(true);
    expect(canShowApplyAction('awaiting_confirmation', 'docker-vm', 'gcp', gcpPlanSummary)).toBe(true);
    expect(canShowApplyAction('awaiting_confirmation', 'docker-vm', 'gcp', { safety_checklist: { passed: false } })).toBe(
      false,
    );
    const appliedMeta = { terraform_apply_completed: true, applied_at: '2026-01-01T00:00:00Z' };
    expect(canShowApplyAction('awaiting_confirmation', 'docker-vm', 'gcp', gcpPlanSummary, appliedMeta)).toBe(false);
    expect(hasTerraformApplyCompleted(appliedMeta)).toBe(true);
    expect(canShowValidateAction('pending')).toBe(true);
    expect(canShowPlanAction('validated')).toBe(true);
    expect(canShowPlanAction('awaiting_confirmation')).toBe(false);
  });

  it('shows credentials help for GCP', () => {
    expect(credentialsRefHelpText('gcp')).toContain('GOOGLE_APPLICATION_CREDENTIALS');
    expect(
      applyDisabledReason('awaiting_confirmation', 'docker-vm', 'gcp', { safety_checklist: { passed: false, items: [] } }),
    ).toContain('Safety checks failed');
    expect(destroyDisabledReason('awaiting_confirmation', 'docker-vm', 'gcp', {})).toContain('not been applied');
  });

  it('shows destroy from partial failure states when apply metadata exists', () => {
    const appliedMeta = { applied_at: '2026-01-01T00:00:00Z', apply_execution_id: 'x', terraform_apply_completed: true };
    expect(canShowDestroyAction('configuration_failed', 'docker-vm', 'gcp', appliedMeta)).toBe(true);
    expect(canShowDestroyAction('registration_failed', 'docker-vm', 'gcp', appliedMeta)).toBe(true);
    expect(canShowRetryConfigurationAction('configuration_failed', appliedMeta)).toBe(true);
    expect(canShowRetryConfigurationAction('registration_failed', appliedMeta)).toBe(true);
    expect(canShowRetryConfigurationAction('applying', appliedMeta)).toBe(true);
    expect(canShowRetryConfigurationAction('configuring', appliedMeta)).toBe(true);
    expect(canShowRetryConfigurationAction('succeeded', appliedMeta)).toBe(false);
    expect(canShowRetryConfigurationAction('awaiting_confirmation', appliedMeta)).toBe(false);
    expect(destroyDisabledReason('configuration_failed', 'docker-vm', 'gcp', appliedMeta)).toBeNull();
  });

  it('allows idempotent destroy from destroyed without disabled reason', () => {
    expect(canShowDestroyAction('destroyed', 'docker-vm', 'gcp', {})).toBe(true);
    expect(destroyDisabledReason('destroyed', 'docker-vm', 'gcp', {})).toBeNull();
  });

  it('derives configuration_failed and registration_failed display status', () => {
    expect(deriveConfigurationStatus('configuration_failed', ['configure_failed'])).toBe('failed');
    expect(deriveConfigurationStatus('registration_failed', ['registration_failed'])).toBe('registration_failed');
    expect(
      deriveTerraformStatus('configuration_failed', ['apply_completed', 'configure_failed']),
    ).toBe('applied');
  });

  it('extracts safety checklist and open CIDR warning', () => {
    const checklist = extractApplySafetyChecklist(gcpPlanSummary);
    expect(checklist?.passed).toBe(true);
    expect(hasOpenInternetCidr({ allowed_ssh_cidr: '0.0.0.0/0' })).toBe(true);
    expect(hasOpenInternetCidr({ allowed_ssh_cidr: '203.0.113.0/24' })).toBe(false);
  });

  it('shows destroy only after apply for GCP', () => {
    const appliedMeta = { applied_at: '2026-01-01T00:00:00Z' };
    expect(canShowDestroyAction('awaiting_confirmation', 'docker-vm', 'gcp', {})).toBe(false);
    expect(canShowDestroyAction('succeeded', 'docker-vm', 'gcp', appliedMeta)).toBe(true);
  });

  it('builds GCP docker-vm create payload', () => {
    expect(
      buildInfrastructureCreatePayload({
        name: 'gcp-lab',
        templateId: 'docker-vm',
        provider: 'gcp',
        region: 'us-central1',
        vmCount: 1,
        credentialsRef: 'env:GOOGLE_APPLICATION_CREDENTIALS',
        projectId: 'my-gcp-project',
        zone: 'us-central1-a',
        machineType: 'e2-medium',
        networkName: 'default',
        instanceName: 'cns-docker-vm',
        sshUser: 'ubuntu',
        allowedSshCidr: '203.0.113.0/24',
        allowedAppCidr: '203.0.113.0/24',
        tags: 'cns-docker-vm',
      }),
    ).toMatchObject({
      template_id: 'docker-vm',
      provider: 'gcp',
      credentials_ref: 'env:GOOGLE_APPLICATION_CREDENTIALS',
      variables: { project_id: 'my-gcp-project', zone: 'us-central1-a' },
    });
  });

  it('derives terraform and ansible status from events', () => {
    expect(deriveTerraformStatus('awaiting_confirmation', ['validate_completed', 'plan_completed'])).toBe(
      'planned (awaiting confirmation)',
    );
    expect(deriveTerraformStatus('succeeded', ['apply_started', 'apply_completed'])).toBe('applied');
    expect(deriveConfigurationStatus('succeeded', ['configure_started', 'configure_completed', 'runtime_ready'])).toBe(
      'completed',
    );
    expect(deriveConfigurationStatus('awaiting_confirmation', [])).toBe('not started');
  });
});

describe('InfrastructureDeploymentsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(infraApi.listInfrastructureDeployments).mockResolvedValue([]);
  });

  it('renders create button and GCP credentials help when template supports gcp', () => {
    vi.mocked(infraApi.listInfrastructureTemplates).mockResolvedValue([
      {
        template_id: 'docker-vm',
        provider: 'docker-vm',
        description: 'Docker VM',
        supported_providers: ['local', 'mock', 'gcp', 'aws'],
      },
    ]);
    const html = renderToStaticMarkup(<InfrastructureDeploymentsPanel topologyId="topo-1" />);
    expect(html).toContain('Create Infrastructure Deployment');
    expect(html).toContain('Deployment name');
    expect(html).toContain('New infrastructure deployment');
    expect(html).toContain('Terraform to provision');
  });

  it('provides data needed to render GCP safety checklist in detail view', () => {
    const checklist = extractApplySafetyChecklist(gcpPlanSummary);
    expect(checklist?.items?.some((item) => item.name === 'cost_warning')).toBe(true);
    expect(gcpPlanSummary.cost_warning).toContain('billable');
    expect(
      canShowApplyAction('awaiting_confirmation', 'docker-vm', 'gcp', gcpPlanSummary),
    ).toBe(true);
    expect(
      canShowApplyAction('awaiting_confirmation', 'docker-vm', 'gcp', gcpPlanSummary, {
        terraform_apply_completed: true,
      }),
    ).toBe(false);
    expect(
      hasOpenInternetCidr({ allowed_ssh_cidr: '0.0.0.0/0', allowed_app_cidr: '203.0.113.0/24' }),
    ).toBe(true);
  });
});

describe('submitInfrastructureCreate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(infraApi.createInfrastructureDeployment).mockResolvedValue(sampleDeployment);
    vi.mocked(infraApi.listInfrastructureDeployments).mockResolvedValue([sampleDeployment]);
  });

  it('creates deployment and returns refreshed list with created deployment', async () => {
    const result = await submitInfrastructureCreate('topo-1', {
      name: 'lab-infra',
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
    });

    expect(infraApi.createInfrastructureDeployment).toHaveBeenCalledWith('topo-1', {
      name: 'lab-infra',
      template_id: 'local-mock',
      provider: 'local',
      variables: { region: 'local', vm_count: 1 },
    });
    expect(result.created.id).toBe('dep-new');
    expect(result.deployments.some((d) => d.id === 'dep-new')).toBe(true);
    expect(infraApi.listInfrastructureDeployments).toHaveBeenCalledWith('topo-1');
  });
});
