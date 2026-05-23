/** Image capability profiles and hints for freeform node configuration. */

export type ImageCapabilityProfile =
  | 'ubuntu-debian'
  | 'alpine'
  | 'python-runtime'
  | 'node-runtime'
  | 'go-runtime'
  | 'nginx'
  | 'netshoot'
  | 'redis'
  | 'postgres'
  | 'generic';

export interface ImageCapabilities {
  profile: ImageCapabilityProfile;
  /** Typical missing tools unless user bootstraps. */
  missingByDefault: string[];
  hints: string[];
  suggestsRuntimeCheck: boolean;
  httpByDefault: boolean;
  networkToolsAvailable: boolean;
}

export const BASE_OS_IMAGE_WARNING =
  'Base OS images usually do not include ping/ip/curl and do not run a service by default. Add a bootstrap command, use Debug Toolbox, or choose a service image.';

export const DEBUG_TOOLBOX_RECOMMENDATION =
  'For network diagnostics (curl, dig, ping, traceroute, tcpdump), add a Debug Toolbox node (nicolaka/netshoot).';

export function detectImageProfile(image: string): ImageCapabilityProfile {
  const il = image.trim().toLowerCase();
  if (!il) return 'generic';
  if (il.includes('netshoot')) return 'netshoot';
  if (il.includes('nginx') || il.includes('httpd')) return 'nginx';
  if (il.includes('redis')) return 'redis';
  if (il.includes('postgres')) return 'postgres';
  if (il.includes('ubuntu') || il.includes('debian')) return 'ubuntu-debian';
  if (il.includes('alpine') || il.includes('busybox')) return 'alpine';
  if (il.includes('python')) return 'python-runtime';
  if (il.includes('node') && !il.includes('node-exporter')) return 'node-runtime';
  if (il.includes('golang') || il.startsWith('go:')) return 'go-runtime';
  return 'generic';
}

export function commandLikelyStartsHttpServer(command: string): boolean {
  const c = command.toLowerCase();
  return (
    c.includes('http.server') ||
    c.includes('httpd') ||
    c.includes('nginx') ||
    c.includes('python -m http.server') ||
    c.includes('python3 -m http.server') ||
    c.includes('caddy') ||
    c.includes('uvicorn') ||
    c.includes('node server')
  );
}

export function getImageCapabilities(image: string, command = ''): ImageCapabilities {
  const profile = detectImageProfile(image);
  const cmd = command.trim();
  switch (profile) {
    case 'ubuntu-debian':
      return {
        profile,
        missingByDefault: ['ping', 'ip', 'curl', 'dig', 'nc'],
        hints: [
          BASE_OS_IMAGE_WARNING,
          'Ubuntu/Debian may need: apt-get install -y iproute2 iputils-ping curl dnsutils netcat-openbsd',
          DEBUG_TOOLBOX_RECOMMENDATION,
        ],
        suggestsRuntimeCheck: true,
        httpByDefault: false,
        networkToolsAvailable: false,
      };
    case 'alpine':
      return {
        profile,
        missingByDefault: ['ping', 'ip', 'curl', 'dig', 'nc'],
        hints: [
          BASE_OS_IMAGE_WARNING,
          'Alpine may need: apk add --no-cache iproute2 iputils curl bind-tools netcat-openbsd',
          DEBUG_TOOLBOX_RECOMMENDATION,
        ],
        suggestsRuntimeCheck: true,
        httpByDefault: false,
        networkToolsAvailable: false,
      };
    case 'python-runtime':
    case 'node-runtime':
    case 'go-runtime':
      return {
        profile,
        missingByDefault: cmd ? [] : ['http server'],
        hints: [
          'Runtime language images do not start a server unless your command starts one.',
          cmd && !commandLikelyStartsHttpServer(cmd)
            ? 'Use runtime health check, or add a server command (e.g. python -m http.server 80).'
            : 'Configure HTTP health check only when your command starts an HTTP listener.',
          DEBUG_TOOLBOX_RECOMMENDATION,
        ].filter(Boolean) as string[],
        suggestsRuntimeCheck: !commandLikelyStartsHttpServer(cmd),
        httpByDefault: false,
        networkToolsAvailable: false,
      };
    case 'nginx':
      return {
        profile,
        missingByDefault: [],
        hints: ['Nginx exposes HTTP on port 80 by default.'],
        suggestsRuntimeCheck: false,
        httpByDefault: true,
        networkToolsAvailable: false,
      };
    case 'netshoot':
      return {
        profile,
        missingByDefault: [],
        hints: ['Debug Toolbox includes ping, ip, curl, dig, traceroute, and tcpdump.'],
        suggestsRuntimeCheck: true,
        httpByDefault: false,
        networkToolsAvailable: true,
      };
    case 'redis':
      return {
        profile,
        missingByDefault: [],
        hints: ['Redis listens on TCP 6379 — use a TCP health check.'],
        suggestsRuntimeCheck: false,
        httpByDefault: false,
        networkToolsAvailable: false,
      };
    case 'postgres':
      return {
        profile,
        missingByDefault: [],
        hints: ['PostgreSQL listens on TCP 5432 — use a TCP health check.'],
        suggestsRuntimeCheck: false,
        httpByDefault: false,
        networkToolsAvailable: false,
      };
    default:
      return {
        profile,
        missingByDefault: [],
        hints: [DEBUG_TOOLBOX_RECOMMENDATION],
        suggestsRuntimeCheck: true,
        httpByDefault: false,
        networkToolsAvailable: false,
      };
  }
}

export function inferHealthWarningsFromCapabilities(
  image: string,
  command: string,
  checkType: string,
): string[] {
  const caps = getImageCapabilities(image, command);
  const warnings = [...caps.hints];
  if (
    checkType === 'http' &&
    !caps.httpByDefault &&
    !commandLikelyStartsHttpServer(command) &&
    caps.profile !== 'nginx'
  ) {
    warnings.push(
      'No HTTP service appears to be running. Configure a server command or use runtime/TCP check.',
    );
  }
  return [...new Set(warnings)];
}
