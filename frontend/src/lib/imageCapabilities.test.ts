import { describe, expect, it } from 'vitest';
import {
  BASE_OS_IMAGE_WARNING,
  detectImageProfile,
  getImageCapabilities,
  inferHealthWarningsFromCapabilities,
} from './imageCapabilities';

describe('imageCapabilities', () => {
  it('detects ubuntu as ubuntu-debian profile', () => {
    expect(detectImageProfile('ubuntu:22.04')).toBe('ubuntu-debian');
  });

  it('shows base OS warning for ubuntu images', () => {
    const caps = getImageCapabilities('ubuntu:22.04', 'sleep infinity');
    expect(caps.profile).toBe('ubuntu-debian');
    expect(caps.suggestsRuntimeCheck).toBe(true);
    expect(caps.hints).toContain(BASE_OS_IMAGE_WARNING);
    expect(caps.missingByDefault).toContain('ping');
    expect(caps.missingByDefault).toContain('ip');
  });

  it('warns when HTTP check is set without a server command on base images', () => {
    const warnings = inferHealthWarningsFromCapabilities('ubuntu:22.04', 'sleep infinity', 'http');
    expect(warnings.some((w) => w.includes('No HTTP service appears to be running'))).toBe(true);
  });

  it('identifies netshoot as network toolbox', () => {
    const caps = getImageCapabilities('nicolaka/netshoot:latest', 'sleep infinity');
    expect(caps.profile).toBe('netshoot');
    expect(caps.networkToolsAvailable).toBe(true);
    expect(caps.missingByDefault).toHaveLength(0);
  });

  it('identifies nginx as HTTP-by-default service image', () => {
    const caps = getImageCapabilities('nginx:alpine', '');
    expect(caps.profile).toBe('nginx');
    expect(caps.httpByDefault).toBe(true);
  });
});
