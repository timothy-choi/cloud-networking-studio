import { describe, expect, it } from 'vitest';

import {
  buildInfraNavigationKey,
  infraTargetNavigationIntent,
  shouldApplyInfraNavigation,
} from './externalDeploymentNavigation';

describe('externalDeploymentNavigation', () => {
  it('opens Targets tab for infra-created target navigation', () => {
    const intent = infraTargetNavigationIntent('target-abc');
    expect(intent.preferredTab).toBe('targets');
    expect(intent.preselectedTargetId).toBe('target-abc');
    expect(intent.highlightTargetId).toBe('target-abc');
    expect(intent.preferredTab).not.toBe('jobs');
  });

  it('applies navigation once per unique key', () => {
    const key = buildInfraNavigationKey('targets', 'target-1', 'target-1');
    expect(shouldApplyInfraNavigation(key, null)).toBe(true);
    expect(shouldApplyInfraNavigation(key, key)).toBe(false);
  });

  it('does not force workflow jobs tab in navigation key', () => {
    const key = buildInfraNavigationKey('targets', 'target-1', 'target-1');
    expect(key.startsWith('targets:')).toBe(true);
    expect(key).not.toContain('jobs');
  });
});
