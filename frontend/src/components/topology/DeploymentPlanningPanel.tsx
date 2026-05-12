import { computeDeployReadiness, topologyLinkComponentCount } from '../../lib/deployReadiness';
import type { TopologyLinkResponse, TopologyNodeResponse } from '../../types/topology';

function parseIPv4(addr: string): number | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(addr.trim());
  if (!m) return null;
  const oct = [m[1], m[2], m[3], m[4]].map((x) => Number(x));
  if (oct.some((n) => n > 255)) return null;
  return (((oct[0] << 24) | (oct[1] << 16) | (oct[2] << 8) | oct[3]) >>> 0) as number;
}

function parseCidrRange(cidr: string): { start: number; end: number } | null {
  const [host, maskStr] = cidr.trim().split('/');
  if (!maskStr) return null;
  const mask = Number(maskStr);
  if (!Number.isFinite(mask) || mask < 0 || mask > 32) return null;
  const base = parseIPv4(host);
  if (base === null) return null;
  const hostBits = 32 - mask;
  const start = (base >>> hostBits) << hostBits;
  const end = start + (1 << hostBits) - 1;
  return { start, end };
}

function ipv4RangesOverlap(
  a: { start: number; end: number },
  b: { start: number; end: number },
): boolean {
  return a.start <= b.end && b.start <= a.end;
}

export interface DeploymentPlanningPanelProps {
  nodes: TopologyNodeResponse[];
  links: TopologyLinkResponse[];
  topologyStatus?: string | null;
  deploymentStatus?: string | null;
}

export function DeploymentPlanningPanel({
  nodes,
  links,
  topologyStatus,
  deploymentStatus,
}: DeploymentPlanningPanelProps) {
  const ips = nodes.map((n) => n.ip_address).filter((x): x is string => Boolean(x));
  const ipDup = (() => {
    const seen = new Map<string, number>();
    for (const ip of ips) {
      seen.set(ip, (seen.get(ip) ?? 0) + 1);
    }
    return [...seen.entries()].filter(([, c]) => c > 1).map(([ip]) => ip);
  })();

  const cidrRanges = links
    .map((l) => l.cidr)
    .filter((c): c is string => Boolean(c))
    .map((c) => ({ c, range: parseCidrRange(c) }))
    .filter((x): x is { c: string; range: { start: number; end: number } } => x.range !== null);

  const cidrOverlaps: string[] = [];
  for (let i = 0; i < cidrRanges.length; i += 1) {
    for (let j = i + 1; j < cidrRanges.length; j += 1) {
      if (ipv4RangesOverlap(cidrRanges[i].range, cidrRanges[j].range)) {
        cidrOverlaps.push(`${cidrRanges[i].c} ∩ ${cidrRanges[j].c}`);
      }
    }
  }

  const nodeIds = nodes.map((n) => n.id);
  const graphComps = topologyLinkComponentCount(nodeIds, links);
  const fragmented =
    nodes.length > 1 && graphComps > 1
      ? `Graph has ${graphComps} disconnected components (islands).`
      : null;

  const { deployable, blockingReasons, warnings: deployWarnings } = computeDeployReadiness(nodes, links);

  const readiness: { ok: boolean; text: string }[] = [
    { ok: nodes.length > 0, text: 'At least one node is defined.' },
    { ok: nodes.length <= 1 || links.length > 0, text: 'Multi-node labs include at least one link.' },
    { ok: ipDup.length === 0, text: 'No duplicate intent IPv4 addresses on nodes.' },
    { ok: cidrOverlaps.length === 0, text: 'No overlapping IPv4 link subnets (best-effort check).' },
    {
      ok: !(nodes.length > 1 && graphComps > 1),
      text: 'Single connected component (no isolated nodes).',
    },
    {
      ok: topologyStatus !== 'archived',
      text: 'Topology is not archived.',
    },
  ];

  const ready = readiness.every((r) => r.ok) && deployable;

  return (
    <div className="rounded-xl border border-zinc-700/80 bg-zinc-950/60 p-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-cns-inverse-muted">Deployment planning</h3>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <dt className="text-cns-inverse-label">Nodes</dt>
        <dd className="text-right font-mono text-zinc-200">{nodes.length}</dd>
        <dt className="text-cns-inverse-label">Links</dt>
        <dd className="text-right font-mono text-zinc-200">{links.length}</dd>
        <dt className="text-cns-inverse-label">Subnets (links with CIDR)</dt>
        <dd className="text-right font-mono text-zinc-200">{cidrRanges.length}</dd>
        <dt className="text-cns-inverse-label">Runtime deploy status</dt>
        <dd className="text-right font-mono text-zinc-200">{deploymentStatus ?? '—'}</dd>
      </dl>

      <div className="mt-4 border-t border-zinc-800 pt-3">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-cns-inverse-label">Readiness</div>
        <ul className="mt-2 space-y-1.5 text-[11px]">
          {readiness.map((r) => (
            <li key={r.text} className={r.ok ? 'text-emerald-300' : 'text-amber-200'}>
              {r.ok ? '✓' : '•'} {r.text}
            </li>
          ))}
        </ul>
        <div
          className={`mt-3 rounded-md border px-2 py-1.5 text-center text-[11px] font-semibold ${
            ready
              ? 'border-emerald-800/60 bg-emerald-950/40 text-emerald-100'
              : 'border-amber-800/60 bg-amber-950/30 text-amber-100'
          }`}
        >
          {ready ? 'Ready to deploy (intent checks passed)' : 'Review warnings before deploying'}
        </div>
        {!deployable && blockingReasons.length > 0 ? (
          <ul className="mt-2 space-y-1 text-[10px] text-amber-100">
            {blockingReasons.map((b) => (
              <li key={b}>• {b}</li>
            ))}
          </ul>
        ) : null}
        {deployWarnings.length > 0 ? (
          <ul className="mt-2 space-y-1 text-[10px] text-sky-100/90">
            {deployWarnings.map((w) => (
              <li key={w}>○ {w}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {ipDup.length > 0 && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/30 px-2 py-2 text-[11px] text-red-100">
          <div className="font-semibold">Duplicate intent IPs</div>
          <ul className="mt-1 list-inside list-disc font-mono">
            {ipDup.map((ip) => (
              <li key={ip}>{ip}</li>
            ))}
          </ul>
        </div>
      )}

      {fragmented ? (
        <div className="mt-3 rounded-md border border-sky-900/40 bg-sky-950/25 px-2 py-2 text-[11px] text-sky-100">
          <div className="font-semibold">Connectivity</div>
          <p className="mt-1">{fragmented} Consider consolidating links or using auto layout before deploy.</p>
        </div>
      ) : null}

      {cidrOverlaps.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-900/50 bg-amber-950/25 px-2 py-2 text-[11px] text-amber-50">
          <div className="font-semibold">Overlapping subnets</div>
          <ul className="mt-1 space-y-0.5 font-mono text-[10px] leading-snug">
            {cidrOverlaps.slice(0, 8).map((x) => (
              <li key={x}>{x}</li>
            ))}
            {cidrOverlaps.length > 8 ? <li>…and more</li> : null}
          </ul>
        </div>
      )}
    </div>
  );
}
