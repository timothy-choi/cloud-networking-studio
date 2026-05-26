import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as infraApi from '../../api/infrastructureDeployments';
import {
  buildInfrastructureCreatePayload,
  canShowApplyAction,
  canShowPlanAction,
  canShowValidateAction,
  applyDisabledReason,
  credentialsRefHelpText,
  destroyDisabledReason,
  deriveConfigurationStatus,
  deriveTerraformStatus,
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
  confirmed_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  destroyed_at: null,
};

describe('infrastructureDeploymentForm', () => {
  it('requires name, template, provider, region, and vm count', () => {
    const errors = validateInfrastructureCreateForm({
      name: '',
      templateId: '',
      provider: '',
      region: '',
      vmCount: 0,
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
        allowedSshCidr: '0.0.0.0/0',
        allowedAppCidr: '0.0.0.0/0',
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
    expect(canShowApplyAction('pending', 'local')).toBe(false);
    expect(canShowApplyAction('awaiting_confirmation', 'local')).toBe(true);
    expect(canShowApplyAction('awaiting_confirmation', 'gcp')).toBe(false);
    expect(canShowValidateAction('pending')).toBe(true);
    expect(canShowPlanAction('validated')).toBe(true);
    expect(canShowPlanAction('awaiting_confirmation')).toBe(false);
  });

  it('shows credentials help for GCP', () => {
    expect(credentialsRefHelpText('gcp')).toContain('GOOGLE_APPLICATION_CREDENTIALS');
    expect(applyDisabledReason('gcp')).toContain('Apply disabled');
    expect(destroyDisabledReason('awaiting_confirmation', 'gcp')).toContain('plan-only');
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
      allowedSshCidr: '0.0.0.0/0',
      allowedAppCidr: '0.0.0.0/0',
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
