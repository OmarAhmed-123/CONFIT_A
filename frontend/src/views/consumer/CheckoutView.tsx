import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { catalogService, commerceService } from '../../services/apiServices';
import { StoreInventoryLocation } from '../../models';
import {
  BopisIcon,
  OrdersIcon,
  SparkleIcon,
  UserIcon,
} from '../../components/icons/ConfitIcons';
import { BNPLBadge } from '../../components/common/CommonComponents';

function marketCode(country: string): string {
  const c = country.trim().toUpperCase();
  if (c === 'UAE' || c === 'UNITED ARAB EMIRATES') return 'AE';
  if (c === 'KSA' || c === 'SAUDI ARABIA') return 'SA';
  if (c.length === 2) return c;
  return 'AE';
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `chk_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export const CheckoutView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { cart, fetchCart, applyPromo } = useCartStore();
  const { user, isAuthenticated } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();

  const [fulfillmentType, setFulfillmentType] = useState<'delivery' | 'bopis'>('delivery');
  const [shippingMethod, setShippingMethod] = useState<'standard' | 'express'>('standard');
  const [selectedBopisStoreId, setSelectedBopisStoreId] = useState<number | null>(null);
  const [bopisStores, setBopisStores] = useState<StoreInventoryLocation[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<string>('card');
  const [paymentOptions, setPaymentOptions] = useState<
    Array<{ id: string; title_en: string; description_en: string; installment_available?: boolean }>
  >([]);

  const [recipientName, setRecipientName] = useState(user?.full_name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [guestEmail, setGuestEmail] = useState('');
  const [addressLine, setAddressLine] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('UAE');
  const [promoInput, setPromoInput] = useState(cart?.promo_code || '');
  const [promoError, setPromoError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  useEffect(() => {
    if (user) {
      setRecipientName(user.full_name);
      if (user.phone) setPhone(user.phone);
    }
  }, [user]);

  useEffect(() => {
    commerceService
      .getPaymentMethods(marketCode(country))
      .then((res) => {
        setPaymentOptions(res.available_methods || []);
        if (res.available_methods?.length && !res.available_methods.some((m) => m.id === paymentMethod)) {
          setPaymentMethod(res.available_methods[0].id);
        }
      })
      .catch(() => setPaymentOptions([]));
  }, [country]);

  useEffect(() => {
    const skuId = cart?.items?.[0]?.product_sku_id;
    if (!skuId || fulfillmentType !== 'bopis') return;
    catalogService
      .getBopisStoresForSKU(skuId)
      .then((stores) => {
        const available = stores.filter((s) => s.is_available_for_pickup);
        setBopisStores(available);
        if (available.length && selectedBopisStoreId == null) {
          setSelectedBopisStoreId(available[0].store_id);
        }
      })
      .catch(() => setBopisStores([]));
  }, [cart?.items, fulfillmentType, selectedBopisStoreId]);

  const total = cart?.total || 0;
  const subtotal = cart?.subtotal || 0;
  const discount = cart?.discount_amount || 0;
  const tax = cart?.tax_amount || 0;
  const shipping = cart?.shipping_amount || 0;

  const handleApplyPromo = async () => {
    setPromoError(null);
    try {
      await applyPromo(promoInput.trim());
      showToast('Promotion applied', 'success');
    } catch (err: any) {
      setPromoError(err?.message || 'Code could not be applied');
    }
  };

  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cart || cart.items_count === 0) {
      showToast('Your bag is empty.', 'error');
      return;
    }
    if (!isAuthenticated && !guestEmail.trim()) {
      showToast('Enter an email for guest checkout, or sign in.', 'info');
      return;
    }
    if (fulfillmentType === 'bopis' && !selectedBopisStoreId) {
      showToast('Select a boutique with stock for pickup.', 'error');
      return;
    }
    if (fulfillmentType === 'delivery' && !addressLine.trim()) {
      showToast('A delivery address is required.', 'error');
      return;
    }

    setIsSubmitting(true);
    try {
      const order = await commerceService.checkout({
        payment_method: paymentMethod,
        fulfillment_type: fulfillmentType,
        bopis_store_id: fulfillmentType === 'bopis' ? selectedBopisStoreId || undefined : undefined,
        recipient_name: recipientName,
        phone,
        address_line: fulfillmentType === 'delivery' ? addressLine : undefined,
        city,
        country,
        promo_code: promoInput || cart.promo_code || undefined,
        try_on_assisted: false,
        stylist_assisted: false,
        guest_email: isAuthenticated ? undefined : guestEmail.trim(),
        shipping_method: shippingMethod,
        idempotency_key: newIdempotencyKey(),
      });
      showToast('Order placed. Payment status is confirmed by the server.', 'success');
      await fetchCart();
      navigate(`/orders/${order.order_number}`);
    } catch (err: any) {
      showToast(err?.message || 'Checkout failed', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 pb-24 max-w-5xl mx-auto">
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
          {t('commerce.checkout')}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
          Multi-brand checkout. Totals, tax, and discounts are calculated on the server.
        </p>
      </div>

      {!isAuthenticated && (
        <div className="bg-[#FAF9F6] border border-[#C5A059]/40 rounded-3xl p-5 sm:p-6 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-[#0C0E1E] text-[#C5A059] flex items-center justify-center font-bold shrink-0 shadow-2xs">
              <UserIcon size={20} color="#C5A059" />
            </div>
            <div>
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                Guest checkout
              </h3>
              <p className="text-xs text-slate-500 font-light mt-0.5">
                Sign in to save your style profile, or continue as a guest with an email address.
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
        <div className="lg:col-span-7 space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">1. Fulfillment</h3>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setFulfillmentType('delivery')}
                className={`p-4 rounded-2xl border text-left transition-all ${
                  fulfillmentType === 'delivery'
                    ? 'border-[#1B1F3B] bg-[#FAF9F6] ring-1 ring-[#1B1F3B]'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <OrdersIcon size={20} color={fulfillmentType === 'delivery' ? '#1B1F3B' : '#777777'} />
                  <span className="text-xs font-bold text-slate-900">{t('commerce.delivery')}</span>
                </div>
                <span className="text-[11px] text-slate-500 font-light">Standard or express · estimated at checkout</span>
              </button>
              <button
                type="button"
                onClick={() => setFulfillmentType('bopis')}
                className={`p-4 rounded-2xl border text-left transition-all ${
                  fulfillmentType === 'bopis'
                    ? 'border-[#C5A059] bg-[#FDF8EE] ring-1 ring-[#C5A059]'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <BopisIcon size={20} color={fulfillmentType === 'bopis' ? '#C5A059' : '#777777'} />
                  <span className="text-xs font-bold text-slate-900">{t('commerce.bopis')}</span>
                </div>
                <span className="text-[11px] text-[#A37E44] font-semibold">Pickup from stores with live stock</span>
              </button>
            </div>

            {fulfillmentType === 'delivery' && (
              <div className="flex gap-2">
                {(['standard', 'express'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setShippingMethod(m)}
                    className={`px-4 py-2 rounded-xl text-xs font-bold border ${
                      shippingMethod === m ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white' : 'border-slate-200'
                    }`}
                  >
                    {m === 'standard' ? 'Standard' : 'Express'}
                  </button>
                ))}
              </div>
            )}

            {fulfillmentType === 'bopis' && (
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <label className="text-xs font-bold text-slate-800 block">Boutique with stock</label>
                {bopisStores.length === 0 ? (
                  <p className="text-xs text-slate-500">No store currently holds this SKU. Switch to home delivery.</p>
                ) : (
                  bopisStores.map((s) => (
                    <label
                      key={s.store_id}
                      className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer ${
                        selectedBopisStoreId === s.store_id
                          ? 'border-[#C5A059] bg-white ring-1 ring-[#C5A059]'
                          : 'border-slate-200 bg-[#FAF9F6]'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <input
                          type="radio"
                          name="bopis_store"
                          checked={selectedBopisStoreId === s.store_id}
                          onChange={() => setSelectedBopisStoreId(s.store_id)}
                          className="accent-[#C5A059]"
                        />
                        <div className="text-xs">
                          <div className="font-bold text-slate-900">{s.store_name}</div>
                          <div className="text-[10px] text-slate-500">{s.address}</div>
                          <div className="text-[10px] text-emerald-600 font-semibold">{s.quantity_available} available</div>
                        </div>
                      </div>
                    </label>
                  ))
                )}
              </div>
            )}
          </div>

          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">2. Contact & address</h3>
            {!isAuthenticated && (
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="guest-email">
                  Guest email
                </label>
                <input
                  id="guest-email"
                  type="email"
                  required={!isAuthenticated}
                  value={guestEmail}
                  onChange={(e) => setGuestEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="full-name">Full name</label>
                <input
                  id="full-name"
                  type="text"
                  required
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="phone">Phone</label>
                <input
                  id="phone"
                  type="tel"
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
                  <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="address">Delivery address</label>
                  <input
                    id="address"
                    type="text"
                    required
                    value={addressLine}
                    onChange={(e) => setAddressLine(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="city">City</label>
                    <input
                      id="city"
                      type="text"
                      required
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="country">Country</label>
                    <input
                      id="country"
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

          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">3. Payment</h3>
            {paymentOptions.length === 0 ? (
              <p className="text-xs text-slate-500">Payment methods for this market could not be loaded.</p>
            ) : (
              <div className="space-y-2.5">
                {paymentOptions.map((pm) => (
                  <label
                    key={pm.id}
                    className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer ${
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
                        <div className="text-xs font-bold text-slate-900">{pm.title_en}</div>
                        <div className="text-[11px] text-slate-500 font-light">{pm.description_en}</div>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-5 space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B] pb-3 border-b border-slate-100">
              Order summary ({cart?.items_count || 0})
            </h3>
            {cart?.fit_summary && cart.fit_summary.length > 0 && (
              <ul className="text-[11px] text-slate-600 space-y-1">
                {cart.fit_summary.map((row) => (
                  <li key={row.cart_item_id}>
                    {row.title} — {row.verdict}
                  </li>
                ))}
              </ul>
            )}
            <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
              {(cart?.items || []).map((it) => (
                <div key={it.id} className="flex gap-3 text-xs">
                  <div className="w-12 h-14 rounded-xl bg-slate-100 overflow-hidden shrink-0 border border-slate-200/60">
                    <img src={it.image_url} alt={it.product_title} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-slate-900 truncate">{it.product_title}</div>
                    <div className="text-slate-500 text-[11px] font-light">
                      {it.brand_name} · Size {it.size} · Qty {it.quantity}
                    </div>
                    <div className="text-slate-900 font-bold mt-0.5">${it.subtotal.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                value={promoInput}
                onChange={(e) => setPromoInput(e.target.value)}
                placeholder="Promo code"
                aria-label="Promo code"
                className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 text-xs uppercase font-semibold focus:outline-none focus:border-[#C5A059]"
              />
              <button
                type="button"
                onClick={handleApplyPromo}
                className="px-3.5 py-2 rounded-xl bg-slate-100 text-xs font-bold text-slate-700 hover:bg-slate-200 transition-colors"
              >
                Apply
              </button>
            </div>
            {promoError && <p className="text-[11px] text-rose-600">{promoError}</p>}
            <div className="space-y-2 text-xs text-slate-600 pt-3 border-t border-slate-100 font-light">
              <div className="flex justify-between">
                <span>Subtotal</span>
                <span className="font-medium text-slate-900">${subtotal.toFixed(2)}</span>
              </div>
              {discount > 0 && (
                <div className="flex justify-between text-emerald-600 font-medium">
                  <span>Discount {cart?.promo_code ? `(${cart.promo_code})` : ''}</span>
                  <span>-${discount.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Tax</span>
                <span>${tax.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span>Shipping</span>
                <span>{fulfillmentType === 'bopis' ? 'Pickup' : `$${shipping.toFixed(2)}`}</span>
              </div>
              <div className="flex justify-between text-base font-bold text-[#1B1F3B] pt-3 border-t border-slate-200">
                <span>Total</span>
                <span>${total.toFixed(2)}</span>
              </div>
            </div>
            {cart && cart.bnpl_monthly_quote > 0 && (
              <BNPLBadge price={total} installmentAmount={cart.bnpl_monthly_quote} eligible />
            )}
            <button
              type="submit"
              disabled={isSubmitting || !cart || cart.items_count === 0}
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <SparkleIcon size={16} color="#C5A059" />
              <span>{isSubmitting ? 'Placing order...' : 'Place order'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
