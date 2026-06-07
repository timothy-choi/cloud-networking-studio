import type { TopologyNodeResponse } from '../types/topology';

export const NODE_EXPOSURE_TYPES = ['internal', 'private', 'public'] as const;
export type NodeExposure = (typeof NODE_EXPOSURE_TYPES)[number];

export interface NodeResourceFields {
  cpu: string;
  memoryMb: string;
  diskGb: string;
  replicas: string;
  exposure: NodeExposure;
  stateful: boolean;
  requiredPorts: string;
}

export interface ParsedNodeResources {
  cpu: number;
  memory_mb: number;
  disk_gb: number;
  replicas: number;
  exposure: NodeExposure;
  stateful: boolean;
  required_ports: number[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readConfigValue(config: Record<string, unknown>, keys: string[]): unknown {
  const resources = isRecord(config.resources) ? config.resources : {};
  for (const key of keys) {
    const value = config[key] ?? resources[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return undefined;
}

export function readNodeResourceFields(node: TopologyNodeResponse): NodeResourceFields {
  const config = node.config ?? {};
  const exposure = String(config.exposure ?? 'internal');
  return {
    cpu: String(readConfigValue(config, ['resource_cpu', 'cpu_request', 'cpu']) ?? 0.5),
    memoryMb: String(readConfigValue(config, ['resource_memory_mb', 'memory_request_mb', 'memory_mb']) ?? 512),
    diskGb: String(readConfigValue(config, ['resource_disk_gb', 'disk_request_gb', 'disk_gb']) ?? 5),
    replicas: String(readConfigValue(config, ['replicas']) ?? 1),
    exposure: (NODE_EXPOSURE_TYPES.includes(exposure as NodeExposure) ? exposure : 'internal') as NodeExposure,
    stateful: config.stateful === true || String(config.stateful ?? '').toLowerCase() === 'true',
    requiredPorts: Array.isArray(config.required_ports) ? config.required_ports.join(', ') : '',
  };
}

export function parseResourceNumber(
  _label: string,
  value: string,
  min: number,
  max: number,
  integer = false,
): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max || (integer && !Number.isInteger(parsed))) {
    return null;
  }
  return integer ? Math.trunc(parsed) : parsed;
}

export function parseRequiredPorts(value: string): number[] | null {
  const trimmed = value.trim();
  if (!trimmed) return [];
  const ports = trimmed
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : Number.NaN));
  if (ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65535)) {
    return null;
  }
  return Array.from(new Set(ports)).sort((a, b) => a - b);
}

export function validateNodeResourceFields(fields: NodeResourceFields): string | null {
  if (parseResourceNumber('CPU', fields.cpu, 0.001, 128) == null) {
    return 'CPU must be between 0.001 and 128.';
  }
  if (parseResourceNumber('Memory MB', fields.memoryMb, 128, 1048576, true) == null) {
    return 'Memory MB must be an integer between 128 and 1048576.';
  }
  if (parseResourceNumber('Disk GB', fields.diskGb, 1, 65536) == null) {
    return 'Disk GB must be between 1 and 65536.';
  }
  if (parseResourceNumber('Replicas', fields.replicas, 1, 100, true) == null) {
    return 'Replicas must be an integer between 1 and 100.';
  }
  if (parseRequiredPorts(fields.requiredPorts) == null) {
    return 'Required ports must be a comma-separated list of integers between 1 and 65535.';
  }
  return null;
}

export function parseNodeResourceFields(fields: NodeResourceFields): ParsedNodeResources | null {
  const cpu = parseResourceNumber('CPU', fields.cpu, 0.001, 128);
  const memory_mb = parseResourceNumber('Memory MB', fields.memoryMb, 128, 1048576, true);
  const disk_gb = parseResourceNumber('Disk GB', fields.diskGb, 1, 65536);
  const replicas = parseResourceNumber('Replicas', fields.replicas, 1, 100, true);
  const required_ports = parseRequiredPorts(fields.requiredPorts);
  if (cpu == null || memory_mb == null || disk_gb == null || replicas == null || required_ports == null) {
    return null;
  }
  return {
    cpu,
    memory_mb,
    disk_gb,
    replicas,
    exposure: fields.exposure,
    stateful: fields.stateful,
    required_ports,
  };
}

/** Merge resource/planning fields into an existing node config without dropping other keys. */
export function mergeNodeResourceIntoConfig(
  base: Record<string, unknown> | null | undefined,
  resources: ParsedNodeResources,
): Record<string, unknown> {
  const cfg: Record<string, unknown> = { ...(base ?? {}) };
  const existingResources = isRecord(cfg.resources) ? cfg.resources : {};
  cfg.resources = {
    ...existingResources,
    cpu: resources.cpu,
    memory_mb: resources.memory_mb,
    disk_gb: resources.disk_gb,
    replicas: resources.replicas,
  };
  cfg.exposure = resources.exposure;
  cfg.stateful = resources.stateful;
  cfg.required_ports = resources.required_ports;
  return cfg;
}
