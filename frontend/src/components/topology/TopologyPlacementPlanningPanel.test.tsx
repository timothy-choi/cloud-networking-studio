import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import {
  formatNodeResourceLine,
  formatHostUtilization,
  isStrategySelectable,
  runtimeDeploymentModelLabel,
  runtimeHostModelLabel,
} from '../../api/topologyPlacement';
import type {
  CostCapacityAnalysis,
  RuntimeStrategyPlan,
  StrategyRecommendation,
  TopologyPlacementPlan,
} from '../../api/topologyPlacement';
import {
  CostCapacitySection,
  DeploymentStrategySection,
  PlacementConstraintsSection,
  PlacementPlanSection,
  PlacementWarningsSection,
  ResourceEstimateSection,
  RuntimeStrategySection,
} from './TopologyPlacementPlanSections';

vi.mock('../../api/topologyPlacement', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/topologyPlacement')>();
  return {
    ...actual,
    getTopologyPlacementPlan: vi.fn(() => new Promise(() => {})),
    getTopologyStrategyRecommendation: vi.fn(() => new Promise(() => {})),
    getTopologyCostCapacityAnalysis: vi.fn(() => new Promise(() => {})),
    getTopologyRuntimeStrategyPlan: vi.fn(() => new Promise(() => {})),
    listPlacementConstraints: vi.fn(() => Promise.resolve([])),
    createPlacementConstraint: vi.fn(),
    deletePlacementConstraint: vi.fn(),
    getAiInfrastructureAdvice: vi.fn(() => new Promise(() => {})),
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
      utilization: {
        cpu_utilization: 38,
        memory_utilization: 75,
        disk_utilization: 43,
      },
      assigned_nodes: ['cli-edge', 'svc-origin'],
    },
  ],
};

const sampleStrategy: StrategyRecommendation = {
  recommended_strategy: 'docker-vm',
  alternatives: ['docker-multi-vm', 'k8s-cluster'],
  reasons: [
    'Topology fits on a single host',
    'No unsupported placement constraints detected',
    'Remote Docker runtime is supported',
  ],
  warnings: [],
  strategies: [
    {
      id: 'docker-vm',
      display_name: 'Docker VM',
      status: 'available',
      description: 'Single VM',
      min_hosts: 1,
      max_hosts: 1,
      supports_multi_host: false,
      supports_stateful: true,
      supports_public_ingress: true,
      runtime_type: 'docker',
      template_id: 'docker-vm',
    },
    {
      id: 'docker-multi-vm',
      display_name: 'Docker Multi-VM',
      status: 'planning_only',
      description: 'Multi VM',
      min_hosts: 2,
      max_hosts: 10,
      supports_multi_host: true,
      supports_stateful: true,
      supports_public_ingress: true,
      runtime_type: 'docker',
      template_id: 'docker-multi-vm',
    },
    {
      id: 'k8s-cluster',
      display_name: 'Kubernetes Cluster',
      status: 'future',
      description: 'K8s',
      min_hosts: 1,
      max_hosts: 999,
      supports_multi_host: true,
      supports_stateful: true,
      supports_public_ingress: true,
      runtime_type: 'kubernetes',
      template_id: 'k8s-cluster',
    },
  ],
};

const sampleRuntimeStrategyPlan: RuntimeStrategyPlan = {
  recommended_runtime_strategy: 'docker-vm',
  selected_runtime_strategy: 'docker-vm',
  runtime_strategy: {
    id: 'docker-vm',
    display_name: 'Docker VM',
    status: 'available',
    runtime_provider: 'remote_docker',
    host_model: 'single_host',
    deployment_model: 'docker_compose',
    supports_multi_host: false,
    supports_runtime_target_generation: true,
    supports_external_deployment: true,
    description: 'Single remote Docker host.',
  },
  capabilities: {
    runtime_target_generation: true,
    external_deployment: true,
    multi_host: false,
  },
  runtime_target_requirements: [
    { key: 'ssh_credential', label: 'SSH credential', description: 'SSH credential profile for host access', required: true },
    { key: 'docker', label: 'Docker', description: 'Docker engine installed on the remote host', required: true },
    { key: 'docker_compose', label: 'Docker Compose', description: 'Docker Compose available on the remote host', required: true },
    { key: 'remote_workdir', label: 'remote_workdir', description: 'Writable remote_workdir on the target host', required: true },
  ],
  deployment_requirements: [],
  unsupported_features: [],
  can_generate_infrastructure: true,
  host_count: 1,
  placement_constraints_count: 0,
};

