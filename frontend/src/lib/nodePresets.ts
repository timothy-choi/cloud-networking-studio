import type { NodeType } from '../types/topology';
import type { NodeRuntimeFields } from './nodeRuntimeConfig';
import { emptyNodeRuntimeFields } from './nodeRuntimeConfig';
import type { HealthCheckFields } from './healthCheckConfig';
import { emptyHealthCheckFields } from './healthCheckConfig';

export interface NodePreset {
  id: string;
  label: string;
  description: string;
  node_type: NodeType;
  image: string | null;
  runtime: Partial<NodeRuntimeFields>;
  healthCheck?: Partial<HealthCheckFields>;
}

/** Presets prefill the node form — every field remains editable before save. */
export const NODE_PRESETS: NodePreset[] = [
  {
    id: 'alpine-host',
    label: 'Alpine host',
    description: 'General-purpose shell host with NET_ADMIN-friendly image.',
    node_type: 'host',
    image: 'alpine:latest',
    runtime: {
      role_label: 'host',
      command: 'sleep infinity',
      portsJson: '',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'ubuntu-sandbox',
    label: 'Ubuntu developer sandbox',
    description: 'Long-running Ubuntu host for manual setup (no auto-installed tools).',
    node_type: 'host',
    image: 'ubuntu:22.04',
    runtime: {
      role_label: 'dev_sandbox',
      command: 'sleep infinity',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'python-sandbox',
    label: 'Python sandbox',
    description: 'Python runtime image kept alive with sleep infinity.',
    node_type: 'host',
    image: 'python:3.12',
    runtime: {
      role_label: 'python',
      command: 'sleep infinity',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'node-sandbox',
    label: 'Node.js sandbox',
    description: 'Node runtime image kept alive with sleep infinity.',
    node_type: 'host',
    image: 'node:22',
    runtime: {
      role_label: 'node',
      command: 'sleep infinity',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'nginx-service',
    label: 'Nginx service',
    description: 'HTTP service on port 80 using the stock nginx entrypoint.',
    node_type: 'generic',
    image: 'nginx:alpine',
    runtime: {
      role_label: 'web',
      portsJson: JSON.stringify([{ port: 80, target_port: 80, protocol: 'TCP' }], null, 2),
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'http', port: '80', path: '/' },
  },
  {
    id: 'busybox-http',
    label: 'Busybox HTTP',
    description: 'Tiny static HTTP responder on port 80.',
    node_type: 'generic',
    image: 'busybox:latest',
    runtime: {
      role_label: 'microservice',
      command:
        'sh -c "mkdir -p /www && printf ok\\n >/www/index.html && exec httpd -f -p 80 -h /www"',
      portsJson: JSON.stringify([{ port: 80, target_port: 80 }], null, 2),
    },
    healthCheck: { check_type: 'http', port: '80', path: '/' },
  },
  {
    id: 'redis-service',
    label: 'Redis',
    description: 'Redis with TCP health check on port 6379.',
    node_type: 'generic',
    image: 'redis:7',
    runtime: {
      role_label: 'cache',
      portsJson: JSON.stringify([{ port: 6379, target_port: 6379 }], null, 2),
    },
    healthCheck: { check_type: 'tcp', port: '6379' },
  },
  {
    id: 'postgres-service',
    label: 'PostgreSQL',
    description: 'PostgreSQL with TCP health check on port 5432.',
    node_type: 'generic',
    image: 'postgres:16',
    runtime: {
      role_label: 'database',
      portsJson: JSON.stringify([{ port: 5432, target_port: 5432 }], null, 2),
      envJson: JSON.stringify({ POSTGRES_PASSWORD: 'lab' }, null, 2),
    },
    healthCheck: { check_type: 'tcp', port: '5432' },
  },
  {
    id: 'debug-toolbox',
    label: 'Debug Toolbox',
    description: 'Network diagnostics (curl, dig, ping, tcpdump) via netshoot.',
    node_type: 'host',
    image: 'nicolaka/netshoot:latest',
    runtime: {
      role_label: 'debug_toolbox',
      command: 'sleep infinity',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'segment-router',
    label: 'Segment router',
    description: 'Router role with long-running shell for multinet labs.',
    node_type: 'router',
    image: 'alpine:latest',
    runtime: {
      role_label: 'segment_router',
      command: 'sleep infinity',
      terminal_enabled: true,
    },
    healthCheck: { check_type: 'runtime' },
  },
  {
    id: 'custom-blank',
    label: 'Custom (blank)',
    description: 'Empty form — set image, command, ports, and env yourself.',
    node_type: 'host',
    image: null,
    runtime: {},
    healthCheck: { check_type: 'runtime' },
  },
];

export function applyPreset(preset: NodePreset): {
  node_type: NodeType;
  image: string | null;
  runtime: NodeRuntimeFields;
  healthCheck: HealthCheckFields;
} {
  const base = emptyNodeRuntimeFields();
  const hcBase = emptyHealthCheckFields();
  return {
    node_type: preset.node_type,
    image: preset.image,
    runtime: { ...base, ...preset.runtime },
    healthCheck: { ...hcBase, ...(preset.healthCheck ?? { check_type: 'runtime' }) },
  };
}

export function defaultImageForNodeType(nodeType: NodeType): string | null {
  if (nodeType === 'generic') return 'nginx:alpine';
  return 'alpine:latest';
}

export function defaultNamePrefix(nodeType: NodeType): string {
  return nodeType === 'generic' ? 'service' : nodeType;
}
