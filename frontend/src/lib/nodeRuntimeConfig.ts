/** Well-known keys in `TopologyNode.config` for freeform runtime intent. */

import type { NodeType, TopologyNodeCreate, TopologyNodeResponse } from '../types/topology';
import { EDITOR_POSITION_KEY } from '../types/topology';

export const NODE_CONFIG_KEYS = {
  roleLabel: 'role_label',
  command: 'command',
  ports: 'ports',
  env: 'env',
  terminalEnabled: 'terminal_enabled',
  healthCheck: 'health_check',
  description: 'description',
} as const;

export interface NodePortSpec {
  port: number;
  target_port?: number;
  protocol?: string;
}

export interface NodeRuntimeFields {
  role_label: string;
  command: string;
  portsJson: string;
  envJson: string;
  terminal_enabled: boolean;
  health_check: string;
  description: string;
}

export function emptyNodeRuntimeFields(): NodeRuntimeFields {
  return {
    role_label: '',
    command: '',
    portsJson: '',
    envJson: '',
    terminal_enabled: true,
    health_check: '',
    description: '',
  };
}

function parsePortsJson(raw: string): NodePortSpec[] | null {
  const s = raw.trim();
  if (!s) return null;
  const parsed: unknown = JSON.parse(s);
  if (!Array.isArray(parsed)) return null;
  const out: NodePortSpec[] = [];
  for (const item of parsed) {
    if (typeof item === 'number' && item > 0) {
      out.push({ port: item, target_port: item });
      continue;
    }
    if (item && typeof item === 'object' && 'port' in item) {
      const p = item as Record<string, unknown>;
      const port = Number(p.port);
      if (!Number.isFinite(port) || port <= 0) continue;
      const tp = p.target_port != null ? Number(p.target_port) : port;
      out.push({
        port,
        target_port: Number.isFinite(tp) ? tp : port,
        protocol: typeof p.protocol === 'string' ? p.protocol : 'TCP',
      });
    }
  }
  return out.length ? out : null;
}

function parseEnvJson(raw: string): Record<string, string> | string[] | null {
  const s = raw.trim();
  if (!s) return null;
  const parsed: unknown = JSON.parse(s);
  if (Array.isArray(parsed)) {
    const out = parsed.filter((x) => typeof x === 'string' && x.includes('='));
    return out.length ? out : null;
  }
  if (parsed && typeof parsed === 'object') {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (k.trim()) out[k] = String(v);
    }
    return Object.keys(out).length ? out : null;
  }
  return null;
}

function parseHealthCheck(raw: string): Record<string, unknown> | string | null {
  const s = raw.trim();
  if (!s) return null;
  if (s.startsWith('{')) {
    const parsed: unknown = JSON.parse(s);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  }
  return s;
}

export function readNodeRuntimeFields(node: TopologyNodeResponse): NodeRuntimeFields {
  const cfg = node.config ?? {};
  const ports = cfg[NODE_CONFIG_KEYS.ports];
  const env = cfg[NODE_CONFIG_KEYS.env];
  const hc = cfg[NODE_CONFIG_KEYS.healthCheck];
  const te = cfg[NODE_CONFIG_KEYS.terminalEnabled];
  const roleRaw = cfg[NODE_CONFIG_KEYS.roleLabel];
  const cmdRaw = cfg[NODE_CONFIG_KEYS.command];
  const descRaw = cfg[NODE_CONFIG_KEYS.description];
  return {
    role_label: typeof roleRaw === 'string' ? roleRaw : '',
    command: Array.isArray(cmdRaw)
      ? cmdRaw.map(String).join(' ')
      : typeof cmdRaw === 'string'
        ? cmdRaw
        : '',
    portsJson: ports != null ? JSON.stringify(ports, null, 2) : '',
    envJson: env != null ? JSON.stringify(env, null, 2) : '',
    terminal_enabled: te === false || te === 'false' ? false : true,
    health_check:
      hc != null
        ? typeof hc === 'string'
          ? hc
          : JSON.stringify(hc, null, 2)
        : '',
    description: typeof descRaw === 'string' ? descRaw : '',
  };
}

