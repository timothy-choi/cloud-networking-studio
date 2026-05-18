import { describe, expect, it } from 'vitest';
import { pickDefaultHttpTrafficTarget } from './runtimeTrafficDefaults';

describe('pickDefaultHttpTrafficTarget', () => {
  it('prefers server/service named peer internal URL', () => {
    const services = [
      { id: 'res-a', type: 'service', name: 'client', internal_url: 'http://cns-node-aaa-client:80' },
      { id: 'res-b', type: 'service', name: 'server', internal_url: 'http://cns-node-bbb-server:80' },
    ];
    expect(pickDefaultHttpTrafficTarget(services, 'res-a')).toBe('http://cns-node-bbb-server:80');
  });

  it('prefers api-named peer when multiple services', () => {
    const services = [
      { id: 'a', type: 'service', name: 'sidecar', internal_url: 'http://x:80' },
      { id: 'b', type: 'service', name: 'api', internal_url: 'http://y:80' },
    ];
    expect(pickDefaultHttpTrafficTarget(services, 'a')).toBe('http://y:80');
  });

  it('returns empty when no peer URL', () => {
    expect(pickDefaultHttpTrafficTarget([{ id: 'x', type: 'service', name: 'only', internal_url: null }], 'x')).toBe(
      '',
    );
  });
});
