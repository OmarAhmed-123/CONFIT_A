import { request } from './apiClient';

/** One in-app notification as returned by the backend (per-recipient). */
export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  link: string | null;
  data: Record<string, unknown> | null;
  read: boolean;
  created_at: string;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
  next_before_id: number | null;
}

/**
 * Thin client over the authenticated /notifications API. Auth travels on the
 * httpOnly session cookie (apiClient attaches no Bearer), so these calls only
 * succeed for a signed-in shopper — which is exactly when the bell is shown.
 */
export const notificationService = {
  unreadCount: () => request<{ unread_count: number }>('/notifications/unread-count'),

  list: (opts?: { unreadOnly?: boolean; limit?: number; beforeId?: number }) => {
    const p = new URLSearchParams();
    if (opts?.unreadOnly) p.set('unread_only', 'true');
    if (opts?.limit) p.set('limit', String(opts.limit));
    if (opts?.beforeId) p.set('before_id', String(opts.beforeId));
    const qs = p.toString();
    return request<NotificationList>(`/notifications${qs ? `?${qs}` : ''}`);
  },

  markRead: (id: number) =>
    request<NotificationItem>(`/notifications/${id}/read`, { method: 'POST' }),

  markAllRead: () =>
    request<{ updated: number }>('/notifications/read-all', { method: 'POST' }),
};
