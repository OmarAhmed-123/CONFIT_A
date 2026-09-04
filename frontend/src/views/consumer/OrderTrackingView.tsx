import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import { useTranslation } from 'react-i18next';
import { commerceService } from '../../services/apiServices';
import { Order, OrderTrackingTimeline } from '../../models';
import { BopisIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';

export const OrderTrackingView: React.FC = () => {
  const { orderNumber } = useParams<{ orderNumber: string }>();
  const { t } = useTranslation();

  const [order, setOrder] = useState<Order | null>(null);
  const [timeline, setTimeline] = useState<OrderTrackingTimeline | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [returnModalOpen, setReturnModalOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('Wrong Size');
  const [returnLabelUrl, setReturnLabelUrl] = useState<string | null>(null);
  const [returnError, setReturnError] = useState<string | null>(null);
  const [returnSubmitting, setReturnSubmitting] = useState(false);

  useEffect(() => {
    if (!orderNumber) {
      setIsLoading(false);
      setLoadError('No order number was provided.');
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    Promise.all([
      commerceService.getOrderDetail(orderNumber),
      commerceService.getOrderTracking(orderNumber),
    ])
      .then(([orderRes, trackRes]) => {
        setOrder(orderRes);
        setTimeline(trackRes);
        setIsLoading(false);
      })
      .catch((err) => {
        setOrder(null);
        setTimeline(null);
        setLoadError(err?.message || 'Order could not be loaded.');
        setIsLoading(false);
      });
  }, [orderNumber]);

  if (isLoading) {
    return <LoadingSpinner text="Loading order tracking..." />;
  }

  if (loadError || !order || !timeline) {
    return (
      <EmptyState
        title="Order not found"
        description={loadError || 'We could not load this order. Check the order number and try again.'}
      />
    );
  }

  const handleReturnSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setReturnError(null);
    setReturnSubmitting(true);
    try {
      const res = await commerceService.createReturn({
        order_id: order.id,
        reason: returnReason,
        details: 'Customer initiated return',
        item_ids: order.items.filter((i) => !i.is_returned).map((i) => i.id),
      });
      setReturnLabelUrl(res.return_label_url || null);
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
        eyebrow="Fulfillment Story Stack"
        title="Track every step with premium visual clarity"
        description="The order experience uses the card stack to make pickup, courier, returns, and status checkpoints feel transparent."
      />
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <span className="text-xs font-bold text-[#B8935A] uppercase tracking-wider">
            {timeline.current_status.replace(/_/g, ' ')}
          </span>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#1B1F3B] mt-1">
            Order #{order.order_number}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Placed on {new Date(order.created_at).toLocaleDateString()} · {order.payment_method} · payment {order.payment_status}
            {order.payment_mode === 'demo' ? ' (demo adapter)' : ''}
          </p>
          {timeline.tracking_number && (
            <p className="text-xs text-slate-600 mt-1">
              {timeline.carrier} · {timeline.tracking_number}
            </p>
          )}
        </div>
        <button
          onClick={() => {
            setReturnModalOpen(true);
            setReturnError(null);
            setReturnLabelUrl(null);
          }}
          className="px-4 py-2 rounded-xl border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-semibold transition-all"
        >
          {t('commerce.return_item')}
        </button>
      </div>

      {order.fulfillment_type === 'bopis' && (
        <div className="bg-[#FDF8EE] border border-[#B8935A]/40 rounded-3xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[#B8935A] flex items-center justify-center text-slate-950">
              <BopisIcon size={24} color="#0F172A" />
            </div>
            <div>
              <span className="text-xs font-bold text-[#B8935A] uppercase tracking-wider">Pickup</span>
              <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                {order.bopis_store_name || timeline.bopis_store_info?.name || 'Selected boutique'}
              </h3>
              {timeline.bopis_store_info?.address && (
                <p className="text-xs text-slate-600">{timeline.bopis_store_info.address}</p>
              )}
            </div>
          </div>
          {order.bopis_pickup_code && (
            <div className="text-center sm:text-right bg-white px-6 py-3 rounded-2xl border border-[#B8935A]/30 shadow-2xs">
              <span className="text-[10px] text-slate-400 font-bold uppercase block">Pickup code</span>
              <span className="font-mono text-2xl font-black text-[#1B1F3B] tracking-widest">
                {order.bopis_pickup_code}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">Fulfillment progress</h2>
        <div className="relative pl-6 space-y-8 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
          {timeline.timeline.map((step) => (
            <div key={step.status_key} className="relative">
              <div
                className={`absolute -left-6 top-1 w-4 h-4 rounded-full border-2 ${
                  step.is_completed
                    ? 'bg-[#1B1F3B] border-[#1B1F3B]'
                    : step.is_current
                    ? 'bg-[#B8935A] border-white ring-4 ring-[#B8935A]/30'
                    : 'bg-white border-slate-300'
                }`}
                aria-hidden
              />
              <div className="ml-2">
                <div className="flex items-baseline gap-2">
                  <h4 className={`text-sm font-bold ${step.is_current ? 'text-[#B8935A]' : 'text-slate-900'}`}>
                    {step.title}
                  </h4>
                  {step.is_current && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#B8935A]/20 text-[#B8935A] font-semibold">
                      Current
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{step.description}</p>
                {step.timestamp && (
                  <p className="text-[10px] text-slate-400 mt-0.5">{new Date(step.timestamp).toLocaleString()}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B] pb-3 border-b border-slate-100">
          Items ({order.items.length})
        </h3>
        <div className="divide-y divide-slate-100">
          {order.items.map((it) => (
            <div key={it.id} className="py-3 flex justify-between items-center text-xs">
              <div>
                <div className="font-bold text-slate-900">{it.product_title}</div>
                <div className="text-slate-500 text-[11px]">
                  {it.brand_name} · Size {it.size} · {it.color}
                  {it.is_returned ? ' · returned' : ''}
                </div>
              </div>
              <div className="text-right font-bold text-slate-900">${it.subtotal.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      {returnModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="return-title">
          <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 space-y-4">
            <h3 id="return-title" className="font-serif text-lg font-bold text-[#1B1F3B]">
              Request return
            </h3>
            {returnLabelUrl ? (
              <div className="text-center py-6 space-y-2">
                <h4 className="font-bold text-slate-900 text-sm">Return authorised</h4>
                <p className="text-xs text-slate-500">
                  A return authorisation document was issued. Carrier labels are generated only when a shipping provider is configured.
                </p>
                <a href={returnLabelUrl} className="text-xs font-bold text-[#C5A059] underline" target="_blank" rel="noreferrer">
                  Download authorisation
                </a>
                <button
                  onClick={() => setReturnModalOpen(false)}
                  className="mt-4 px-5 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold"
                >
                  Close
                </button>
              </div>
            ) : (
              <form onSubmit={handleReturnSubmit} className="space-y-4 text-xs">
                <div>
                  <label className="font-bold text-slate-700 block mb-1" htmlFor="return-reason">Reason</label>
                  <select
                    id="return-reason"
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 bg-white"
                  >
                    <option value="Wrong Size">Wrong Size</option>
                    <option value="Color Difference">Color Difference</option>
                    <option value="Style Mismatch">Style Mismatch</option>
                    <option value="Changed Mind">Changed Mind</option>
                    <option value="Quality Issue">Quality Issue</option>
                  </select>
                </div>
                {returnError && <p className="text-rose-600">{returnError}</p>}
                <div className="flex gap-2 pt-2">
                  <button type="button" onClick={() => setReturnModalOpen(false)} className="flex-1 py-2.5 rounded-xl border border-slate-200 font-semibold">
                    Cancel
                  </button>
                  <button type="submit" disabled={returnSubmitting} className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] text-white font-semibold shadow-md disabled:opacity-50">
                    {returnSubmitting ? 'Submitting...' : 'Submit return'}
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
