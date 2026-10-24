import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import type { TFunction } from 'i18next';

import { useNotifications } from '../../hooks/useNotifications';
import { ORDER_STATUS_KEYS } from '../../i18n/orderState';
import type { NotificationItem } from '../../services/notificationService';

/** Catalogue-import job states → i18n keys (literal map, like ORDER_STATUS_KEYS,
 *  so the keys are statically referenced for the i18n gate). */
const IMPORT_STATUS_KEYS: Record<string, string> = {
  completed: 'notifications.import_status.completed',
  partially_completed: 'notifications.import_status.partially_completed',
  failed: 'notifications.import_status.failed',
};

/** Localize a notification line from its structured data, so neither an English
 *  nor an Arabic reader ever sees a machine token. order_status, new_order and
 *  catalog_import are composed from a localized prefix + data (no interpolated
 *  sentence); everything else falls back to the stored title. */
function lineFor(t: TFunction, n: NotificationItem): string {
  const d = (n.data || {}) as Record<string, unknown>;
  if (n.type === 'order_status' && typeof d.status === 'string') {
    const statusKey = ORDER_STATUS_KEYS[d.status];
    const status = statusKey ? t(statusKey) : d.status;
    const order = typeof d.order_number === 'string' ? d.order_number : '';
    return `${t('notifications.order_prefix')} ${order}: ${status}`;
  }
  if (n.type === 'new_order') {
    const order = typeof d.order_number === 'string' ? d.order_number : '';
    return `${t('notifications.new_order_prefix')} ${order}`.trim();
  }
  if (n.type === 'catalog_import') {
    const st = typeof d.status === 'string' ? d.status : '';
    const key = IMPORT_STATUS_KEYS[st];
    const statusLabel = key ? t(key) : st;
    return `${t('notifications.import_prefix')} — ${statusLabel}`;
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
  // Secondary line only for generic types; order_status, new_order and
  // catalog_import lines are self-contained in the localized title (and never
  // use a unicode/emoji status channel).
  const body =
    n.type !== 'order_status' && n.type !== 'new_order' && n.type !== 'catalog_import' && n.body
      ? n.body
      : null;
  const handle = () => {
    if (!n.read) onRead();
    onClose();
  };
  const inner = (
    <div className={`flex gap-2 items-start px-2 py-2 rounded-lg ${n.read ? '' : 'bg-brand-wash'}`}>
      {!n.read && <span className="mt-1.5 w-2 h-2 rounded-full bg-rose-600 shrink-0" aria-hidden="true" />}
      <div className="min-w-0">
        <p className="text-xs font-semibold text-brand-charcoal">{text}</p>
        {body ? <p className="text-[11px] text-brand-muted line-clamp-2">{body}</p> : null}
      </div>
    </div>
  );
  return n.link ? (
    <Link to={n.link} onClick={handle} className="block" role="menuitem">
      {inner}
    </Link>
  ) : (
    <button data-motion="neutral" type="button" onClick={handle} className="block w-full text-start" role="menuitem">
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
export const NotificationBell: React.FC<{ tone?: 'light' | 'dark' }> = ({ tone = 'light' }) => {
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
        data-motion="neutral"
        data-motion-tone="icon"
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t('notifications.aria_label', { count: unread })}
        className={`relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 ${
          tone === 'dark'
            ? 'text-neutral-200 hover:bg-white/10 focus-visible:ring-white/60'
            : 'text-brand-charcoal hover:bg-slate-100 focus-visible:ring-brand-charcoal'
        }`}
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
                data-motion="neutral"
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
