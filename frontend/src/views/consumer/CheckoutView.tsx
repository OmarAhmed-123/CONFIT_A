import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { commerceService } from '../../services/apiServices';
import {
  BopisIcon,
  OrdersIcon,
  SparkleIcon,
  UserIcon,
} from '../../components/icons/ConfitIcons';
import { BNPLBadge } from '../../components/common/CommonComponents';

export const CheckoutView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { cart, fetchCart } = useCartStore();
  const { user, isAuthenticated } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();

  const [fulfillmentType, setFulfillmentType] = useState<'delivery' | 'bopis'>('delivery');
  const [selectedBopisStoreId, setSelectedBopisStoreId] = useState<number>(1);
  const [paymentMethod, setPaymentMethod] = useState<'card' | 'bnpl_tabby' | 'bnpl_tamara' | 'apple_pay' | 'cod'>('bnpl_tabby');

  // Shipping Form State
  const [recipientName, setRecipientName] = useState(user?.full_name || '');
  const [phone, setPhone] = useState(user?.phone || '+971501234567');
  const [addressLine, setAddressLine] = useState('Villa 14, Al Wasl Road');
  const [city, setCity] = useState('Dubai');
  const [country, setCountry] = useState('UAE');
  const [promoCode, setPromoCode] = useState('CONFIT10');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      setRecipientName(user.full_name);
      if (user.phone) setPhone(user.phone);
    }
  }, [user]);

  const total = cart?.total || 0;
  const subtotal = cart?.subtotal || 0;

  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault();

    // Enforce the "Browse-First, Auth-at-Purchase" rule (Section 3.1 & 7.2)
    if (!isAuthenticated || !user) {
      showToast('Please sign in or create an account to secure your order and activate tracking.', 'info');
      openAuthModal('login');
      return;
    }

    setIsSubmitting(true);
    try {
      const order = await commerceService.checkout({
        payment_method: paymentMethod,
        fulfillment_type: fulfillmentType,
        bopis_store_id: fulfillmentType === 'bopis' ? selectedBopisStoreId : undefined,
        recipient_name: recipientName || user.full_name,
        phone,
        address_line: addressLine,
        city,
        country,
        promo_code: promoCode || undefined,
        try_on_assisted: true,
        stylist_assisted: false,
      });

      setIsSubmitting(false);
      showToast('Order confirmed! Tracking and receipt initiated.', 'success');
      navigate(`/orders/${order.order_number}`);
    } catch (err: any) {
      setIsSubmitting(false);
      showToast('Checkout failed: ' + err.message, 'error');
    }
  };

  return (
    <div className="space-y-8 pb-24 max-w-5xl mx-auto">
      {/* Header */}
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
          {t('commerce.checkout')}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
          Multi-Brand Unified Checkout with Guaranteed Fit & Flexible BNPL Payments
        </p>
      </div>

      {/* Late-Auth Identity Gate Banner for Guests (Section 2 & 3.1) */}
      {!isAuthenticated && (
        <div className="bg-[#FAF9F6] border border-[#C5A059]/40 rounded-3xl p-5 sm:p-6 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-[#0C0E1E] text-[#C5A059] flex items-center justify-center font-bold shrink-0 shadow-2xs">
              <UserIcon size={20} color="#C5A059" />
            </div>
            <div>
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                Guest Checkout — Secure Identity Step
              </h3>
              <p className="text-xs text-slate-500 font-light mt-0.5">
                Sign in or create an account in 1 click to save your User Style Profile, track orders real-time, and access 30-day zero-fee returns.
              </p>
            </div>
          </div>

          <div className="flex gap-2.5 shrink-0 w-full sm:w-auto">
            <button
              type="button"
              onClick={() => openAuthModal('login')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-2xs transition-all"
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => openAuthModal('register')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 text-xs font-semibold shadow-2xs transition-all"
            >
              Create Account
            </button>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmitOrder} className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Fulfillment, Address & Payment (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* 1. Fulfillment Mode: Delivery vs BOPIS */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
              1. Choose Fulfillment Method:
            </h3>

            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setFulfillmentType('delivery')}
                className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between ${
                  fulfillmentType === 'delivery'
                    ? 'border-[#1B1F3B] bg-[#FAF9F6] ring-1 ring-[#1B1F3B]'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <OrdersIcon size={20} color={fulfillmentType === 'delivery' ? '#1B1F3B' : '#777777'} />
                  <span className="text-xs font-bold text-slate-900">{t('commerce.delivery')}</span>
                </div>
                <span className="text-[11px] text-slate-500 font-light">2-3 Business Days · Luxury Garment Bag</span>
              </button>

              <button
                type="button"
                onClick={() => setFulfillmentType('bopis')}
                className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between ${
                  fulfillmentType === 'bopis'
                    ? 'border-[#C5A059] bg-[#FDF8EE] ring-1 ring-[#C5A059]'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <BopisIcon size={20} color={fulfillmentType === 'bopis' ? '#C5A059' : '#777777'} />
                  <span className="text-xs font-bold text-slate-900">{t('commerce.bopis')}</span>
                </div>
                <span className="text-[11px] text-[#A37E44] font-semibold">Ready in 2 Hours · Zero Shipping Fee</span>
              </button>
            </div>

            {/* BOPIS Store Selector if BOPIS chosen */}
            {fulfillmentType === 'bopis' && (
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <label className="text-xs font-bold text-slate-800 block">
                  Select Boutique for Collection:
                </label>
                <div className="space-y-2">
                  {[
                    { id: 1, name: 'Massimo Dutti — The Dubai Mall (Fashion Avenue)', time: 'Ready today by 4:00 PM' },
                    { id: 2, name: 'Massimo Dutti — Mall of the Emirates (Central Galleria)', time: 'Ready today by 5:30 PM' },
                  ].map((s) => (
                    <label
                      key={s.id}
                      className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all ${
                        selectedBopisStoreId === s.id
                          ? 'border-[#C5A059] bg-white ring-1 ring-[#C5A059]'
                          : 'border-slate-200 bg-[#FAF9F6]'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <input
                          type="radio"
                          name="bopis_store"
                          checked={selectedBopisStoreId === s.id}
                          onChange={() => setSelectedBopisStoreId(s.id)}
                          className="accent-[#C5A059]"
                        />
                        <div className="text-xs">
                          <div className="font-bold text-slate-900">{s.name}</div>
                          <div className="text-[10px] text-emerald-600 font-semibold">{s.time}</div>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 2. Recipient & Address Form */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
              2. Contact & Address Details:
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="Layla Al-Mansoor"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1">Phone (for SMS OTP / Courier)</label>
                <input
                  type="text"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
              </div>
            </div>

            {fulfillmentType === 'delivery' && (
              <>
                <div>
                  <label className="text-xs font-bold text-slate-800 block mb-1">Delivery Address</label>
                  <input
                    type="text"
                    required
                    value={addressLine}
                    onChange={(e) => setAddressLine(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-bold text-slate-800 block mb-1">City</label>
                    <input
                      type="text"
                      required
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-800 block mb-1">Country</label>
                    <input
                      type="text"
                      required
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs"
                    />
                  </div>
                </div>
              </>
            )}
          </div>

          {/* 3. Payment Method & BNPL Selector (PDF G5.2) */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
              3. Payment & Installments:
            </h3>

            <div className="space-y-2.5">
              {[
                { id: 'bnpl_tabby' as const, name: 'Tabby', desc: 'Split into 4 interest-free payments of $' + (total / 4).toFixed(2), highlight: true },
                { id: 'bnpl_tamara' as const, name: 'Tamara', desc: 'Split into 4 payments of $' + (total / 4).toFixed(2), highlight: true },
                { id: 'card' as const, name: 'Credit or Debit Card', desc: 'Visa, Mastercard, American Express', highlight: false },
                { id: 'apple_pay' as const, name: 'Apple Pay', desc: 'Instant biometric checkout', highlight: false },
                { id: 'cod' as const, name: 'Cash on Delivery', desc: 'Pay when delivered to your doorstep', highlight: false },
              ].map((pm) => (
                <label
                  key={pm.id}
                  className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
                    paymentMethod === pm.id
                      ? 'border-[#C5A059] bg-[#FDF8EE] ring-1 ring-[#C5A059]'
                      : 'border-slate-200 bg-white hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="payment_method"
                      checked={paymentMethod === pm.id}
                      onChange={() => setPaymentMethod(pm.id)}
                      className="accent-[#C5A059]"
                    />
                    <div>
                      <div className="text-xs font-bold text-slate-900 flex items-center gap-2">
                        <span>{pm.name}</span>
                        {pm.highlight && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-[#C5A059] text-slate-950 font-bold">
                            0% Interest
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-500 font-light">{pm.desc}</div>
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Order Summary (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B] pb-3 border-b border-slate-100">
              Order Summary ({cart?.items_count || 0} Items)
            </h3>

            {/* Item list preview */}
            <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
              {cart?.items.map((it) => (
                <div key={it.id} className="flex gap-3 text-xs">
                  <div className="w-12 h-14 rounded-xl bg-slate-100 overflow-hidden shrink-0 border border-slate-200/60">
                    <img src={it.image_url} alt={it.product_title} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-slate-900 truncate">{it.product_title}</div>
                    <div className="text-slate-500 text-[11px] font-light">Size {it.size} · Qty {it.quantity}</div>
                    <div className="text-slate-900 font-bold mt-0.5">${it.subtotal}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Promo Code Input */}
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                value={promoCode}
                onChange={(e) => setPromoCode(e.target.value)}
                placeholder="Promo code (e.g. CONFIT10)"
                className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 text-xs uppercase font-semibold focus:outline-none focus:border-[#C5A059]"
              />
              <button
                type="button"
                className="px-3.5 py-2 rounded-xl bg-slate-100 text-xs font-bold text-slate-700 hover:bg-slate-200 transition-colors"
              >
                Apply
              </button>
            </div>

            {/* Cost Breakdown */}
            <div className="space-y-2 text-xs text-slate-600 pt-3 border-t border-slate-100 font-light">
              <div className="flex justify-between">
                <span>Subtotal</span>
                <span className="font-medium text-slate-900">${subtotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-emerald-600 font-medium">
                <span>Promotional Discount (CONFIT10)</span>
                <span>-$20.00</span>
              </div>
              <div className="flex justify-between">
                <span>VAT & Duties (5%)</span>
                <span>${((subtotal - 20) * 0.05).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-emerald-600 font-medium">
                <span>Shipping</span>
                <span>{fulfillmentType === 'bopis' ? 'Free Boutique Pickup' : 'Free Express'}</span>
              </div>
              <div className="flex justify-between text-base font-bold text-[#1B1F3B] pt-3 border-t border-slate-200">
                <span>Total Amount</span>
                <span>${total.toFixed(2)}</span>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !cart || cart.items_count === 0}
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <SparkleIcon size={16} color="#C5A059" />
              <span>
                {isSubmitting
                  ? 'Securing Order...'
                  : !isAuthenticated
                  ? 'Sign In & Place Order'
                  : 'Confirm & Place Order'}
              </span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