const sampleRuntimeStrategyPlanBlocked: RuntimeStrategyPlan = {
  ...sampleRuntimeStrategyPlan,
  selected_runtime_strategy: 'docker-multi-vm',
  runtime_strategy: {
    ...sampleRuntimeStrategyPlan.runtime_strategy,
    id: 'docker-multi-vm',
    display_name: 'Docker Multi-VM',
    status: 'planning_only',
    runtime_provider: 'remote_docker_cluster',
    host_model: 'multi_host',
    deployment_model: 'multi_host_compose',
    supports_multi_host: true,
    supports_runtime_target_generation: false,
    supports_external_deployment: false,
    description: 'Planning only.',
  },
  capabilities: {
    runtime_target_generation: false,
    external_deployment: false,
    multi_host: true,
  },
  unsupported_features: ['Multi-host infrastructure apply', 'Runtime target generation for multiple hosts'],
  can_generate_infrastructure: false,
  generation_block_reason: 'Runtime strategy is planning-only and cannot generate infrastructure yet.',
  host_count: 2,
};

const sampleCostCapacity: CostCapacityAnalysis = {
  cost_estimate: {
    provider: 'gcp',
    machine_type: 'e2-micro',
    host_count: 1,
    estimated_monthly_cost: {
      low: 8,
      high: 12,
      currency: 'USD',
    },
  },
  capacity: {
    cpu_utilization_percent: 38,
    memory_utilization_percent: 75,
    disk_utilization_percent: 33,
  },
  headroom: {
    cpu_headroom_percent: 62,
    memory_headroom_percent: 25,
    disk_headroom_percent: 67,
    remaining_cpu: 1.25,
    remaining_memory_mb: 256,
    remaining_disk_gb: 20,
  },
  scaling_risk: {
    scaling_risk: 'MEDIUM',
    reasons: ['Memory utilization exceeds 75%'],
  },
  alternatives: {
    cheaper_alternative: null,
    safer_alternative: 'e2-small',
  },
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

  it('includes the resource source when present', () => {
    expect(
      formatNodeResourceLine({
        node_id: '1',
        node_name: 'cli-edge',
        resource_cpu: 1.5,
        resource_memory_mb: 1024,
        resource_disk_gb: 10,
        replicas: 1,
        resource_source: 'explicit',
        node_role: 'workload',
        exposure: 'internal',
        stateful: false,
      }),
    ).toBe('cli-edge: 1.5 CPU, 1024 MB, 10 GB disk, 1 replica, source: explicit');
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
    expect(html).toContain('Multi-Host Placement Plan');
    expect(html).toContain('Mode: first_fit');
    expect(html).toContain('Host 1');
    expect(html).toContain('e2-micro');
    expect(html).toContain('cli-edge');
    expect(html).toContain('svc-origin');
    expect(html).toContain('0.75 / 2 vCPU');
    expect(html).toContain('768 / 1024 MB');
    expect(html).toContain('13 / 30 GB');
    expect(html).toContain('CPU utilization');
    expect(html).toContain('38%');
  });
});

