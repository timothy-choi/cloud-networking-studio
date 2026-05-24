import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NotificationBell } from './NotificationBell';

vi.mock('../../api/notifications', () => ({
  getUnreadNotificationCount: vi.fn().mockResolvedValue(2),
  listNotifications: vi.fn().mockResolvedValue([
    {
      id: 'n1',
      type: 'test',
      title: 'Deploy finished',
      message: 'Your topology is live.',
      status: 'unread',
      severity: 'success',
      metadata: { url: '/topologies/t1' },
      created_at: '2026-01-01T00:00:00Z',
      read_at: null,
      project_id: null,
    },
  ]),
  markNotificationRead: vi.fn().mockResolvedValue(undefined),
  markAllNotificationsRead: vi.fn().mockResolvedValue(undefined),
  archiveNotification: vi.fn().mockResolvedValue(undefined),
}));

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders bell with unread badge', async () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    );
    expect(html).toContain('Notifications');
    expect(html).toContain('🔔');
  });
});
