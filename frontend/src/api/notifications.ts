import { apiFetch } from './client';

export interface NotificationRow {
  id: string;
  user_id: string | null;
  project_id: string | null;
  type: string;
  title: string;
  message: string;
  status: 'unread' | 'read' | 'archived' | string;
  severity: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
}

export async function listNotifications(params?: {
  limit?: number;
  include_archived?: boolean;
}): Promise<NotificationRow[]> {
  const q = new URLSearchParams();
  if (params?.limit != null) q.set('limit', String(params.limit));
  if (params?.include_archived) q.set('include_archived', 'true');
  const suffix = q.toString() ? `?${q.toString()}` : '';
  return apiFetch<NotificationRow[]>(`/notifications${suffix}`);
}

export async function getUnreadNotificationCount(): Promise<number> {
  const r = await apiFetch<{ unread_count: number }>('/notifications/unread-count');
  return r.unread_count;
}

export async function markNotificationRead(id: string): Promise<NotificationRow> {
  return apiFetch<NotificationRow>(`/notifications/${id}/read`, { method: 'POST' });
}

export async function markAllNotificationsRead(): Promise<number> {
  const r = await apiFetch<{ marked_read: number }>('/notifications/read-all', { method: 'POST' });
  return r.marked_read;
}

export async function archiveNotification(id: string): Promise<NotificationRow> {
  return apiFetch<NotificationRow>(`/notifications/${id}/archive`, { method: 'POST' });
}
