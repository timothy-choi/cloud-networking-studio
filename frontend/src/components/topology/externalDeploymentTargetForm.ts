import type { DeploymentTarget, RuntimeDeploymentTargetType } from '../../api/deploymentTargets';

export type TargetFormMode = 'closed' | 'create' | 'edit';

export type TargetFormState = {
  name: string;
  targetType: RuntimeDeploymentTargetType;
  credentialsRef: string;
  status: string;
  configJson: string;
};

export const REMOTE_DOCKER_CONFIG_TEMPLATE = JSON.stringify(
  {
    host: '',
    ssh_user: 'ubuntu',
    ssh_port: 22,
    remote_workdir: '/opt/cns-external-deployments',
    supports_compose: true,
  },
  null,
  2,
);

export function createBlankTargetFormState(): TargetFormState {
  return {
    name: '',
    targetType: 'remote_docker',
    credentialsRef: '',
    status: 'active',
    configJson: '{}',
  };
}

export function targetToFormState(target: DeploymentTarget): TargetFormState {
  const targetType: RuntimeDeploymentTargetType =
    target.target_type === 'kubernetes' ? 'kubernetes' : 'remote_docker';
  return {
    name: target.name,
    targetType,
    credentialsRef: target.credentials_ref ?? '',
    status: target.status,
    configJson: JSON.stringify(target.config_json ?? {}, null, 2),
  };
}

export function applyRemoteDockerTemplate(form: TargetFormState): TargetFormState {
  return {
    ...form,
    configJson: REMOTE_DOCKER_CONFIG_TEMPLATE,
  };
}

export function parseTargetConfigJson(configJson: string): Record<string, unknown> {
  return JSON.parse(configJson || '{}') as Record<string, unknown>;
}
