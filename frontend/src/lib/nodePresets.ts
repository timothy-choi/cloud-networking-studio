import type { NodeType } from '../types/topology';
import type { NodeRuntimeFields } from './nodeRuntimeConfig';
import { emptyNodeRuntimeFields } from './nodeRuntimeConfig';

export interface NodePreset {
  id: string;
  label: string;
  description: string;
  node_type: NodeType;
  image: string | null;
  runtime: Partial<NodeRuntimeFields>;
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
      health_check: '/',
      terminal_enabled: true,
    },
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
      health_check: '/',
    },
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
  },
  {
    id: 'custom-blank',
    label: 'Custom (blank)',
    description: 'Empty form — set image, command, ports, and env yourself.',
    node_type: 'host',
    image: null,
    runtime: {},
  },
];

export function applyPreset(preset: NodePreset): {
  node_type: NodeType;
  image: string | null;
  runtime: NodeRuntimeFields;
} {
  const base = emptyNodeRuntimeFields();
  return {
    node_type: preset.node_type,
    image: preset.image,
    runtime: { ...base, ...preset.runtime },
  };
}

export function defaultImageForNodeType(nodeType: NodeType): string | null {
  if (nodeType === 'generic') return 'nginx:alpine';
  return 'alpine:latest';
}

export function defaultNamePrefix(nodeType: NodeType): string {
  return nodeType === 'generic' ? 'service' : nodeType;
}
