import { describe, expect, it } from 'vitest';

import type { DeploymentTarget } from '../../api/deploymentTargets';
import {
  enabledWorkloadModes,
  isMockOrTestTarget,
  MOCK_TARGET_LABEL,
  mockTargetLabel,
  supportsRealRemoteValidation,
  supportsSimulatedValidation,
  workloadApplyDisabledReason,
} from './runtimeTargetHelpers';

const mockTarget: DeploymentTarget = {
  id: 't1',
  project_id: 'p1',
  name: 'mock-host',
  target_type: 'remote_docker',
  config_json: {
    host: '203.0.113.10',
    is_mock: true,
    target_source: 'local_mock_infra',
    mock_label: MOCK_TARGET_LABEL,
    workload_apply_disabled: true,
    workload_apply_disabled_reason:
      'Mock/simulated target — real workload validate/apply is disabled for workflow testing only.',
  },
  credentials_ref: null,
  status: 'active',
  created_by_user_id: null,
  infrastructure_deployment_id: 'infra-1',
  created_at: '2026-01-01T00:00:00Z',
};

describe('runtimeTargetHelpers', () => {
  it('detects mock targets and disables real apply/destroy', () => {
    expect(isMockOrTestTarget(mockTarget)).toBe(true);
    expect(mockTargetLabel(mockTarget)).toBe(MOCK_TARGET_LABEL);
    expect(workloadApplyDisabledReason(mockTarget)).toContain('simulated');
    expect(supportsSimulatedValidation(mockTarget)).toBe(true);
    expect(supportsRealRemoteValidation(mockTarget)).toBe(false);
    expect(enabledWorkloadModes(mockTarget)).toEqual(['validate', 'plan']);
  });

  it('allows real validate/apply/destroy for real remote_docker targets', () => {
    const realTarget: DeploymentTarget = {
      ...mockTarget,
      config_json: { host: '10.0.0.5' },
    };
    expect(isMockOrTestTarget(realTarget)).toBe(false);
    expect(supportsRealRemoteValidation(realTarget)).toBe(true);
    expect(supportsSimulatedValidation(realTarget)).toBe(false);
    expect(enabledWorkloadModes(realTarget)).toEqual(['validate', 'plan', 'apply', 'destroy']);
  });
});
