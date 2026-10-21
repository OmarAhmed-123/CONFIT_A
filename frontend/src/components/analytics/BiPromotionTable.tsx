import React from 'react';
import { useTranslation } from 'react-i18next';
import type { BiPromotionItem } from '../../models';

interface BiPromotionTableProps {
  promotions: BiPromotionItem[];
  currency?: string;
}

export const BiPromotionTable: React.FC<BiPromotionTableProps> = ({
  promotions,
  currency = 'USD',
}) => {
  const { t } = useTranslation();

  if (!promotions || promotions.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-4">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="font-serif text-lg font-bold text-brand-charcoal">
          {t('bi.promotions_performance', 'Promotions & Campaign Performance')}
        </h2>
        <p className="text-[11px] text-slate-500">
          {t('bi.promotions_desc', 'Recorded promo code redemption counts, total discount apportionments, and attributable customer order volume')}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
              <th className="py-2.5">{t('bi.promo_code', 'Code')}</th>
              <th className="py-2.5">{t('bi.discount_rule', 'Discount Rule')}</th>
              <th className="py-2.5 text-center">{t('bi.status', 'Status')}</th>
              <th className="py-2.5 text-right">{t('bi.redemptions', 'Redemptions')}</th>
              <th className="py-2.5 text-right">{t('bi.discounts_granted', 'Discounts Granted')}</th>
              <th className="py-2.5 text-right">{t('bi.revenue_generated', 'Revenue Generated')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {promotions.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50">
                <td className="py-2.5 font-mono font-bold text-brand-charcoal text-xs">
                  {p.code}
                </td>
                <td className="py-2.5 text-slate-600">
                  {p.discount_type === 'percent' ? `${p.discount_value}% off` : `$${p.discount_value} off`}
                  {p.description ? ` · ${p.description}` : ''}
                </td>
                <td className="py-2.5 text-center">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      p.is_expired
                        ? 'bg-slate-100 text-slate-600 border border-slate-200'
                        : p.is_active
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}
                  >
                    {p.is_expired ? 'Expired' : p.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="py-2.5 text-right font-mono font-bold text-slate-800">
                  {p.redemptions}
                </td>
                <td className="py-2.5 text-right font-mono text-brand-coral font-medium">
                  {currency} {p.total_discount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
                <td className="py-2.5 text-right font-mono font-bold text-brand-charcoal">
                  {currency} {p.revenue_generated.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
