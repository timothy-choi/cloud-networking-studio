import { describe, expect, it } from 'vitest';
import { applyPreset, NODE_PRESETS } from './nodePresets';
import { healthCheckToConfig } from './healthCheckConfig';

describe('nodePresets', () => {
  it('ubuntu sandbox defaults to runtime health check, not HTTP', () => {
    const preset = NODE_PRESETS.find((p) => p.id === 'ubuntu-sandbox');
    expect(preset).toBeDefined();
    const applied = applyPreset(preset!);
    expect(applied.healthCheck.check_type).toBe('runtime');
    const probe = healthCheckToConfig(applied.healthCheck);
    expect(probe?.check_type).toBe('runtime');
  });

  it('ubuntu debug preset includes explicit bootstrap command', () => {
    const preset = NODE_PRESETS.find((p) => p.id === 'ubuntu-debug-client');
    expect(preset).toBeDefined();
    const applied = applyPreset(preset!);
    expect(applied.runtime.command).toContain('apt-get install');
    expect(applied.runtime.command).toContain('iproute2');
    expect(applied.runtime.command).toContain('sleep infinity');
  });

  it('python HTTP preset configures HTTP health check metadata', () => {
    const preset = NODE_PRESETS.find((p) => p.id === 'python-http-server');
    expect(preset).toBeDefined();
    const applied = applyPreset(preset!);
    expect(applied.runtime.command).toBe('python -m http.server 80');
    expect(applied.healthCheck.check_type).toBe('http');
    expect(applied.healthCheck.port).toBe('80');
    const probe = healthCheckToConfig(applied.healthCheck);
    expect(probe?.check_type).toBe('http');
    expect(probe?.port).toBe(80);
    expect(probe?.path).toBe('/');
  });
});
