import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { formatNodeResourceLine, formatHostUtilization } from '../../api/topologyPlacement';

vi.mock('../../api/topologyPlacement', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/topologyPlacement')>();
  return {
    ...actual,
    getTopologyPlacementPlan: vi.fn(() => new Promise(() => {})),
    generateInfrastructureDeployment: vi.fn(),
  };
});

vi.mock('../../api/credentialProfiles', () => ({
  listCredentialProfiles: vi.fn(() => Promise.resolve([])),
}));

import { TopologyPlacementPlanningPanel } from './TopologyPlacementPlanningPanel';

describe('formatNodeResourceLine', () => {
  it('formats node resource line with name', () => {
    expect(
      formatNodeResourceLine({
        node_id: '1',
        node_name: 'cli-edge',
        resource_cpu: 0.25,
        resource_memory_mb: 256,
        resource_disk_gb: 5,
        replicas: 1,
        node_role: 'workload',
        exposure: 'internal',
        stateful: false,
      }),
    ).toBe('cli-edge: 0.25 CPU, 256 MB, 1 replica');
  });
});

describe('formatHostUtilization', () => {
  it('formats cpu and memory utilization lines', () => {
    expect(
      formatHostUtilization({
        host_index: 1,
        machine_type: 'e2-micro',
        cpu_used: 0.75,
        cpu_capacity: 2,
        memory_used_mb: 768,
        memory_capacity_mb: 1024,
        assigned_nodes: ['cli-edge', 'svc-origin'],
      }),
    ).toEqual({ cpu: '0.75 / 2', memory: '768 MB / 1024 MB' });
  });
});

describe('TopologyPlacementPlanningPanel', () => {
  it('renders planning shell while loading', () => {
    const html = renderToStaticMarkup(
      <TopologyPlacementPlanningPanel topologyId="topo-1" projectId="proj-1" />,
    );
    expect(html).toContain('Generic placement planner');
    expect(html).toContain('Loading placement plan');
  });
});
