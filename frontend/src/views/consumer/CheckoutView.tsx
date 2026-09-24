import { validateCheckoutSubmission, isValidEmail, CheckoutField } from '../../lib/checkoutValidation';
import { generateIdempotencyKey } from '../../lib/secureId';
import { localizeApiError } from '../../i18n/apiErrors';
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
  // Same CSPRNG helper as the guest session token. This key is what tells the
  // backend that a retry is the SAME purchase, so a collision is a correctness
  // bug (a replay answered with the wrong order) and a predictable key is a
  // replay hazard. See lib/secureId.ts (2026-09-22 consumer closure).
  return generateIdempotencyKey();
}

export const CheckoutView: React.FC = () => {
  const { t, i18n } = useTranslation();
  // Same precedent as BNPLBadge: pick the localized field by LANGUAGE, not by
  // visual direction. The API ships title_ar/description_ar for every method
  // and the checkout was rendering title_en to Arabic shoppers.
  const isArabic = (i18n.resolvedLanguage ?? 'en').startsWith('ar');
  const navigate = useNavigate();
  const { cart, fetchCart, applyPromo, updateQuantity, removeItem } = useCartStore();
  const { user, isAuthenticated } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();

  const [fulfillmentType, setFulfillmentType] = useState<'delivery' | 'bopis'>('delivery');
  const [shippingMethod, setShippingMethod] = useState<'standard' | 'express'>('standard');
  const [selectedBopisStoreId, setSelectedBopisStoreId] = useState<number | null>(null);
  const [bopisStores, setBopisStores] = useState<StoreInventoryLocation[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<string>('card');
  const [paymentOptions, setPaymentOptions] = useState<
    Array<{
      id: string;
      title_en: string;
      title_ar?: string;
      description_en: string;
      description_ar?: string;
      /**
       * Server-derived from `payment_method_is_live()`. False = this deployment
       * cannot settle with this method; the option is still selectable in demo
       * mode, but the shopper is told which is which.
       */
      is_live?: boolean;
      installment_available?: boolean;
    }>
  >([]);

  const [recipientName, setRecipientName] = useState(user?.full_name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [guestEmail, setGuestEmail] = useState('');
  const [fieldError, setFieldError] = useState<CheckoutField | null>(null);
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
    // P0-01 fix: same rules, but now machine-usable — the offending field is
    // highlighted inline, scrolled into view and marked aria-invalid instead
    // of relying on a transient toast that guests routinely missed.
    const verdict = validateCheckoutSubmission({
      isAuthenticated,
      itemsCount: cart?.items_count ?? 0,
      guestEmail,
      fulfillmentType,
      bopisStoreId: selectedBopisStoreId,
      addressLine,
      recipientName,
      phone,
    });
    if (!verdict.ok) {
      setFieldError(verdict.field ?? null);
      showToast(verdict.message || 'Please complete the highlighted fields.', 'error');
      const fieldId =
        verdict.field === 'guest_email' ? 'guest-email' :
        verdict.field === 'recipient_name' ? 'full-name' :
        verdict.field === 'phone' ? 'phone' :
        verdict.field === 'address' ? 'address' : null;
      if (fieldId) {
        const el = document.getElementById(fieldId);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        (el as HTMLInputElement | null)?.focus({ preventScroll: true });
      }
      return;
    }
    setFieldError(null);

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
      // Localized by error CODE, so an Arabic shopper reads Arabic instead of a
      // raw English server diagnostic on the payment path. Unknown codes keep
      // the server's own wording rather than a vague generic sentence.
      showToast(localizeApiError(err, t), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 pb-24 max-w-5xl mx-auto">
      {/* C4 FIX: Payment Demo Safety - unmistakable banner when PAYMENTS_LIVE=false */}
      <div className="bg-amber-50 border-2 border-amber-400 rounded-2xl p-4 flex items-start gap-3">
        <div className="text-amber-600 text-xl">⚠️</div>
        <div className="flex-1">
          <h4 className="text-xs font-black text-amber-900 uppercase tracking-widest">{t('checkout.demo_mode_title')}</h4>
          <p className="text-[11px] text-amber-800 mt-1 leading-relaxed">
            {t('checkout.demo_mode_body')}
          </p>
        </div>
      </div>

      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
          {t('commerce.checkout')}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
          {t('checkout.subtitle_server_totals')}
        </p>
      </div>

      {cart && cart.items_count === 0 ? (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-10 shadow-2xs text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/40 flex items-center justify-center mx-auto">
            <OrdersIcon size={26} color="#C5A059" />
          </div>
          <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">{t('commerce.cart_title')}</h2>
          <p className="text-sm text-slate-500 font-light max-w-md mx-auto">{t('commerce.cart_empty')}</p>
          <button
            type="button"
            onClick={() => navigate('/discover')}
            className="px-6 py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-2xs transition-all"
          >
            {t('commerce.cart_explore')}
          </button>
        </div>
      ) : (
      <>
      {!isAuthenticated && (
        <div className="bg-[#FAF9F6] border border-[#C5A059]/40 rounded-3xl p-5 sm:p-6 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-[#0C0E1E] text-[#C5A059] flex items-center justify-center font-bold shrink-0 shadow-2xs">
              <UserIcon size={20} color="#C5A059" />
            </div>
            <div>
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                {t('checkout.guest_checkout')}
              </h3>
              <p className="text-xs text-slate-500 font-light mt-0.5">
                {t('checkout.guest_intro')}
              </p>
            </div>
          </div>
          <div className="flex gap-2.5 shrink-0 w-full sm:w-auto">
            <button
              type="button"
              onClick={() => openAuthModal('login')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-2xs transition-all"
            >
              {t('common.sign_in')}
            </button>
            <button
              type="button"
              onClick={() => openAuthModal('register')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 text-xs font-semibold shadow-2xs transition-all"
            >
              {t('common.create_account')}
            </button>
          </div>
        </div>
      )}

      <form noValidate onSubmit={handleSubmitOrder} className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('checkout.step_fulfillment')}</h3>
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
                <span className="text-[11px] text-slate-500 font-light">{t('checkout.shipping_estimate')}</span>
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
                <span className="text-[11px] text-[#A37E44] font-semibold">{t('checkout.pickup_live_stock')}</span>
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
                    {m === 'standard' ? t('checkout.shipping_standard') : t('checkout.shipping_express')}
                  </button>
                ))}
              </div>
            )}

            {fulfillmentType === 'bopis' && (
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <label className="text-xs font-bold text-slate-800 block">{t('checkout.boutique_with_stock')}</label>
                {bopisStores.length === 0 ? (
                  <p className="text-xs text-slate-500">{t('checkout.no_store_for_sku')}</p>
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
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('checkout.step_contact')}</h3>
            {!isAuthenticated && (
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="guest-email">
                  {t('checkout.guest_email')}
                </label>
                <input
                  id="guest-email"
                  type="email"
                  required={!isAuthenticated}
                  aria-invalid={fieldError === 'guest_email'}
                  aria-describedby={fieldError === 'guest_email' ? 'guest-email-error' : undefined}
                  value={guestEmail}
                  onChange={(e) => { setGuestEmail(e.target.value); if (fieldError === 'guest_email') setFieldError(null); }}
                  placeholder={t('checkout.email_placeholder')}
                  className={`w-full px-4 py-2.5 rounded-xl border text-xs focus:outline-none focus:border-[#C5A059] ${fieldError === 'guest_email' ? 'border-rose-400 bg-rose-50' : 'border-slate-200'}`}
                />
                {fieldError === 'guest_email' && (
                  <p id="guest-email-error" role="alert" className="text-[11px] text-rose-600 font-semibold mt-1">
                    {isValidEmail(guestEmail.trim()) || !guestEmail.trim()
                      ? t('errors.guest_email_required')
                      : t('errors.email_invalid')}
                  </p>
                )}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="full-name">{t('checkout.full_name')}</label>
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
                <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="phone">{t('checkout.phone')}</label>
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
                  <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="address">{t('checkout.delivery_address')}</label>
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
                    <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="city">{t('checkout.city')}</label>
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
                    <label className="text-xs font-bold text-slate-800 block mb-1" htmlFor="country">{t('checkout.country')}</label>
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
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('checkout.step_payment')}</h3>
            {paymentOptions.length === 0 ? (
              <p className="text-xs text-slate-500">{t('checkout.payment_methods_unavailable')}</p>
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
                        {/* Localized: the API ships both languages, and an Arabic
                            shopper was being shown the English `title_en`. */}
                        <div className="text-xs font-bold text-slate-900">
                          {isArabic && pm.title_ar ? pm.title_ar : pm.title_en}
                        </div>
                        <div className="text-[11px] text-slate-500 font-light">
                          {isArabic && pm.description_ar ? pm.description_ar : pm.description_en}
                        </div>
                        {pm.is_live === false && (
                          <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-300 rounded px-1.5 py-0.5">
                            {t('checkout.payment_method_demo_note')}
                          </div>
                        )}
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
              {t('checkout.order_summary')} ({cart?.items_count || 0})
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
                      {it.brand_name} · {t('checkout.size')} {it.size}
                    </div>
                    <div className="text-slate-900 font-bold mt-0.5">${it.subtotal.toFixed(2)}</div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <button
                        type="button"
                        aria-label={t('commerce.qty_decrease')}
                        disabled={it.quantity <= 1}
                        onClick={() => {
                          updateQuantity(it.id, it.quantity - 1).catch(() => showToast('Could not update quantity', 'error'));
                        }}
                        className="w-6 h-6 rounded-lg border border-slate-200 text-slate-700 font-bold leading-none hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        −
                      </button>
                      <span className="text-[11px] text-slate-600 font-medium w-10 text-center" aria-live="polite">
                        {t('checkout.qty')} {it.quantity}
                      </span>
                      <button
                        type="button"
                        aria-label={t('commerce.qty_increase')}
                        disabled={it.quantity >= 10}
                        onClick={() => {
                          updateQuantity(it.id, it.quantity + 1).catch(() => showToast('Could not update quantity', 'error'));
                        }}
                        className="w-6 h-6 rounded-lg border border-slate-200 text-slate-700 font-bold leading-none hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        +
                      </button>
                      <button
                        type="button"
                        aria-label={t('commerce.remove_item')}
                        onClick={() => {
                          removeItem(it.id).catch(() => showToast('Could not remove item', 'error'));
                        }}
                        className="ml-auto text-[10px] font-semibold text-slate-400 hover:text-rose-600 underline underline-offset-2"
                      >
                        {t('commerce.remove_item')}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                value={promoInput}
                onChange={(e) => setPromoInput(e.target.value)}
                placeholder={t('checkout.promo_code')}
                aria-label={t('checkout.promo_code')}
                className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 text-xs uppercase font-semibold focus:outline-none focus:border-[#C5A059]"
              />
              <button
                type="button"
                onClick={handleApplyPromo}
                className="px-3.5 py-2 rounded-xl bg-slate-100 text-xs font-bold text-slate-700 hover:bg-slate-200 transition-colors"
              >
                {t('common.apply')}
              </button>
            </div>
            {promoError && <p className="text-[11px] text-rose-600">{promoError}</p>}
            <div className="space-y-2 text-xs text-slate-600 pt-3 border-t border-slate-100 font-light">
              <div className="flex justify-between">
                <span>{t('commerce.subtotal')}</span>
                <span className="font-medium text-slate-900">${subtotal.toFixed(2)}</span>
              </div>
              {discount > 0 && (
                <div className="flex justify-between text-emerald-600 font-medium">
                  <span>{t('commerce.discount')} {cart?.promo_code ? `(${cart.promo_code})` : ''}</span>
                  <span>-${discount.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span>{t('checkout.tax')}</span>
                <span>${tax.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span>{t('commerce.shipping')}</span>
                <span>{fulfillmentType === 'bopis' ? t('checkout.pickup') : `$${shipping.toFixed(2)}`}</span>
              </div>
              <div className="flex justify-between text-base font-bold text-[#1B1F3B] pt-3 border-t border-slate-200">
                <span>{t('commerce.total')}</span>
                <span>${total.toFixed(2)}</span>
              </div>
            </div>
            {cart && cart.bnpl_monthly_quote > 0 && (
              <BNPLBadge
                price={total}
                installmentAmount={cart.bnpl_monthly_quote}
                isEstimate={cart.bnpl_is_estimate !== false}
                eligible
              />
            )}
            <button
              type="submit"
              disabled={isSubmitting || !cart || cart.items_count === 0}
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <SparkleIcon size={16} color="#C5A059" />
              <span>{isSubmitting ? t('checkout.placing_order') : t('checkout.place_order')}</span>
            </button>
          </div>
        </div>
      </form>
      </>
      )}
    </div>
  );
};
