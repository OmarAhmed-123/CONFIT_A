import { useCallback, useEffect, useRef, useState } from 'react';

import { notificationService, type NotificationItem } from '../services/notificationService';

/** Poll cadence for the unread badge. CONFIT is serverless (no sockets), so
 *  the bell polls; 30s keeps it near-real-time without hammering the API. */
const POLL_MS = 30_000;

export interface UseNotifications {
  unread: number;
  items: NotificationItem[];
  loading: boolean;
  loadList: () => Promise<void>;
  markRead: (id: number) => Promise<void>;
  markAllRead: () => Promise<void>;
}

/**
 * Notification state for the bell. Polls the unread count while `enabled`
 * (i.e. the shopper is signed in) and loads the list on demand when the panel
 * opens. Every network error is swallowed and the last known state is kept —
 * a transient blip must never break the navbar.
 */
export function useNotifications(enabled: boolean): UseNotifications {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | null>(null);

  const refreshCount = useCallback(async () => {
    if (!enabled) return;
    try {
      const { unread_count } = await notificationService.unreadCount();
      setUnread(unread_count);
    } catch {
      /* transient — keep last known count */
    }
  }, [enabled]);

  const loadList = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      const res = await notificationService.list({ limit: 15 });
      setItems(res.items);
      setUnread(res.unread_count);
    } catch {
      /* ignore — panel shows last known items */
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  const markRead = useCallback(async (id: number) => {
    try {
      await notificationService.markRead(id);
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, read: true } : x)));
      setUnread((c) => Math.max(0, c - 1));
    } catch {
      /* ignore */
    }
  }, []);

  const markAllRead = useCallback(async () => {
    try {
      await notificationService.markAllRead();
      setItems((xs) => xs.map((x) => ({ ...x, read: true })));
      setUnread(0);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setUnread(0);
      setItems([]);
      return;
    }
    void refreshCount();
    timer.current = window.setInterval(() => void refreshCount(), POLL_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [enabled, refreshCount]);

  return { unread, items, loading, loadList, markRead, markAllRead };
}
