import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import { useTranslation } from 'react-i18next';
import { commerceService } from '../../services/apiServices';
import { Order, OrderTrackingTimeline } from '../../models';
import {
  localizeOrderStatus,
  localizePaymentMethod,
  localizePaymentStatus,
} from '../../i18n/orderState';
import { BopisIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { useAuthStore } from '../../stores/authStore';
import { formatDate, formatDateTime } from '../../i18n/format';
import type { Order as OrderSummary } from '../../models';

export const OrderTrackingView: React.FC = () => {
  const { orderNumber } = useParams<{ orderNumber: string }>();
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const { isAuthenticated } = useAuthStore();

  const [order, setOrder] = useState<Order | null>(null);
  const [timeline, setTimeline] = useState<OrderTrackingTimeline | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [orderList, setOrderList] = useState<OrderSummary[] | null>(null);
  const [listError, setListError] = useState(false);
  const [listTick, setListTick] = useState(0);
  const lang = i18n.resolvedLanguage ?? 'en';
  const [returnModalOpen, setReturnModalOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('Wrong Size');
  const [returnLabelUrl, setReturnLabelUrl] = useState<string | null>(null);
  const [returnError, setReturnError] = useState<string | null>(null);
  const [returnSubmitting, setReturnSubmitting] = useState(false);
  // CUS-09 second factor for guest orders + Cycle7 anti-enumeration
  const [guestEmailInput, setGuestEmailInput] = useState('');
  const [guestEmailForLookup, setGuestEmailForLookup] = useState<string | undefined>(undefined);
  const [needsSecondFactor, setNeedsSecondFactor] = useState(false);

  const loadOrder = useCallback(async (orderNum: string, guestEmail?: string) => {
    setIsLoading(true);
    setLoadError(null);
    setNeedsSecondFactor(false);
    try {
      let [orderRes, trackRes] = await Promise.all([
        commerceService.getOrderDetail(orderNum, guestEmail),
        commerceService.getOrderTracking(orderNum, guestEmail),
      ]);
      const params = new URLSearchParams(location.search);
      const hasPaymentReturn = params.has('payment_result') || params.has('payment_return');
      if (
        hasPaymentReturn &&
        orderRes.payment_status === 'pending' &&
        typeof commerceService.reconcileOrderPayment === 'function'
      ) {
        try {
          orderRes = await commerceService.reconcileOrderPayment(orderNum, guestEmail);
          trackRes = await commerceService.getOrderTracking(orderNum, guestEmail);
        } catch {
          // Non-fatal: webhook or subsequent poll reconciles independently
        }
      }
      setOrder(orderRes);
      setTimeline(trackRes);
      setLoadError(null);
      setCanRetry(false);
      setIsLoading(false);
    } catch (err: any) {
      const msg = typeof err?.message === 'string' ? err.message : '';
      const status = err?.status || 0;
      const code = (err?.code || '').toString().toLowerCase();
      const lowerMsg = msg.toLowerCase();

      // Cycle7 anti-enumeration: anonymous failures are normalized to 404 generic.
      // We must not reveal whether order exists. For anonymous users, any failure
      // (404, 401 with second factor, etc.) should prompt neutral verification
      // without claiming existence. For authenticated 403, keep access-denied.
      const isAuthError = status === 401 || status === 403 || code.includes('auth') || code.includes('forbidden');
      const isNotFound = status === 404 || code.includes('not_found') || code.includes('resource_not_found') || lowerMsg.includes('not found') || lowerMsg.includes('access denied');
      // A 5xx or a network failure (status 0) is OUR problem, not an unverified
      // guest. Showing the email-verification form for it was misleading.
      // Status decides first: a 5xx whose message happens to say "not found" is still a server fault.
      const isServerFault = status >= 500 || (status === 0 && !isNotFound && !isAuthError);

      if (isServerFault) {
        setNeedsSecondFactor(false);
        setLoadError(t('order.load_failed'));
        setCanRetry(true);
      } else if (!isAuthenticated) {
        // Anonymous: offer neutral verification prompt for any failure, unless
        // it's clearly a business validation that should not be retried via email.
        // After first attempt without email, or with wrong email, show verification.
        if (isNotFound || isAuthError || lowerMsg.includes('second factor') || lowerMsg.includes('guest order access') || lowerMsg.includes('email') || !guestEmail) {
          // Neutral copy only: backend text is English and must not reach AR users.
          setNeedsSecondFactor(true);
          setLoadError(t('order.verify_failed'));
        } else {
          setLoadError(t('order.load_failed'));
          setCanRetry(true);
        }
      } else {
        // Authenticated: if 403 cross-customer, do not prompt for email
        if (status === 403) {
          setNeedsSecondFactor(false);
          setLoadError(t('order.access_denied'));
        } else if (isNotFound) {
          // A signed-in customer has no guest flow to fall back to.
          setNeedsSecondFactor(false);
          setLoadError(t('order.not_found_desc'));
        } else if (lowerMsg.includes('second factor') || lowerMsg.includes('guest order access')) {
          setNeedsSecondFactor(true);
          setLoadError(t('order.verify_failed'));
        } else {
          setLoadError(t('order.load_failed'));
          setCanRetry(true);
        }
      }
      setOrder(null);
      setTimeline(null);
      setIsLoading(false);
      if (!isServerFault) setCanRetry(false);
    }
  }, [isAuthenticated, location.search, t]);

  useEffect(() => {
    if (orderNumber) {
      void loadOrder(orderNumber, guestEmailForLookup);
      return;
    }
    setLoadError(null);
    if (!isAuthenticated) {
      setIsLoading(false);
      setLoadError(t('order.no_number'));
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setListError(false);
    commerceService
      .getOrders()
      .then((rows) => {
        if (cancelled) return;
        setOrderList(rows);
        setIsLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setListError(true);
        setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orderNumber, guestEmailForLookup, loadOrder, isAuthenticated, t, listTick]);

  const handleGuestEmailSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!guestEmailInput.trim()) return;
    setGuestEmailForLookup(guestEmailInput.trim());
  };

  if (isLoading) {
    return <LoadingSpinner text={t('order.loading')} />;
  }

  if (needsSecondFactor) {
    return (
      <div className="max-w-md mx-auto mt-10 p-6 bg-white rounded-3xl border border-brand-hairline shadow-sm space-y-4">
        <h2 className="font-serif text-lg font-bold text-brand-charcoal">{t('order.verify_prompt_title')}</h2>
        <p className="text-xs text-brand-muted">{t('order.verify_prompt_desc')}</p>
        <p className="text-[11px] text-brand-muted">{t('order.verify_neutral')}</p>
        <form onSubmit={handleGuestEmailSubmit} className="space-y-3">
          <label className="block text-xs font-bold text-brand-charcoal">
            {t('order.guest_email_label')}
            <input
              type="email"
              value={guestEmailInput}
              onChange={(e) => setGuestEmailInput(e.target.value)}
              placeholder="name@example.com"
              required
              className="mt-1 w-full p-2.5 rounded-xl border border-brand-hairline text-xs"
            />
          </label>
          <button data-motion="recovery" type="submit" className="w-full py-2.5 rounded-xl bg-brand-charcoal text-white text-xs font-semibold">
            {t('order.guest_lookup_retry')}
          </button>
        </form>
        {loadError && <p className="text-[11px] text-rose-600">{loadError}</p>}
      </div>
    );
  }

  if (!orderNumber && isAuthenticated) {
    return (
      <section className="space-y-6 pb-20 max-w-4xl mx-auto">
        <header>
          <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('order.list_title')}</h1>
          <p className="text-xs text-brand-muted mt-1">{t('order.list_subtitle')}</p>
        </header>
        {listError ? (
          <EmptyState
            title={t('order.list_error_title')}
            description={t('order.load_failed')}
            actionText={t('order.retry')}
            onAction={() => {
              setListError(false);
              setListTick((n) => n + 1);
            }}
          />
        ) : orderList && orderList.length === 0 ? (
          <EmptyState title={t('order.list_empty_title')} description={t('order.list_empty')} />
        ) : (
          <ul className="space-y-3">
            {(orderList ?? []).map((o) => (
              <li key={o.order_number}>
                <Link
                  to={`/orders/${encodeURIComponent(o.order_number)}`}
                  className="block rounded-2xl border border-brand-hairline bg-white p-4 hover:border-brand-charcoal focus-visible:outline-brand-charcoal transition-colors"
                >
                  <div className="flex flex-wrap justify-between gap-2">
                    <span className="text-sm font-bold text-brand-charcoal">
                      {t('order.number_label')} {o.order_number}
                    </span>
                    <span className="text-xs text-brand-muted">{formatDate(o.created_at, lang)}</span>
                  </div>
                  <div className="mt-1 text-xs text-brand-muted">
                    {localizeOrderStatus(o.status, t)}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  if (loadError || !order || !timeline) {
    return (
      <EmptyState
        title={canRetry ? t('order.load_failed_title') : t('order.not_found')}
        description={loadError || t('order.load_failed')}
        actionText={canRetry ? t('order.retry') : undefined}
        onAction={canRetry && orderNumber ? () => void loadOrder(orderNumber, guestEmailForLookup) : undefined}
      />
    );
  }

  const isGuestOrder = !order.user_id && !!order.guest_email;

  const handleReturnSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setReturnError(null);
    setReturnSubmitting(true);
    try {
      if (isGuestOrder) {
        // CUS-10 guest returns with second factor
        const res = await commerceService.createGuestReturn({
          order_number: order.order_number,
          guest_email: guestEmailForLookup || order.guest_email || guestEmailInput || undefined,
          reason: returnReason,
          details: 'Customer initiated return (guest)',
          item_ids: order.items.filter((i) => !i.is_returned).map((i) => i.id),
        });
        setReturnLabelUrl(res.return_label_url || null);
      } else {
        const res = await commerceService.createReturn({
          order_id: order.id,
          reason: returnReason,
          details: 'Customer initiated return',
          item_ids: order.items.filter((i) => !i.is_returned).map((i) => i.id),
        });
        setReturnLabelUrl(res.return_label_url || null);
      }
    } catch (err: any) {
      setReturnError(err?.message || 'Return could not be created.');
    } finally {
      setReturnSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 pb-20 max-w-4xl mx-auto">
      <CardStackShowcase
        tone="commerce"
        compact
        eyebrow={t('order.story_eyebrow')}
        title={t('order.track_subtitle')}
        description={t('order.story_description')}
      />
      <div className="bg-white rounded-3xl border border-brand-hairline p-6 sm:p-8 shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <span className="text-xs font-bold text-brand-muted uppercase tracking-wider">
            {localizeOrderStatus(timeline.current_status, t)}
          </span>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-brand-charcoal mt-1">
            {t('order.number_label')}{order.order_number}
          </h1>
          <p className="text-xs text-brand-muted mt-1">
            {formatDate(order.created_at, lang)} ·{' '}
            {localizePaymentMethod(order.payment_method, t)} ·{' '}
            {localizePaymentStatus(order.payment_status, t)}
            {order.payment_mode === 'demo' ? ` (${t('order.demo_adapter_note')})` : ''}
          </p>
          {timeline.tracking_number && (
            <p className="text-xs text-brand-muted mt-1">
              {timeline.carrier} · {timeline.tracking_number}
            </p>
          )}
          {isGuestOrder && (
            <p className="text-[10px] text-brand-muted mt-1">{t('order.guest_return_note')}</p>
          )}
        </div>
        <button data-motion="progressive"
          onClick={() => {
            setReturnModalOpen(true);
            setReturnError(null);
            setReturnLabelUrl(null);
          }}
          className="px-4 py-2 rounded-xl border border-brand-field hover:border-brand-charcoal text-brand-charcoal text-xs font-semibold transition-all min-h-11 focus-visible:outline-brand-charcoal"
        >
          {t('commerce.return_item')}
        </button>
      </div>

      {order.fulfillment_type === 'bopis' && (
        <div className="bg-brand-wash border border-brand-field rounded-3xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-charcoal flex items-center justify-center text-white">
              <BopisIcon size={24} color="#FFFFFF" />
            </div>
            <div>
              <span className="text-xs font-bold text-brand-muted uppercase tracking-wider">{t('checkout.pickup')}</span>
              <h3 className="font-serif text-lg font-bold text-brand-charcoal">
                {order.bopis_store_name || timeline.bopis_store_info?.name || t('order.selected_boutique')}
              </h3>
              {timeline.bopis_store_info?.address && (
                <p className="text-xs text-brand-muted">{timeline.bopis_store_info.address}</p>
              )}
            </div>
          </div>
          {order.bopis_pickup_code && (
            <div className="text-center sm:text-right bg-white px-6 py-3 rounded-2xl border border-brand-field shadow-2xs">
              <span className="text-[10px] text-brand-muted font-bold uppercase block">{t('order.pickup_code')}</span>
              <span className="font-mono text-2xl font-black text-brand-charcoal tracking-widest">
                {order.bopis_pickup_code}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-3xl border border-brand-hairline p-6 sm:p-8 shadow-sm space-y-6">
        <h2 className="font-serif text-xl font-bold text-brand-charcoal">{t('order.fulfillment_progress')}</h2>
        <div className="relative pl-6 space-y-8 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-brand-hairline">
          {timeline.timeline.map((step) => (
            <div key={step.status_key} className="relative">
              <div
                className={`absolute -left-6 top-1 w-4 h-4 rounded-full border-2 ${
                  step.is_completed
                    ? 'bg-brand-charcoal border-brand-charcoal'
                    : step.is_current
                    ? 'bg-brand-charcoal border-white ring-4 ring-brand-charcoal/20'
                    : 'bg-white border-brand-field'
                }`}
                aria-hidden
              />
              <div className="ml-2">
                <div className="flex items-baseline gap-2">
                  <h4 className={`text-sm font-bold text-brand-charcoal`}>
                    {step.title}
                  </h4>
                  {step.is_current && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand-wash text-brand-charcoal font-semibold">
                      {t('order.current_step')}
                    </span>
                  )}
                </div>
                <p className="text-xs text-brand-muted mt-0.5">{step.description}</p>
                {step.timestamp && (
                  <p className="text-[10px] text-brand-muted mt-0.5">{formatDateTime(step.timestamp, lang)}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-3xl border border-brand-hairline p-6 shadow-sm space-y-4">
        <h3 className="font-serif text-lg font-bold text-brand-charcoal pb-3 border-b border-brand-hairline">
          {t('order.items_label')} ({order.items.length})
        </h3>
        <div className="divide-y divide-brand-hairline">
          {order.items.map((it) => (
            <div key={it.id} className="py-3 flex justify-between items-center text-xs">
              <div>
                <div className="font-bold text-brand-charcoal">{it.product_title}</div>
                <div className="text-brand-muted text-[11px]">
                  {it.brand_name} · {t('checkout.size')} {it.size} · {it.color}
                  {it.is_returned ? t('order.returned_suffix') : ''}
                </div>
              </div>
              <div className="text-right font-bold text-brand-charcoal">${it.subtotal.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      {returnModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-brand-charcoal/70 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="return-title">
          <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 space-y-4">
            <h3 id="return-title" className="font-serif text-lg font-bold text-brand-charcoal">
              {t('order.request_return')}
            </h3>
            {returnLabelUrl ? (
              <div className="text-center py-6 space-y-2">
                <h4 className="font-bold text-brand-charcoal text-sm">{t('order.return_authorised')}</h4>
                <p className="text-xs text-brand-muted">
                  {t('order.return_authorised_detail')}
                </p>
                <a href={returnLabelUrl} className="text-xs font-bold text-brand-charcoal underline" target="_blank" rel="noreferrer">
                  {t('order.download_authorisation')}
                </a>
                <button data-motion="neutral"
                  onClick={() => setReturnModalOpen(false)}
                  className="mt-4 px-5 py-2 rounded-xl bg-brand-charcoal text-white text-xs font-semibold min-h-11"
                >
                  {t('common.close')}
                </button>
              </div>
            ) : (
              <form onSubmit={handleReturnSubmit} className="space-y-4 text-xs">
                <div>
                  <label className="font-bold text-brand-charcoal block mb-1" htmlFor="return-reason">{t('order.return_reason')}</label>
                  <select
                    id="return-reason"
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    className="w-full p-2.5 rounded-xl border border-brand-hairline bg-white min-h-11"
                  >
                    <option value="Wrong Size">{t('order.reason_wrong_size')}</option>
                    <option value="Color Difference">{t('order.reason_color')}</option>
                    <option value="Style Mismatch">{t('order.reason_style')}</option>
                    <option value="Changed Mind">{t('order.reason_changed_mind')}</option>
                    <option value="Quality Issue">{t('order.reason_quality')}</option>
                  </select>
                </div>
                {isGuestOrder && (
                  <div>
                    <label className="font-bold text-brand-charcoal block mb-1">{t('order.guest_email_label')}</label>
                    <input
                      type="email"
                      value={guestEmailForLookup || guestEmailInput}
                      onChange={(e) => setGuestEmailInput(e.target.value)}
                      placeholder="name@example.com"
                      className="w-full p-2.5 rounded-xl border border-brand-hairline min-h-11"
                    />
                    <p className="text-[10px] text-brand-muted mt-1">{t('order.guest_return_note')}</p>
                  </div>
                )}
                {returnError && <p className="text-rose-600" role="alert">{returnError}</p>}
                <div className="flex gap-2 pt-2">
                  <button data-motion="neutral" type="button" onClick={() => setReturnModalOpen(false)} className="flex-1 py-2.5 rounded-xl border border-brand-hairline font-semibold min-h-11">
                    {t('common.cancel')}
                  </button>
                  <button data-motion="progressive" data-motion-tone="icon" type="submit" disabled={returnSubmitting} className="flex-1 py-2.5 rounded-xl bg-brand-charcoal text-white font-semibold shadow-md disabled:opacity-50 min-h-11">
                    {returnSubmitting ? 'Submitting...' : t('order.submit_return')}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
