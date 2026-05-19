/** Network allocation mode stored on topology.config.network_allocation_mode */

export type NetworkAllocationMode = 'managed' | 'intent';

export const DEFAULT_NETWORK_ALLOCATION_MODE: NetworkAllocationMode = 'managed';

export function readNetworkAllocationMode(
  config: Record<string, unknown> | null | undefined,
): NetworkAllocationMode {
  const raw = config?.network_allocation_mode;
  if (raw === 'intent' || raw === 'static' || raw === 'intent_ips') return 'intent';
  return 'managed';
}

export const NETWORK_ALLOCATION_HELP: Record<NetworkAllocationMode, string> = {
  managed:
    'Managed: CNS assigns safe runtime IPs automatically. Topology intent IPs are kept as design metadata only.',
  intent:
    'Intent: CNS tries to preserve your designed CIDRs and static IPs (Docker runtime only).',
};
