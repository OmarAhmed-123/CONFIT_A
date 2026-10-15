import React from 'react';
import { useTranslation } from 'react-i18next';
import type { BrandPromotion } from '../../models';

interface PromotionBannerProps {
  promotions: BrandPromotion[];
  brandName?: string;
  branchName?: string;
}

export const PromotionBanner: React.FC<PromotionBannerProps> = ({
  promotions,
  brandName,
  branchName,
}) => {
  const { t } = useTranslation();
  if (!promotions || promotions.length === 0) return null;

  return (
    <div className="space-y-3" role="region" aria-label={t('brands.active_promotions_aria')}>
      {promotions.map((promo) => (
        <div
          key={promo.id}
          className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-brand-charcoal via-neutral-900 to-brand-charcoal p-5 text-white shadow-sm border border-neutral-800"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider bg-brand-coral text-white">
                  {promo.discount_type === 'percent'
                    ? `${promo.discount_value}% OFF`
                    : `${promo.currency} ${promo.discount_value} OFF`}
                </span>
                {promo.code && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-white/10 text-brand-mint border border-white/10">
                    CODE: {promo.code}
                  </span>
                )}
                {branchName ? (
                  <span className="text-[11px] text-neutral-300 font-medium">
                    Branch Offer • {branchName}
                  </span>
                ) : (
                  <span className="text-[11px] text-neutral-300 font-medium">
                    Official Partner Offer {brandName ? `• ${brandName}` : ''}
                  </span>
                )}
              </div>
              <h4 className="font-serif text-base font-bold text-white tracking-tight">
                {promo.description}
              </h4>
              {promo.min_order_amount > 0 && (
                <p className="text-xs text-neutral-400">
                  Minimum qualifying order: {promo.currency} {promo.min_order_amount}
                </p>
              )}
            </div>

            {promo.expires_at && (
              <div className="shrink-0 text-left sm:text-right">
                <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-400 block">
                  Valid Through
                </span>
                <span className="text-xs font-semibold text-brand-lilac">
                  {new Date(promo.expires_at).toLocaleDateString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
