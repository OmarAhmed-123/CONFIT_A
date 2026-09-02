import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCartStore } from '../../stores/cartStore';
import { BagIcon, SparkleIcon } from '../icons/ConfitIcons';
import { BNPLBadge } from '../common/CommonComponents';

export const CartDrawer: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { cart, isOpen, closeCart, fetchCart, updateQuantity, removeItem } = useCartStore();

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
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/50 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col border-l border-slate-200">
          {/* Header */}
          <div className="p-4 sm:p-6 border-b border-slate-100 flex items-center justify-between bg-[#FAF9F6]">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#1B1F3B] text-white flex items-center justify-center">
                <BagIcon size={20} color="#FFFFFF" />
              </div>
              <div>
                <h3 className="font-serif text-base font-bold text-[#1B1F3B]">
                  {t('commerce.cart_title')}
                </h3>
                <span className="text-xs text-slate-500">
                  {cart?.items_count || 0} items from multi-brand boutiques
                </span>
              </div>
            </div>
            <button
              onClick={closeCart}
              className="w-8 h-8 rounded-full bg-slate-100 text-slate-500 hover:text-slate-900 flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Cart Item List */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {items.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-slate-100 mx-auto flex items-center justify-center text-slate-400 mb-3">
                  <BagIcon size={28} />
                </div>
                <h4 className="font-serif text-base font-bold text-[#1B1F3B] mb-1">
                  Your bag is currently empty
                </h4>
                <p className="text-xs text-slate-500 max-w-xs mx-auto mb-4">
                  Discover curated silhouettes or style your personal look with our AI Director.
                </p>
                <button
                  onClick={() => {
                    closeCart();
                    navigate('/discover');
                  }}
                  className="px-5 py-2.5 rounded-full bg-[#1B1F3B] text-white text-xs font-semibold hover:bg-[#2A3C78] transition-all"
                >
                  Explore Fashion Catalog
                </button>
              </div>
            ) : (
              items.map((item) => (
                <div
                  key={item.id}
                  className="flex gap-3.5 p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80 hover:border-slate-300 transition-all"
                >
                  <div className="w-20 h-24 rounded-xl overflow-hidden bg-white shrink-0">
                    <img src={item.image_url} alt={item.product_title} className="w-full h-full object-cover" />
                  </div>

                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          {item.brand_name}
                        </span>
                        <button
                          onClick={() => removeItem(item.id)}
                          className="text-slate-400 hover:text-rose-500 text-xs"
                          title="Remove item"
                        >
                          ✕
                        </button>
                      </div>
                      <h4 className="text-xs font-bold text-[#1B1F3B] truncate">{item.product_title}</h4>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-600">
                        <span>Size: <strong>{item.size}</strong></span>
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
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          className="px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-100 rounded-l"
                        >
                          -
                        </button>
                        <span className="px-2 text-xs font-bold text-slate-800">{item.quantity}</span>
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          className="px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-100 rounded-r"
                        >
                          +
                        </button>
                      </div>
                      <span className="text-xs font-bold text-[#1B1F3B]">${item.subtotal}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer Checkout Summary */}
          {items.length > 0 && (
            <div className="p-4 sm:p-6 border-t border-slate-200 bg-white space-y-3">
              <div className="space-y-1.5 text-xs text-slate-600">
                <div className="flex justify-between">
                  <span>{t('commerce.subtotal')}</span>
                  <span className="font-semibold text-slate-900">${subtotal.toFixed(2)}</span>
                </div>
                {(cart?.discount_amount || 0) > 0 && (
                  <div className="flex justify-between text-emerald-600">
                    <span>Discount</span>
                    <span>-${(cart?.discount_amount || 0).toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span>{t('commerce.tax')}</span>
                  <span>${(cart?.tax_amount ?? 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span>{t('commerce.shipping')}</span>
                  <span>${(cart?.shipping_amount ?? 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm font-bold text-[#1B1F3B] pt-2 border-t border-slate-100">
                  <span>{t('commerce.total')}</span>
                  <span>${total.toFixed(2)}</span>
                </div>
              </div>

              {cart && cart.bnpl_monthly_quote > 0 && (
                <div className="p-2.5 rounded-xl bg-[#FDF8EE] border border-[#B8935A]/30 text-center">
                  <BNPLBadge price={total} installmentAmount={cart.bnpl_monthly_quote} eligible />
                </div>
              )}

              <button
                onClick={() => {
                  closeCart();
                  navigate('/checkout');
                }}
                className="w-full py-3.5 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white font-bold text-xs shadow-lg transition-all flex items-center justify-center gap-2"
              >
                <span>{t('commerce.checkout')}</span>
                <span>→</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
