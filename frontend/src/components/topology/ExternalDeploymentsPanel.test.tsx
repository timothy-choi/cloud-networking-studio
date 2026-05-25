import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExternalDeploymentsPanel } from './ExternalDeploymentsPanel';

vi.mock('../../api/deploymentTargets', () => ({
  listDeploymentTargets: vi.fn().mockResolvedValue([
    {
      id: 'target-1',
      project_id: 'project-1',
      name: 'Staging Docker',
      target_type: 'remote_docker',
      config_json: { host: '10.0.0.1', ssh_user: 'ubuntu', remote_workdir: '/opt/cns' },
      credentials_ref: 'dev:default',
      status: 'active',
      created_by_user_id: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
    },
  ]),
  createDeploymentTarget: vi.fn(),
  updateDeploymentTarget: vi.fn(),
  getDeploymentTarget: vi.fn(),
}));

vi.mock('../../api/externalDeploymentJobs', () => ({
  listExternalDeploymentJobs: vi.fn().mockResolvedValue([]),
  listExternalDeployments: vi.fn().mockResolvedValue([]),
  createExternalDeploymentJob: vi.fn(),
}));

describe('ExternalDeploymentsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading shell before targets load', () => {
    const html = renderToStaticMarkup(
      <ExternalDeploymentsPanel topologyId="topo-1" projectId="project-1" />,
    );
    expect(html).toContain('Loading external deployments');
  });
});
