import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { formatNodeResourceLine, formatHostUtilization } from '../../api/topologyPlacement';
import type { TopologyPlacementPlan } from '../../api/topologyPlacement';
import {
  PlacementPlanSection,
  PlacementWarningsSection,
  ResourceEstimateSection,
} from './TopologyPlacementPlanSections';

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

const samplePlan: TopologyPlacementPlan = {
  total_cpu: 0.75,
  total_memory_mb: 768,
  total_disk_gb: 13,
  total_replicas: 2,
  node_count: 2,
  workload_node_count: 2,
  placement_unit_count: 2,
  provider: 'gcp',
  recommended_host_count: 1,
  recommended_machine_type: 'e2-micro',
  machine_rationale: 'Fits on one e2-micro host.',
  exposed_ports: [],
  suggested_template_id: 'docker-vm',
  warnings: ['Public workload requires exposed ports: 8080.'],
  nodes: [
    {
      node_id: 'n1',
      node_name: 'cli-edge',
      resource_cpu: 0.25,
      resource_memory_mb: 256,
      resource_disk_gb: 5,
      cpu: 0.25,
      memory_mb: 256,
      disk_gb: 5,
      replicas: 1,
      node_role: 'workload',
      exposure: 'internal',
      stateful: false,
    },
    {
      node_id: 'n2',
      node_name: 'svc-origin',
      resource_cpu: 0.5,
      resource_memory_mb: 512,
      resource_disk_gb: 8,
      cpu: 0.5,
      memory_mb: 512,
      disk_gb: 8,
      replicas: 1,
      node_role: 'workload',
      exposure: 'public',
      stateful: false,
    },
  ],
  hosts: [
    {
      host_index: 1,
      machine_type: 'e2-micro',
      cpu_used: 0.75,
      cpu_capacity: 2,
      memory_used_mb: 768,
      memory_capacity_mb: 1024,
      disk_used_gb: 13,
      disk_capacity_gb: 30,
      assigned_nodes: ['cli-edge', 'svc-origin'],
    },
  ],
};

describe('formatNodeResourceLine', () => {
  it('formats node resource line with name and disk', () => {
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
    ).toBe('cli-edge: 0.25 CPU, 256 MB, 5 GB disk, 1 replica');
  });

  it('uses cpu/memory_mb/disk_gb aliases when present', () => {
    expect(
      formatNodeResourceLine({
        node_id: '1',
        node_name: 'api',
        resource_cpu: 99,
        resource_memory_mb: 99,
        resource_disk_gb: 99,
        cpu: 0.5,
        memory_mb: 512,
        disk_gb: 10,
        replicas: 2,
        node_role: 'workload',
        exposure: 'internal',
        stateful: false,
      }),
    ).toBe('api: 0.5 CPU, 512 MB, 10 GB disk, 2 replicas');
  });

  it('falls back when node_name is empty', () => {
    expect(
      formatNodeResourceLine({
        node_id: '1',
        node_name: '',
        resource_cpu: 0.25,
        resource_memory_mb: 256,
        resource_disk_gb: 5,
        replicas: 1,
        node_role: 'workload',
        exposure: 'internal',
        stateful: false,
      }),
    ).toBe('unnamed node: 0.25 CPU, 256 MB, 5 GB disk, 1 replica');
  });
});

describe('formatHostUtilization', () => {
  it('formats cpu, memory, and disk utilization lines', () => {
    expect(
      formatHostUtilization({
        host_index: 1,
        machine_type: 'e2-micro',
        cpu_used: 0.75,
        cpu_capacity: 2,
        memory_used_mb: 768,
        memory_capacity_mb: 1024,
        disk_used_gb: 13,
        disk_capacity_gb: 30,
        assigned_nodes: ['cli-edge', 'svc-origin'],
      }),
    ).toEqual({
      cpu: '0.75 / 2 vCPU',
      memory: '768 / 1024 MB',
      disk: '13 / 30 GB',
    });
  });
});

describe('ResourceEstimateSection', () => {
  it('renders node estimate rows with names', () => {
    const html = renderToStaticMarkup(<ResourceEstimateSection plan={samplePlan} />);
    expect(html).toContain('cli-edge: 0.25 CPU, 256 MB, 5 GB disk, 1 replica');
    expect(html).toContain('svc-origin: 0.5 CPU, 512 MB, 8 GB disk, 1 replica');
    expect(html).not.toContain(': CPU,');
  });
});

describe('PlacementPlanSection', () => {
  it('renders host assignment and utilization', () => {
    const html = renderToStaticMarkup(<PlacementPlanSection plan={samplePlan} />);
    expect(html).toContain('Placement plan');
    expect(html).toContain('Host 1');
    expect(html).toContain('e2-micro');
    expect(html).toContain('cli-edge');
    expect(html).toContain('svc-origin');
    expect(html).toContain('0.75 / 2 vCPU');
    expect(html).toContain('768 / 1024 MB');
    expect(html).toContain('13 / 30 GB');
  });
});

describe('PlacementWarningsSection', () => {
  it('renders placement warnings', () => {
    const html = renderToStaticMarkup(<PlacementWarningsSection warnings={samplePlan.warnings} />);
    expect(html).toContain('Public workload requires exposed ports: 8080.');
  });

  it('shows none when there are no warnings', () => {
    const html = renderToStaticMarkup(<PlacementWarningsSection warnings={[]} />);
    expect(html).toContain('None');
  });
});

describe('TopologyPlacementPlanningPanel', () => {
  it('renders planning shell while loading', () => {
    const html = renderToStaticMarkup(
      <TopologyPlacementPlanningPanel topologyId="topo-1" projectId="proj-1" />,
    );
    expect(html).toContain('Estimates capacity from topology node metadata');
    expect(html).toContain('Loading placement plan');
  });
});
