import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/topologyPlacement', () => ({
  getTopologyPlacementPlan: vi.fn(() => new Promise(() => {})),
  generateInfrastructureDeployment: vi.fn(),
}));

vi.mock('../../api/credentialProfiles', () => ({
  listCredentialProfiles: vi.fn(() => Promise.resolve([])),
}));

import { TopologyPlacementPlanningPanel } from './TopologyPlacementPlanningPanel';

describe('TopologyPlacementPlanningPanel', () => {
  it('renders planning shell while loading', () => {
    const html = renderToStaticMarkup(
      <TopologyPlacementPlanningPanel topologyId="topo-1" projectId="proj-1" />,
    );
    expect(html).toContain('Generic placement planner');
    expect(html).toContain('Loading placement plan');
  });

  it('renders generate section when not read-only', () => {
    const html = renderToStaticMarkup(
      <TopologyPlacementPlanningPanel topologyId="topo-1" projectId="proj-1" readOnly={false} />,
    );
    expect(html).toContain('Refresh plan');
  });
});
