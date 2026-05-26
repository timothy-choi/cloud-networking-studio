export type ExternalDeploymentsTab = 'targets' | 'jobs' | 'deployments';

export function infraTargetNavigationIntent(targetId: string): {
  preferredTab: ExternalDeploymentsTab;
  preselectedTargetId: string;
  highlightTargetId: string;
} {
  return {
    preferredTab: 'targets',
    preselectedTargetId: targetId,
    highlightTargetId: targetId,
  };
}

/** Apply one-shot navigation from infra without forcing the jobs tab. */
export function shouldApplyInfraNavigation(
  navigationKey: string,
  lastAppliedKey: string | null,
): boolean {
  return Boolean(navigationKey) && navigationKey !== lastAppliedKey;
}

export function buildInfraNavigationKey(
  preferredTab: ExternalDeploymentsTab | null | undefined,
  preselectedTargetId: string | null | undefined,
  highlightTargetId: string | null | undefined,
): string {
  return `${preferredTab ?? ''}:${preselectedTargetId ?? ''}:${highlightTargetId ?? ''}`;
}
