import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCartStore } from '../../stores/cartStore';
import { BagIcon, SparkleIcon } from '../icons/ConfitIcons';
import { BNPLBadge } from '../common/CommonComponents';
import { HonestProductImage } from '../common/HonestProductImage';
import { formatMoney } from '../../i18n/format';
import { useModalFocus } from '../../hooks/useModalFocus';

export const CartDrawer: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const isRtl = i18n.dir() === 'rtl';
  const navigate = useNavigate();
  const { cart, isOpen, closeCart, fetchCart, updateQuantity, removeItem } = useCartStore();
  const drawerRef = useModalFocus<HTMLDivElement>(closeCart, isOpen);

  useEffect(() => {
    if (isOpen) {
      fetchCart();
    }
  }, [isOpen, fetchCart]);

  if (!isOpen) return null;

  const items = cart?.items || [];
  const total = cart?.total || 0;
  const subtotal = cart?.subtotal || 0;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-slate-950/50 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeCart();
      }}
    >
      <div className="absolute inset-y-0 end-0 max-w-full flex ps-10">
        <div
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="cart-drawer-title"
          tabIndex={-1}
          className="w-screen max-w-md bg-white shadow-2xl flex flex-col border-s border-slate-200 outline-none"
        >
          {/* Header */}
          <div className="p-4 sm:p-6 border-b border-slate-100 flex items-center justify-between bg-brand-wash">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-brand-charcoal text-white flex items-center justify-center">
                <BagIcon size={20} color="#FFFFFF" />
              </div>
              <div>
                <h3 id="cart-drawer-title" className="font-serif text-base font-bold text-brand-charcoal">
                  {t('commerce.cart_title')}
                </h3>
                <span className="text-xs text-slate-500" aria-live="polite">
                  {cart?.items_count || 0} {t('commerce.items_from_boutiques')}
                </span>
              </div>
            </div>
            <button data-motion="neutral" data-motion-tone="icon"
              onClick={closeCart}
              aria-label={t('common.close')}
              className="min-w-[44px] min-h-[44px] rounded-full bg-slate-100 text-slate-500 hover:text-slate-900 flex items-center justify-center transition-colors"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>

          {/* Cart Item List */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {items.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-slate-100 mx-auto flex items-center justify-center text-slate-500 mb-3">
                  <BagIcon size={28} />
                </div>
                <h4 className="font-serif text-base font-bold text-brand-charcoal mb-1">
                  {t('commerce.cart_empty_title')}
                </h4>
                <p className="text-xs text-slate-500 max-w-xs mx-auto mb-4">
                  {t('commerce.cart_empty_body')}
                </p>
                <button data-motion="progressive"
                  onClick={() => {
                    closeCart();
                    navigate('/discover');
                  }}
                  className="px-5 py-2.5 rounded-full bg-brand-charcoal text-white text-xs font-semibold hover:bg-black transition-all"
                >
                  {t('commerce.explore_catalog')}
                </button>
              </div>
            ) : (
              items.map((item) => (
                <div
                  key={item.id}
                  className="flex gap-3.5 p-3 rounded-2xl bg-brand-wash border border-slate-200/80 hover:border-slate-300 transition-all"
                >
                  <div className="w-20 h-24 rounded-xl overflow-hidden bg-white shrink-0">
                    <HonestProductImage src={item.image_url} alt={item.product_title} className="w-full h-full object-cover" />
                  </div>

                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                          {item.brand_name}
                        </span>
                        <button data-motion="destructive" data-motion-tone="icon"
                          onClick={() => removeItem(item.id)}
                          className="min-w-[44px] min-h-[44px] text-slate-500 hover:text-rose-500 text-xs flex items-center justify-center rounded"
                          title={t('commerce.remove_item')}
                          aria-label={t('commerce.remove_item')}
                        >
                          <span aria-hidden="true">✕</span>
                        </button>
                      </div>
                      <h4 className="text-xs font-bold text-brand-charcoal truncate">{item.product_title}</h4>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-600">
                        <span>{t('audit_closure.cart_size_prefix')} <strong><bdi dir="ltr">{item.size}</bdi></strong></span>
                        <span>•</span>
                        <span>{item.color}</span>
                      </div>
                      <div className="text-[10px] text-emerald-700 font-medium mt-0.5 flex items-center gap-1">
                        <SparkleIcon size={10} color="#059669" />
                        <span>{item.ai_fit_verdict}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-200/60 mt-1">
                      <div className="flex items-center border border-slate-200 rounded-lg bg-white">
                        <button data-motion="commerce" data-motion-tone="icon"
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          className="min-w-[44px] min-h-[44px] px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-100 rounded-s flex items-center justify-center"
                          aria-label={t('audit_closure.cart_decrease_item', { title: item.product_title })}
                        >
                          <span aria-hidden="true">-</span>
                        </button>
                        <span className="px-2 text-xs font-bold text-slate-800" aria-live="polite">{item.quantity}</span>
                        <button data-motion="commerce" data-motion-tone="icon"
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          className="min-w-[44px] min-h-[44px] px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-100 rounded-e flex items-center justify-center"
                          aria-label={t('audit_closure.cart_increase_item', { title: item.product_title })}
                        >
                          <span aria-hidden="true">+</span>
                        </button>
                      </div>
                      <span className="text-xs font-bold text-brand-charcoal">
                        <bdi dir="ltr">{formatMoney(Math.round(item.subtotal * 100), cart?.currency || 'USD', lang)}</bdi>
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer Checkout Summary */}
          {items.length > 0 && (
            <div className="p-4 sm:p-6 border-t border-slate-200 bg-white space-y-3">
              {/* Every line item above already rendered through
                  formatMoney(cart.currency) — but this totals block hardcoded
                  the "$" glyph, so an EGP cart showed dollar-prefixed EGP
                  numbers in its own summary (2026-10-07 audit). Same
                  formatter, same currency authority, every row. */}
              <div className="space-y-1.5 text-xs text-slate-600">
                <div className="flex justify-between">
                  <span>{t('commerce.subtotal')}</span>
                  <span className="font-semibold text-slate-900">
                    <bdi dir="ltr">{formatMoney(Math.round(subtotal * 100), cart?.currency || 'USD', lang)}</bdi>
                  </span>
                </div>
                {(cart?.discount_amount || 0) > 0 && (
                  <div className="flex justify-between text-emerald-600">
                    <span>{t('commerce.discount')}</span>
                    <span><bdi dir="ltr">-{formatMoney(Math.round((cart?.discount_amount || 0) * 100), cart?.currency || 'USD', lang)}</bdi></span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span>{t('commerce.tax')}</span>
                  <span><bdi dir="ltr">{formatMoney(Math.round((cart?.tax_amount ?? 0) * 100), cart?.currency || 'USD', lang)}</bdi></span>
                </div>
                <div className="flex justify-between">
                  <span>{t('commerce.shipping')}</span>
                  <span><bdi dir="ltr">{formatMoney(Math.round((cart?.shipping_amount ?? 0) * 100), cart?.currency || 'USD', lang)}</bdi></span>
                </div>
                <div className="flex justify-between text-sm font-bold text-brand-charcoal pt-2 border-t border-slate-100">
                  <span>{t('commerce.total')}</span>
                  <span><bdi dir="ltr">{formatMoney(Math.round(total * 100), cart?.currency || 'USD', lang)}</bdi></span>
                </div>
              </div>

              {cart && cart.bnpl_monthly_quote > 0 && (
                <div className="p-2.5 rounded-xl bg-brand-wash border border-brand-hairline text-center">
                  <BNPLBadge
                    currency={cart.currency || 'USD'}
                    installmentAmount={cart.bnpl_monthly_quote}
                    isEstimate={cart.bnpl_is_estimate !== false}
                    eligible
                  />
                </div>
              )}

              <button data-motion="financial"
                onClick={() => {
                  closeCart();
                  navigate('/checkout');
                }}
                className="w-full py-3.5 rounded-xl bg-brand-charcoal hover:bg-black text-white font-bold text-xs shadow-lg transition-all flex items-center justify-center gap-2"
              >
                <span>{t('commerce.checkout')}</span>
                <span aria-hidden="true">{isRtl ? '←' : '→'}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