export function mergeNodeRuntimeIntoConfig(
  base: Record<string, unknown> | null | undefined,
  fields: NodeRuntimeFields,
): Record<string, unknown> {
  const cfg: Record<string, unknown> = { ...(base ?? {}) };
  const setOrDelete = (key: string, value: unknown) => {
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
      delete cfg[key];
    } else {
      cfg[key] = value;
    }
  };

  setOrDelete(NODE_CONFIG_KEYS.roleLabel, fields.role_label.trim() || null);
  const cmd = fields.command.trim();
  setOrDelete(NODE_CONFIG_KEYS.command, cmd || null);
  try {
    const ports = parsePortsJson(fields.portsJson);
    setOrDelete(NODE_CONFIG_KEYS.ports, ports);
  } catch {
    /* keep prior ports if JSON invalid — caller should validate */
  }
  try {
    const env = parseEnvJson(fields.envJson);
    setOrDelete(NODE_CONFIG_KEYS.env, env);
  } catch {
    /* caller validates */
  }
  setOrDelete(NODE_CONFIG_KEYS.terminalEnabled, fields.terminal_enabled ? null : false);
  try {
    const hc = parseHealthCheck(fields.health_check);
    setOrDelete(NODE_CONFIG_KEYS.healthCheck, hc);
  } catch {
    /* caller validates */
  }
  setOrDelete(NODE_CONFIG_KEYS.description, fields.description.trim() || null);
  return cfg;
}

export function validateNodeRuntimeFields(fields: NodeRuntimeFields): string | null {
  if (fields.portsJson.trim()) {
    try {
      parsePortsJson(fields.portsJson);
    } catch {
      return 'Ports must be valid JSON (array of port objects or numbers).';
    }
  }
  if (fields.envJson.trim()) {
    try {
      parseEnvJson(fields.envJson);
    } catch {
      return 'Env must be valid JSON (object or array of KEY=value strings).';
    }
  }
  if (fields.health_check.trim() && fields.health_check.trim().startsWith('{')) {
    try {
      parseHealthCheck(fields.health_check);
    } catch {
      return 'Health check JSON must be valid.';
    }
  }
  return null;
}

export function buildNodeCreatePayload(input: {
  name: string;
  node_type: NodeType;
  image: string | null;
  ip_address: string | null;
  editorPosition?: { x: number; y: number };
  runtime: NodeRuntimeFields;
  extraConfig?: Record<string, unknown> | null;
}): TopologyNodeCreate {
  const cfg = mergeNodeRuntimeIntoConfig(input.extraConfig, input.runtime);
  if (input.editorPosition) {
    cfg[EDITOR_POSITION_KEY] = input.editorPosition;
  }
  return {
    name: input.name,
    node_type: input.node_type,
    image: input.image,
    ip_address: input.ip_address,
    config: Object.keys(cfg).length ? cfg : null,
  };
}

export function metadataDisplay(meta: Record<string, string> | undefined | null): {
  roleLabel?: string;
  image?: string;
  command?: string;
  intendedIp?: string;
  runtimeIp?: string;
  terminalEnabled?: boolean;
  env?: string;
} {
  if (!meta) return {};
  const te = meta.terminal_enabled;
  return {
    roleLabel: meta.role_label,
    image: meta.image,
    command: meta.command,
    intendedIp: meta.intended_ip,
    runtimeIp: meta.actual_runtime_ip,
    terminalEnabled: te === undefined ? undefined : te !== 'false',
    env: meta.env,
  };
}

export function isTerminalEnabledForResource(meta: Record<string, string> | undefined | null): boolean {
  if (!meta) return true;
  return meta.terminal_enabled !== 'false';
}
