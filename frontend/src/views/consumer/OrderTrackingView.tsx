import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { commerceService } from '../../services/apiServices';
import { Order, OrderTrackingTimeline } from '../../models';
import {
  OrdersIcon,
  BopisIcon,
  SparkleIcon,
  BagIcon,
} from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const OrderTrackingView: React.FC = () => {
  const { orderNumber } = useParams<{ orderNumber: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [order, setOrder] = useState<Order | null>(null);
  const [timeline, setTimeline] = useState<OrderTrackingTimeline | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [returnModalOpen, setReturnModalOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('Wrong Size');
  const [returnSubmitted, setReturnSubmitted] = useState(false);

  useEffect(() => {
    const targetOrder = orderNumber || 'CONF-8821094A';
    setIsLoading(true);

    Promise.allSettled([
      commerceService.getOrderDetail(targetOrder),
      commerceService.getOrderTracking(targetOrder),
    ]).then(([orderRes, trackRes]) => {
      if (orderRes.status === 'fulfilled') setOrder(orderRes.value);
      if (trackRes.status === 'fulfilled') setTimeline(trackRes.value);
      setIsLoading(false);
    });
  }, [orderNumber]);

  if (isLoading || !order || !timeline) {
    return <LoadingSpinner text="Connecting to CONFIT Logistics & Tracking..." />;
  }

  const handleReturnSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    commerceService
      .createReturn({
        order_id: order.id,
        reason: returnReason,
        details: 'Customer initiated return flow',
        item_ids: order.items.map((i) => i.id),
      })
      .then(() => {
        setReturnSubmitted(true);
      });
  };

  return (
    <div className="space-y-8 pb-20 max-w-4xl mx-auto">
      {/* Header */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <span className="text-xs font-bold text-[#B8935A] uppercase tracking-wider">
            Order Dispatched & Tracking Active
          </span>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#1B1F3B] mt-1">
            Order #{order.order_number}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Placed on {new Date(order.created_at).toLocaleDateString()} · Paid via {order.payment_method.toUpperCase()}
          </p>
        </div>

        <button
          onClick={() => setReturnModalOpen(true)}
          className="px-4 py-2 rounded-xl border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-semibold transition-all"
        >
          {t('commerce.return_item')}
        </button>
      </div>

      {/* BOPIS Pickup Code Box if BOPIS */}
      {order.fulfillment_type === 'bopis' && (
        <div className="bg-[#FDF8EE] border border-[#B8935A]/40 rounded-3xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[#B8935A] flex items-center justify-center text-slate-950">
              <BopisIcon size={24} color="#0F172A" />
            </div>
            <div>
              <span className="text-xs font-bold text-[#B8935A] uppercase tracking-wider">
                Digital Pickup Pass
              </span>
              <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                {order.bopis_store_name || 'Massimo Dutti — The Dubai Mall'}
              </h3>
              <p className="text-xs text-slate-600">
                Present this code to the boutique associate for instant pickup.
              </p>
            </div>
          </div>

          <div className="text-center sm:text-right bg-white px-6 py-3 rounded-2xl border border-[#B8935A]/30 shadow-2xs">
            <span className="text-[10px] text-slate-400 font-bold uppercase block">Pickup Code</span>
            <span className="font-mono text-2xl font-black text-[#1B1F3B] tracking-widest">
              {order.bopis_pickup_code || 'PICKUP-8821'}
            </span>
          </div>
        </div>
      )}

      {/* Real-Time Tracking Timeline */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">
          Live Fulfillment Progress
        </h2>

        <div className="relative pl-6 space-y-8 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
          {timeline.timeline.map((step, idx) => (
            <div key={step.status_key} className="relative group">
              {/* Status Circle Indicator */}
              <div
                className={`absolute -left-6 top-1 w-4 h-4 rounded-full border-2 transition-all ${
                  step.is_completed
                    ? 'bg-[#1B1F3B] border-[#1B1F3B]'
                    : step.is_current
                    ? 'bg-[#B8935A] border-white ring-4 ring-[#B8935A]/30 animate-pulse'
                    : 'bg-white border-slate-300'
                }`}
              ></div>

              <div className="ml-2">
                <div className="flex items-baseline gap-2">
                  <h4
                    className={`text-sm font-bold ${
                      step.is_current ? 'text-[#B8935A]' : 'text-slate-900'
                    }`}
                  >
                    {step.title}
                  </h4>
                  {step.is_current && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#B8935A]/20 text-[#B8935A] font-semibold">
                      Current Stage
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Order Item Summary */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B] pb-3 border-b border-slate-100">
          Items in this Order ({order.items.length})
        </h3>
        <div className="divide-y divide-slate-100">
          {order.items.map((it) => (
            <div key={it.id} className="py-3 flex justify-between items-center text-xs">
              <div>
                <div className="font-bold text-slate-900">{it.product_title}</div>
                <div className="text-slate-500 text-[11px]">{it.brand_name} · Size {it.size} · {it.color}</div>
              </div>
              <div className="text-right font-bold text-slate-900">
                ${it.subtotal.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Return Request Modal */}
      {returnModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 space-y-4">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Request Return or Exchange
            </h3>

            {returnSubmitted ? (
              <div className="text-center py-6 space-y-2">
                <div className="text-2xl">✅</div>
                <h4 className="font-bold text-slate-900 text-sm">Return Label Generated!</h4>
                <p className="text-xs text-slate-500">
                  Prepaid return label has been emailed. You can drop off the package at any partner courier or boutique.
                </p>
                <button
                  onClick={() => {
                    setReturnModalOpen(false);
                    setReturnSubmitted(false);
                  }}
                  className="mt-4 px-5 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold"
                >
                  Close
                </button>
              </div>
            ) : (
              <form onSubmit={handleReturnSubmit} className="space-y-4 text-xs">
                <div>
                  <label className="font-bold text-slate-700 block mb-1">Reason for Return</label>
                  <select
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 bg-white"
                  >
                    <option value="Wrong Size">Wrong Size</option>
                    <option value="Color Difference">Color Difference</option>
                    <option value="Style Mismatch">Style Mismatch</option>
                    <option value="Changed Mind">Changed Mind</option>
                  </select>
                </div>

                <p className="text-[11px] text-slate-500">
                  🔒 CONFIT Try-On Guarantee: Items styled or tried on via VTON receive complimentary zero-fee returns within 30 days.
                </p>

                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setReturnModalOpen(false)}
                    className="flex-1 py-2.5 rounded-xl border border-slate-200 font-semibold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] text-white font-semibold shadow-md"
                  >
                    Submit Return
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
