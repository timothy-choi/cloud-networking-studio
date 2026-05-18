/** Defaults for Runtime Access traffic operations (Step 46). */

export type TrafficServicePickRow = {
  id?: string;
  type?: string;
  name?: string;
  internal_url?: string | null;
};

/**
 * When running HTTP from a source *service* resource, prefer the other workload's
 * ``internal_url`` from Runtime Access (Docker DNS / K8s service URL), not a bare node UUID.
 */
export function pickDefaultHttpTrafficTarget(
  services: TrafficServicePickRow[],
  sourceResourceId: string,
): string {
  const trimmed = sourceResourceId.trim();
  const candidates = services.filter(
    (s) =>
      (!s.type || s.type === 'service') &&
      s.id &&
      s.id !== trimmed &&
      typeof s.internal_url === 'string' &&
      s.internal_url.trim().startsWith('http'),
  );
  if (candidates.length === 0) {
    return '';
  }
  const name = (x: TrafficServicePickRow) => (x.name || '').trim().toLowerCase();
  const preferred = candidates.find((s) => {
    const n = name(s);
    return n === 'server' || n === 'service' || n === 'api' || n === 'backend';
  });
  return (preferred ?? candidates[0]).internal_url!.trim();
}
