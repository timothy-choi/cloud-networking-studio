// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RuntimeStrategyPlan } from '../../api/topologyPlacement';
import { RuntimePackageExportSection } from './TopologyPlacementPlanSections';

const samplePlan: RuntimeStrategyPlan = {
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
  runtime_target_requirements: [],
  deployment_requirements: [],
  unsupported_features: [],
  can_generate_infrastructure: true,
  host_count: 1,
  placement_constraints_count: 0,
};

const generateRuntimePackage = vi.fn();
const downloadRuntimePackage = vi.fn();

vi.mock('../../api/topologyPlacement', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/topologyPlacement')>();
  return {
    ...actual,
    generateRuntimePackage: (...args: unknown[]) => generateRuntimePackage(...args),
    downloadRuntimePackage: (...args: unknown[]) => downloadRuntimePackage(...args),
  };
});

describe('RuntimePackageExportSection interactions', () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.clearAllMocks();
  });

  function mount() {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <RuntimePackageExportSection topologyId="topo-1" strategyId="docker-vm" runtimePlan={samplePlan} />,
      );
    });
  }

  it('generates package and renders files list with download button', async () => {
    generateRuntimePackage.mockResolvedValue({
      package_id: 'pkg-123',
      strategy_id: 'docker-vm',
      status: 'generated',
      files: ['docker-compose.yml', 'README.md'],
      download_url: '/api/runtime-packages/pkg-123/download',
      planning_only: false,
      limitations: [],
    });
    mount();

    const button = container.querySelector('button');
    expect(button?.textContent).toContain('Generate Runtime Package');

    await act(async () => {
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });

    await vi.waitFor(() => {
      expect(generateRuntimePackage).toHaveBeenCalledWith('topo-1', {
        strategy_id: 'docker-vm',
        provider: 'gcp',
        placement_mode: 'first_fit',
      });
    });

    expect(container.textContent).toContain('docker-compose.yml');
    expect(container.textContent).toContain('README.md');
    expect(container.textContent).toContain('Download ZIP');
  });

  it('downloads zip when download button is clicked', async () => {
    generateRuntimePackage.mockResolvedValue({
      package_id: 'pkg-456',
      strategy_id: 'docker-vm',
      status: 'generated',
      files: ['README.md'],
      download_url: '/api/runtime-packages/pkg-456/download',
      planning_only: false,
      limitations: [],
    });
    downloadRuntimePackage.mockResolvedValue(undefined);
    mount();

    await act(async () => {
      container.querySelector('button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });

    await vi.waitFor(() => expect(container.textContent).toContain('Download ZIP'));

    const downloadButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      btn.textContent?.includes('Download ZIP'),
    );
    await act(async () => {
      downloadButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });

    expect(downloadRuntimePackage).toHaveBeenCalledWith('pkg-456');
  });
});
