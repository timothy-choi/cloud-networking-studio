import type { DeploymentTarget } from '../../api/deploymentTargets';

export function isMockOrTestTarget(target: DeploymentTarget | null | undefined): boolean {
  if (!target) return false;
  const cfg = target.config_json ?? {};
  return Boolean(cfg.is_mock || cfg.workload_apply_disabled);
}

export function mockTargetLabel(target: DeploymentTarget | null | undefined): string | null {
  if (!target) return null;
  const cfg = target.config_json ?? {};
  if (typeof cfg.mock_label === 'string' && cfg.mock_label.trim()) {
    return cfg.mock_label;
  }
  if (cfg.is_mock) {
    return 'Mock target — for workflow testing only';
  }
  return null;
}

export function workloadApplyDisabledReason(target: DeploymentTarget | null | undefined): string | null {
  if (!target) return null;
  const cfg = target.config_json ?? {};
  if (!cfg.workload_apply_disabled) return null;
  if (typeof cfg.workload_apply_disabled_reason === 'string' && cfg.workload_apply_disabled_reason.trim()) {
    return cfg.workload_apply_disabled_reason;
  }
  return 'Real workload apply is disabled for this target.';
}

export function enabledWorkloadModes(target: DeploymentTarget | null | undefined): Array<'validate' | 'plan' | 'apply' | 'destroy'> {
  const base: Array<'validate' | 'plan' | 'apply' | 'destroy'> = ['validate', 'plan'];
  if (!target) return base;
  if (target.target_type === 'remote_docker' && !isMockOrTestTarget(target)) {
    return ['validate', 'plan', 'apply', 'destroy'];
  }
  if (target.target_type === 'remote_docker') {
    return ['validate', 'plan'];
  }
  return base;
}