describe('PlacementConstraintsSection', () => {
  it('renders constraints and creation controls', () => {
    const html = renderToStaticMarkup(
      <PlacementConstraintsSection
        constraints={[
          {
            id: 'c1',
            topology_id: 'topo-1',
            constraint_type: 'different_host',
            node_a: 'worker-a',
            node_b: 'worker-b',
            created_at: '2026-06-01T00:00:00Z',
          },
        ]}
        nodes={['worker-a', 'worker-b']}
        creating={false}
        form={{ constraint_type: 'preferred_host', node_a: 'worker-a', node_b: '', preferred_host: '2' }}
        onChangeForm={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(html).toContain('Placement constraints');
    expect(html).toContain('different_host');
    expect(html).toContain('worker-a / worker-b');
    expect(html).toContain('Remove');
    expect(html).toContain('Preferred host');
    expect(html).toContain('Add constraint');
  });

  it('hides remove buttons in read-only mode', () => {
    const html = renderToStaticMarkup(
      <PlacementConstraintsSection
        constraints={[
          {
            id: 'c1',
            topology_id: 'topo-1',
            constraint_type: 'different_host',
            node_a: 'cli-edge',
            node_b: 'svc-origin',
            created_at: '2026-06-01T00:00:00Z',
          },
        ]}
        nodes={['cli-edge', 'svc-origin']}
        creating={false}
        readOnly
        form={{ constraint_type: 'different_host', node_a: '', node_b: '', preferred_host: '1' }}
        onChangeForm={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(html).toContain('cli-edge / svc-origin');
    expect(html).not.toContain('Remove');
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

describe('runtime strategy helpers', () => {
  it('formats host and deployment model labels', () => {
    expect(runtimeHostModelLabel('single_host')).toBe('single host');
    expect(runtimeDeploymentModelLabel('docker_compose')).toBe('Docker Compose');
  });
});

describe('RuntimeStrategySection', () => {
  it('renders runtime strategy capabilities and requirements', () => {
    const html = renderToStaticMarkup(<RuntimeStrategySection plan={sampleRuntimeStrategyPlan} />);
    expect(html).toContain('Runtime strategy');
    expect(html).toContain('docker-vm');
    expect(html).toContain('remote_docker');
    expect(html).toContain('single host');
    expect(html).toContain('Docker Compose');
    expect(html).toContain('SSH credential');
    expect(html).toContain('Runtime target generation');
    expect(html).toContain('External deployment');
  });

  it('renders unsupported features and block reason for planning-only strategies', () => {
    const html = renderToStaticMarkup(<RuntimeStrategySection plan={sampleRuntimeStrategyPlanBlocked} />);
    expect(html).toContain('docker-multi-vm');
    expect(html).toContain('planning only');
    expect(html).toContain('Multi-host infrastructure apply');
    expect(html).toContain('planning-only and cannot generate infrastructure yet');
  });
});

describe('DeploymentStrategySection', () => {
  it('renders recommended strategy, reasons, and alternatives', () => {
    const html = renderToStaticMarkup(
      <DeploymentStrategySection
        recommendation={sampleStrategy}
        selectedStrategyId="docker-vm"
        onSelectStrategy={() => {}}
      />,
    );
    expect(html).toContain('Deployment strategy');
    expect(html).toContain('docker-vm');
    expect(html).toContain('Topology fits on a single host');
    expect(html).toContain('docker-multi-vm');
    expect(html).toContain('planning only');
    expect(html).toContain('k8s-cluster');
    expect(html).toContain('future');
  });
});

describe('CostCapacitySection', () => {
  it('renders estimated cost, capacity, risk, and alternatives', () => {
    const html = renderToStaticMarkup(<CostCapacitySection analysis={sampleCostCapacity} />);
    expect(html).toContain('Cost &amp; Capacity');
    expect(html).toContain('GCP');
    expect(html).toContain('e2-micro');
    expect(html).toContain('$8-12/month');
    expect(html).toContain('CPU: 38% used');
    expect(html).toContain('Memory: 75% used');
    expect(html).toContain('Disk: 33% used');
    expect(html).toContain('CPU: 62% remaining');
    expect(html).toContain('MEDIUM');
    expect(html).toContain('Memory utilization exceeds 75%');
    expect(html).toContain('Safer: e2-small');
  });
});

describe('isStrategySelectable', () => {
  it('allows only available strategies', () => {
    expect(isStrategySelectable('available')).toBe(true);
    expect(isStrategySelectable('planning_only')).toBe(false);
    expect(isStrategySelectable('future')).toBe(false);
  });
});

describe('TopologyPlacementPlanningPanel', () => {
  it('renders planning shell while loading', () => {
    const html = renderToStaticMarkup(
      <TopologyPlacementPlanningPanel topologyId="topo-1" projectId="proj-1" />,
    );
    expect(html).toContain('Estimates capacity, plans host placement');
    expect(html).toContain('Loading placement plan');
  });
});
