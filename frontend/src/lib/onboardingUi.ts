/** Pure helpers for onboarding UI + tests (Step 46). */

import type { OnboardingStepState } from '../api/onboarding';

export function onboardingProgress(steps: Pick<OnboardingStepState, 'completed'>[]): {
  done: number;
  total: number;
} {
  const total = steps.length;
  const done = steps.filter((s) => s.completed).length;
  return { done, total };
}

export function stepHref(
  stepId: string,
  ctx: { firstTopologyId?: string | null; selectedProjectId?: string | null },
): string | null {
  switch (stepId) {
    case 'project':
      return null;
    case 'topology':
      return '/templates';
    case 'deploy':
    case 'runtime_access':
    case 'expose_service':
    case 'health_check':
    case 'safe_exec':
    case 'destroy_deployment':
      return ctx.firstTopologyId ? `/topologies/${ctx.firstTopologyId}` : null;
    default:
      return null;
  }
}
