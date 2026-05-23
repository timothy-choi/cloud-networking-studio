/** Protocol-aware health check configuration stored in node.config.health_check */

export type HealthCheckType = 'runtime' | 'tcp' | 'http' | 'command' | 'none';

export interface HealthCheckFields {
  check_type: HealthCheckType;
  port: string;
  path: string;
  command: string;
  expected_status: string;
  timeout_ms: string;
}

export const HEALTH_CHECK_TYPE_LABELS: Record<HealthCheckType, string> = {
  runtime: 'Runtime only (container running)',
  tcp: 'TCP port reachable',
  http: 'HTTP endpoint',
  command: 'Custom command',
  none: 'Disabled',
};

export function emptyHealthCheckFields(): HealthCheckFields {
  return {
    check_type: 'runtime',
    port: '',
    path: '/',
    command: '',
    expected_status: '200',
    timeout_ms: '8000',
  };
}

export function readHealthCheckFields(raw: unknown): HealthCheckFields {
  const base = emptyHealthCheckFields();
  if (raw == null || raw === '') return base;
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return base;
    if (s.startsWith('{')) {
      try {
        return readHealthCheckFields(JSON.parse(s));
      } catch {
        return { ...base, check_type: 'http', path: s };
      }
    }
    return { ...base, check_type: 'http', path: s };
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const t = typeof o.check_type === 'string' ? (o.check_type as HealthCheckType) : base.check_type;
    return {
      check_type: t,
      port: o.port != null ? String(o.port) : '',
      path: typeof o.path === 'string' ? o.path : base.path,
      command: Array.isArray(o.command)
        ? o.command.map(String).join(' ')
        : typeof o.command === 'string'
          ? o.command
          : '',
      expected_status: o.expected_status != null ? String(o.expected_status) : base.expected_status,
      timeout_ms: o.timeout_ms != null ? String(o.timeout_ms) : base.timeout_ms,
    };
  }
  return base;
}

export function healthCheckToConfig(fields: HealthCheckFields): Record<string, unknown> | null {
  const t = fields.check_type;
  if (t === 'none') {
    return { check_type: 'none' };
  }
  const out: Record<string, unknown> = { check_type: t };
  if (t === 'http') {
    out.path = fields.path.trim() || '/';
    const p = Number(fields.port);
    if (Number.isFinite(p) && p > 0) out.port = p;
    const es = Number(fields.expected_status);
    if (Number.isFinite(es) && es > 0) out.expected_status = es;
  }
  if (t === 'tcp') {
    const p = Number(fields.port);
    if (Number.isFinite(p) && p > 0) out.port = p;
  }
  if (t === 'command') {
    const cmd = fields.command.trim();
    if (cmd) out.command = cmd;
  }
  const tm = Number(fields.timeout_ms);
  if (Number.isFinite(tm) && tm > 0) out.timeout_ms = tm;
  return out;
}

export function inferHealthWarnings(image: string, command: string, hc: HealthCheckFields): string[] {
  const warnings: string[] = [];
  const il = image.toLowerCase();
  const base =
    il.includes('ubuntu') ||
    il.includes('debian') ||
    il.includes('alpine') ||
    il.includes('python') ||
    il.includes('node');
  if (base && !command.trim()) {
    warnings.push(
      'Base/runtime images usually need a long-running command such as sleep infinity, or a server startup command.',
    );
  }
  if (hc.check_type === 'http' && base && !il.includes('nginx') && !il.includes('httpd')) {
    warnings.push('This image may not expose an HTTP service unless you configure one.');
  }
  if (hc.check_type === 'http' || hc.check_type === 'tcp') {
    warnings.push(
      'For curl, dig, ping, traceroute, tcpdump, add a Debug Toolbox node (e.g. nicolaka/netshoot).',
    );
  }
  return warnings;
}

export const DEBUG_TOOLBOX_HINT =
  'For curl, dig, ping, traceroute, tcpdump, use a Debug Toolbox node (nicolaka/netshoot).';
