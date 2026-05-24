import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { AcceptInvitationPage } from './AcceptInvitationPage';

vi.mock('../api/projectMembers', () => ({
  acceptInvitation: vi.fn(),
  declineInvitation: vi.fn(),
}));

describe('AcceptInvitationPage', () => {
  it('renders accept and decline actions when token is present', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/invitations/accept?token=test-token']}>
        <AcceptInvitationPage />
      </MemoryRouter>,
    );
    expect(html).toContain('Project invitation');
    expect(html).toContain('Accept invitation');
    expect(html).toContain('Decline');
  });

  it('shows missing-token error when token query param is absent', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/invitations/accept']}>
        <AcceptInvitationPage />
      </MemoryRouter>,
    );
    expect(html).toContain('Accept invitation');
    expect(html).toMatch(/disabled/);
  });
});
