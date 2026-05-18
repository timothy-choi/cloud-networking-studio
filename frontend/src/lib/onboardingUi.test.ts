import { describe, expect, it } from 'vitest';
import { onboardingProgress } from './onboardingUi';

describe('onboardingProgress', () => {
  it('counts completed steps', () => {
    expect(onboardingProgress([{ completed: true }, { completed: false }])).toEqual({ done: 1, total: 2 });
    expect(onboardingProgress([])).toEqual({ done: 0, total: 0 });
  });
});
