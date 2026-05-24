import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectMembersPanel } from './ProjectMembersPanel';

vi.mock('../api/projectMembers', () => ({
  listProjectMembers: vi.fn().mockResolvedValue([
    {
      id: 'm1',
      user_id: 'u1',
      email: 'owner@example.com',
      display_name: 'Owner',
      role: 'owner',
      created_at: '2026-01-01T00:00:00Z',
    },
  ]),
  listProjectInvitations: vi.fn().mockResolvedValue([
    {
      id: 'i1',
      project_id: 'p1',
      email: 'pending@example.com',
      role: 'member',
      status: 'pending',
      invited_by_user_id: 'u1',
      accepted_by_user_id: null,
      expires_at: '2026-12-31T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ]),
  createProjectInvitation: vi.fn(),
  revokeProjectInvitation: vi.fn(),
  patchProjectMemberRole: vi.fn(),
  removeProjectMember: vi.fn(),
  transferProjectOwnership: vi.fn(),
}));

describe('ProjectMembersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders members panel and invite controls for owners', () => {
    const html = renderToStaticMarkup(
      <ProjectMembersPanel projectId="p1" myRole="owner" />,
    );
    expect(html).toContain('Team &amp; members');
    expect(html).toContain('Send invite');
    expect(html).toContain('Your role: owner');
  });

  it('hides owner-only invite controls for viewers', () => {
    const html = renderToStaticMarkup(
      <ProjectMembersPanel projectId="p1" myRole="viewer" />,
    );
    expect(html).not.toContain('Send invite');
  });
});
