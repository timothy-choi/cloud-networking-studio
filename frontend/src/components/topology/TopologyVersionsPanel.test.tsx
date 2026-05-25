import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { TopologyVersionsPanel } from './TopologyVersionsPanel';

vi.mock('../../api/topologyVersions', () => ({
  listTopologyVersions: vi.fn().mockResolvedValue([]),
  createTopologyVersion: vi.fn(),
  diffTopologyVersions: vi.fn(),
  rollbackTopologyVersion: vi.fn(),
}));

describe('TopologyVersionsPanel', () => {
  it('renders loading state and save control shell', () => {
    const html = renderToStaticMarkup(<TopologyVersionsPanel topologyId="t1" isOwner />);
    expect(html).toContain('Loading versions');
  });
});
