import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatApiError } from '../../api/client';
import {
  archiveNotification,
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationRow,
} from '../../api/notifications';

function severityClass(severity: string): string {
  if (severity === 'error') return 'text-red-700 dark:text-red-300';
  if (severity === 'warning') return 'text-amber-800 dark:text-amber-200';
  if (severity === 'success') return 'text-emerald-700 dark:text-emerald-300';
  return 'text-zinc-700 dark:text-zinc-200';
}

function notificationLink(meta: Record<string, unknown> | null): string | null {
  if (!meta) return null;
  const url = meta.url;
  if (typeof url === 'string' && url.startsWith('/')) return url;
  const tid = meta.topology_id;
  if (typeof tid === 'string') return `/topologies/${tid}`;
  return null;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [rows, setRows] = useState<NotificationRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [count, list] = await Promise.all([
        getUnreadNotificationCount(),
        listNotifications({ limit: 12 }),
      ]);
      setUnread(count);
      setRows(list);
      setErr(null);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    void refresh().finally(() => setLoading(false));
  }, [open, refresh]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  async function onMarkRead(id: string) {
    try {
      await markNotificationRead(id);
      await refresh();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function onMarkAllRead() {
    try {
      await markAllNotificationsRead();
      await refresh();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function onArchive(id: string) {
    try {
      await archiveNotification(id);
      await refresh();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="Notifications"
        className="relative rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
        onClick={() => setOpen((v) => !v)}
      >
        🔔
        {unread > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-2 dark:border-zinc-700">
            <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">Notifications</span>
            <div className="flex items-center gap-2">
              <Link
                to="/notifications"
                className="text-[11px] font-medium text-emerald-700 hover:underline dark:text-emerald-400"
                onClick={() => setOpen(false)}
              >
                View all
              </Link>
              <button
                type="button"
                className="text-[11px] text-cns-muted hover:underline"
                onClick={() => void onMarkAllRead()}
              >
                Mark all read
              </button>
            </div>
          </div>
          {err ? <p className="px-3 py-2 text-xs text-red-700 dark:text-red-300">{err}</p> : null}
          {loading ? <p className="px-3 py-3 text-xs text-cns-muted">Loading…</p> : null}
          <ul className="max-h-80 divide-y divide-zinc-100 overflow-auto dark:divide-zinc-800">
            {rows.length === 0 && !loading ? (
              <li className="px-3 py-4 text-xs text-cns-muted">No notifications yet.</li>
            ) : null}
            {rows.map((n) => {
              const href = notificationLink(n.metadata);
              return (
                <li key={n.id} className="px-3 py-2 text-xs">
                  <div className={`font-medium ${severityClass(n.severity)}`}>{n.title}</div>
                  <p className="mt-0.5 text-cns-muted">{n.message}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {href ? (
                      <Link
                        to={href}
                        className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
                        onClick={() => setOpen(false)}
                      >
                        Open
                      </Link>
                    ) : null}
                    {n.status === 'unread' ? (
                      <button type="button" className="text-cns-muted hover:underline" onClick={() => void onMarkRead(n.id)}>
                        Mark read
                      </button>
                    ) : null}
                    <button type="button" className="text-cns-muted hover:underline" onClick={() => void onArchive(n.id)}>
                      Archive
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
