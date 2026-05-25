import { describe, expect, it } from 'vitest';

import type { DeploymentTarget } from '../../api/deploymentTargets';
import {
  applyRemoteDockerTemplate,
  createBlankTargetFormState,
  targetToFormState,
} from './externalDeploymentTargetForm';

describe('externalDeploymentTargetForm', () => {
  it('createBlankTargetFormState starts with empty fields', () => {
    const form = createBlankTargetFormState();
    expect(form.name).toBe('');
    expect(form.targetType).toBe('remote_docker');
    expect(form.credentialsRef).toBe('');
    expect(form.status).toBe('active');
    expect(form.configJson).toBe('{}');
  });

  it('targetToFormState loads selected target values', () => {
    const target: DeploymentTarget = {
      id: 't1',
      project_id: 'p1',
      name: 'Prod Docker',
      target_type: 'remote_docker',
      config_json: { host: '10.0.0.5', ssh_user: 'ubuntu', remote_workdir: '/opt/cns' },
      credentials_ref: 'env:CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH',
      status: 'disabled',
      created_by_user_id: 'u1',
      created_at: '2026-01-01T00:00:00Z',
    };
    const form = targetToFormState(target);
    expect(form.name).toBe('Prod Docker');
    expect(form.credentialsRef).toBe('env:CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH');
    expect(form.status).toBe('disabled');
    expect(JSON.parse(form.configJson)).toEqual(target.config_json);
  });

  it('applyRemoteDockerTemplate only changes config JSON', () => {
    const blank = createBlankTargetFormState();
    const templated = applyRemoteDockerTemplate(blank);
    expect(templated.name).toBe('');
    expect(templated.credentialsRef).toBe('');
    expect(templated.configJson).toContain('remote_workdir');
    expect(templated.configJson).not.toBe('{}');
  });

  it('cancel flow can restore blank form without mutating prior edit state', () => {
    const target: DeploymentTarget = {
      id: 't1',
      project_id: 'p1',
      name: 'Prod Docker',
      target_type: 'remote_docker',
      config_json: { host: '10.0.0.5' },
      credentials_ref: 'dev:default',
      status: 'active',
      created_by_user_id: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    const editForm = targetToFormState(target);
    const fresh = createBlankTargetFormState();
    expect(fresh.name).not.toBe(editForm.name);
    expect(fresh.configJson).not.toBe(editForm.configJson);
  });
});
