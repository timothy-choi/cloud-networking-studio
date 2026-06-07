import { describe, expect, it } from 'vitest';

import {
  mergeNodeResourceIntoConfig,
  parseNodeResourceFields,
  readNodeResourceFields,
} from './nodeResourceConfig';

describe('nodeResourceConfig', () => {
  it('reads nested resources from node config', () => {
    const fields = readNodeResourceFields({
      id: 'n1',
      topology_id: 't1',
      name: 'api',
      node_type: 'host',
      image: 'nginx',
      ip_address: null,
      config: {
        resources: { cpu: 1.5, memory_mb: 1024, disk_gb: 10, replicas: 2 },
        exposure: 'private',
        stateful: true,
        required_ports: [80],
      },
    });
    expect(fields.cpu).toBe('1.5');
    expect(fields.memoryMb).toBe('1024');
    expect(fields.exposure).toBe('private');
    expect(fields.stateful).toBe(true);
    expect(fields.requiredPorts).toBe('80');
  });

  it('merges resources into existing config without dropping other keys', () => {
    const merged = mergeNodeResourceIntoConfig(
      {
        editor_position: { x: 10, y: 20 },
        health_check: { path: '/' },
        resources: { cpu: 0.5, memory_mb: 512, disk_gb: 5, replicas: 1 },
      },
      {
        cpu: 1.5,
        memory_mb: 1024,
        disk_gb: 10,
        replicas: 1,
        exposure: 'private',
        stateful: false,
        required_ports: [80],
      },
    );
    expect(merged.editor_position).toEqual({ x: 10, y: 20 });
    expect(merged.health_check).toEqual({ path: '/' });
    expect(merged.resources).toEqual({
      cpu: 1.5,
      memory_mb: 1024,
      disk_gb: 10,
      replicas: 1,
    });
    expect(merged.exposure).toBe('private');
    expect(merged.stateful).toBe(false);
    expect(merged.required_ports).toEqual([80]);
  });

  it('parses resource fields for save payload', () => {
    const parsed = parseNodeResourceFields({
      cpu: '1.5',
      memoryMb: '1024',
      diskGb: '10',
      replicas: '1',
      exposure: 'private',
      stateful: false,
      requiredPorts: '80, 443',
    });
    expect(parsed).toEqual({
      cpu: 1.5,
      memory_mb: 1024,
      disk_gb: 10,
      replicas: 1,
      exposure: 'private',
      stateful: false,
      required_ports: [80, 443],
    });
  });
});
