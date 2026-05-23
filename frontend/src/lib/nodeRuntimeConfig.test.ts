import { describe, expect, it } from 'vitest';

import {
  buildNodeCreatePayload,
  mergeNodeRuntimeIntoConfig,
  readNodeRuntimeFields,
  validateNodeRuntimeFields,
} from './nodeRuntimeConfig';

import { metadataDisplay } from './nodeRuntimeConfig';

describe('metadataDisplay', () => {
  it('includes env from runtime metadata', () => {
    const d = metadataDisplay({ env: '{"LAB":"1"}', role_label: 'api' });
    expect(d.roleLabel).toBe('api');
  });
});

describe('nodeRuntimeConfig', () => {
  it('reads and merges freeform fields', () => {
    const node = {
      id: 'n1',
      topology_id: 't1',
      name: 'api',
      node_type: 'generic' as const,
      image: 'busybox:latest',
      ip_address: '10.0.0.5',
      config: {
        role_label: 'api',
        command: 'sleep infinity',
        ports: [{ port: 8080 }],
      },
    };
    const fields = readNodeRuntimeFields(node);
    expect(fields.role_label).toBe('api');
    const merged = mergeNodeRuntimeIntoConfig(node.config, {
      ...fields,
      command: 'nginx -g "daemon off;"',
      portsJson: JSON.stringify([{ port: 443, target_port: 443 }]),
    });
    expect(merged.command).toBe('nginx -g "daemon off;"');
    expect(merged.ports).toEqual([{ port: 443, target_port: 443, protocol: 'TCP' }]);
  });

  it('builds create payload with editor position', () => {
    const body = buildNodeCreatePayload({
      name: 'x',
      node_type: 'host',
      image: 'alpine:latest',
      ip_address: null,
      editorPosition: { x: 10, y: 20 },
      runtime: {
        role_label: '',
        command: '',
        portsJson: '',
        envJson: '',
        terminal_enabled: true,
        bootstrap_command: '',
        description: '',
      },
      healthCheck: { check_type: 'runtime' },
    });
    expect(body.config?.editor_position).toEqual({ x: 10, y: 20 });
  });

  it('validates ports JSON', () => {
    expect(
      validateNodeRuntimeFields({
        role_label: '',
        command: '',
        portsJson: 'not-json',
        envJson: '',
        terminal_enabled: true,
        bootstrap_command: '',
        description: '',
      }),
    ).toMatch(/Ports/);
  });
});
