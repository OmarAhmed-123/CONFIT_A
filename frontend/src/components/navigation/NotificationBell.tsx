import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import type { TFunction } from 'i18next';

import { useNotifications } from '../../hooks/useNotifications';
import { ORDER_STATUS_KEYS } from '../../i18n/orderState';
import type { NotificationItem } from '../../services/notificationService';

/** Localize a notification line. For order-status events we render a fully
 *  localized sentence from the structured data (order number + the shared
 *  order-state label map), so an Arabic shopper never sees an English machine
 *  token. Everything else falls back to the stored title. */
function lineFor(t: TFunction, n: NotificationItem): string {
  if (n.type === 'order_status' && n.data && typeof n.data.status === 'string') {
    const statusKey = ORDER_STATUS_KEYS[n.data.status];
    const status = statusKey ? t(statusKey) : n.data.status;
    const order = typeof n.data.order_number === 'string' ? n.data.order_number : '';
    // Composed from a localized prefix + structured data (no interpolated
    // sentence), so the order number/status render correctly in EN and AR.
    return `${t('notifications.order_prefix')} ${order}: ${status}`;
  }
  return n.title;
}

const NotificationRow: React.FC<{
  n: NotificationItem;
  t: TFunction;
  onRead: () => void;
  onClose: () => void;
}> = ({ n, t, onRead, onClose }) => {
  const text = lineFor(t, n);
  const showBody = n.body && n.type !== 'order_status'; // order lines are self-contained
  const handle = () => {
    if (!n.read) onRead();
    onClose();
  };
  const inner = (
    <div className={`flex gap-2 items-start px-2 py-2 rounded-lg ${n.read ? '' : 'bg-brand-wash'}`}>
      {!n.read && <span className="mt-1.5 w-2 h-2 rounded-full bg-rose-600 shrink-0" aria-hidden="true" />}
      <div className="min-w-0">
        <p className="text-xs font-semibold text-brand-charcoal">{text}</p>
        {showBody ? <p className="text-[11px] text-brand-muted line-clamp-2">{n.body}</p> : null}
      </div>
    </div>
  );
  return n.link ? (
    <Link to={n.link} onClick={handle} className="block" role="menuitem">
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={handle} className="block w-full text-start" role="menuitem">
      {inner}
    </button>
  );
};

/**
 * Authenticated notification bell: a badge that polls the unread count and a
 * dropdown that lists recent notifications with mark-read / mark-all-read.
 * Render it only for signed-in shoppers (the API is owner-scoped and returns
 * 401 otherwise).
 */
export const NotificationBell: React.FC = () => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { unread, items, loading, loadList, markRead, markAllRead } = useNotifications(true);

  useEffect(() => {
    if (open) void loadList();
  }, [open, loadList]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const badge = unread > 9 ? '9+' : String(unread);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t('notifications.aria_label', { count: unread })}
        className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-brand-charcoal hover:bg-slate-100 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
      >
        <Bell size={20} aria-hidden="true" />
        {unread > 0 ? (
          <span className="absolute top-1 end-1 min-w-4 h-4 px-1 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center" aria-hidden="true">
            {badge}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={t('notifications.title')}
          className="absolute top-full end-0 mt-2 w-80 max-w-[90vw] bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150"
        >
          <div className="flex items-center justify-between px-1 pb-2 border-b border-slate-100">
            <span className="text-sm font-bold text-brand-charcoal">{t('notifications.title')}</span>
            {unread > 0 ? (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="text-xs font-semibold text-brand-field hover:underline"
              >
                {t('notifications.mark_all_read')}
              </button>
            ) : null}
          </div>
          <div className="max-h-96 overflow-y-auto py-1">
            {loading ? (
              <p className="text-xs text-brand-muted px-2 py-6 text-center">{t('notifications.loading')}</p>
            ) : items.length === 0 ? (
              <p className="text-xs text-brand-muted px-2 py-6 text-center">{t('notifications.empty')}</p>
            ) : (
              items.map((n) => (
                <NotificationRow
                  key={n.id}
                  n={n}
                  t={t}
                  onRead={() => void markRead(n.id)}
                  onClose={() => setOpen(false)}
                />
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};
