import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { DeploymentTarget } from '../../api/deploymentTargets';
import { MOCK_TARGET_LABEL, mockTargetLabel, workloadApplyDisabledReason } from './runtimeTargetHelpers';

const mockTarget: DeploymentTarget = {
  id: 'target-mock',
  project_id: 'project-1',
  name: 'lab-infra-lab-infra-vm-1',
  target_type: 'remote_docker',
  config_json: {
    host: '203.0.113.10',
    is_mock: true,
    target_source: 'local_mock_infra',
    mock_label: MOCK_TARGET_LABEL,
    workload_apply_disabled: true,
  },
  credentials_ref: 'env:CNS_REMOTE_DOCKER_SSH_KEY_PATH',
  status: 'active',
  created_by_user_id: 'user-1',
  infrastructure_deployment_id: 'infra-1',
  created_at: '2026-01-01T00:00:00Z',
};

describe('runtime target UX copy', () => {
  it('labels mock targets clearly', () => {
    expect(mockTargetLabel(mockTarget)).toBe(MOCK_TARGET_LABEL);
    expect(workloadApplyDisabledReason(mockTarget)).toContain('simulated');
  });

  it('uses consistent use-created-target button label', () => {
    const html = renderToStaticMarkup(
      <button type="button">Use created target for topology deploy</button>,
    );
    expect(html).toContain('Use created target for topology deploy');
    expect(html).not.toContain('Use created topology');
  });
});
