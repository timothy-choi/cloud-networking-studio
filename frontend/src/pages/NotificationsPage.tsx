import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatApiError } from '../api/client';
import {
  archiveNotification,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationRow,
} from '../api/notifications';

export function NotificationsPage() {
  const [rows, setRows] = useState<NotificationRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await listNotifications({ limit: 100, include_archived: true }));
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Notifications</h1>
        <p className="mt-1 text-sm text-cns-muted">Deployment, quota, token, and platform activity for your account.</p>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded border border-zinc-300 px-3 py-1.5 text-xs dark:border-zinc-600"
          onClick={() => void markAllNotificationsRead().then(() => load())}
        >
          Mark all read
        </button>
        <button type="button" className="text-xs text-emerald-700 hover:underline dark:text-emerald-400" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}
      {loading ? <p className="text-sm text-cns-muted">Loading…</p> : null}
      <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900/80">
        {rows.map((n) => (
          <li key={n.id} className="px-4 py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{n.title}</div>
                <p className="mt-1 text-xs text-cns-muted">{n.message}</p>
                <p className="mt-1 text-[10px] text-cns-muted">
                  {n.type} · {n.status} · {new Date(n.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex gap-2 text-xs">
                {n.status === 'unread' ? (
                  <button type="button" className="text-emerald-700 hover:underline dark:text-emerald-400" onClick={() => void markNotificationRead(n.id).then(() => load())}>
                    Mark read
                  </button>
                ) : null}
                {n.status !== 'archived' ? (
                  <button type="button" className="text-cns-muted hover:underline" onClick={() => void archiveNotification(n.id).then(() => load())}>
                    Archive
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
        {!loading && rows.length === 0 ? (
          <li className="px-4 py-8 text-center text-sm text-cns-muted">No notifications.</li>
        ) : null}
      </ul>
    </div>
  );
}
