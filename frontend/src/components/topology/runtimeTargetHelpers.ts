import type { DeploymentTarget } from '../../api/deploymentTargets';

export const MOCK_TARGET_LABEL = 'Mock target — workflow testing only';

export function isMockOrTestTarget(target: DeploymentTarget | null | undefined): boolean {
  if (!target) return false;
  const cfg = target.config_json ?? {};
  return Boolean(
    cfg.is_mock || cfg.target_source === 'local_mock_infra' || cfg.workload_apply_disabled,
  );
}

export function mockTargetLabel(target: DeploymentTarget | null | undefined): string | null {
  if (!target) return null;
  if (!isMockOrTestTarget(target)) return null;
  const cfg = target.config_json ?? {};
  if (typeof cfg.mock_label === 'string' && cfg.mock_label.trim()) {
    return cfg.mock_label;
  }
  return MOCK_TARGET_LABEL;
}

export function workloadApplyDisabledReason(target: DeploymentTarget | null | undefined): string | null {
  if (!target) return null;
  const cfg = target.config_json ?? {};
  if (!cfg.workload_apply_disabled && !isMockOrTestTarget(target)) return null;
  if (typeof cfg.workload_apply_disabled_reason === 'string' && cfg.workload_apply_disabled_reason.trim()) {
    return cfg.workload_apply_disabled_reason;
  }
  if (isMockOrTestTarget(target)) {
    return 'Mock target — real validate/apply uses simulated jobs only (no SSH).';
  }
  return 'Real workload apply is disabled for this target.';
}

export function supportsRealRemoteValidation(target: DeploymentTarget | null | undefined): boolean {
  if (!target || target.target_type !== 'remote_docker') return false;
  return !isMockOrTestTarget(target);
}

export function supportsSimulatedValidation(target: DeploymentTarget | null | undefined): boolean {
  if (!target || target.target_type !== 'remote_docker') return false;
  return isMockOrTestTarget(target);
}

export function enabledWorkloadModes(
  target: DeploymentTarget | null | undefined,
): Array<'validate' | 'plan' | 'apply' | 'destroy'> {
  const base: Array<'validate' | 'plan' | 'apply' | 'destroy'> = ['validate', 'plan'];
  if (!target) return base;
  if (target.target_type === 'remote_docker' && supportsRealRemoteValidation(target)) {
    return ['validate', 'plan', 'apply', 'destroy'];
  }
  if (target.target_type === 'remote_docker' && supportsSimulatedValidation(target)) {
    return ['validate', 'plan'];
  }
  return base;
}
