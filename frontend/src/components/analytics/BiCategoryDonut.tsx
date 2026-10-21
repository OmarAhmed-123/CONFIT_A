import React from 'react';
import { useTranslation } from 'react-i18next';
import type { BiCategoryItem } from '../../models';

interface BiCategoryDonutProps {
  categories: BiCategoryItem[];
  currency?: string;
  onSelectCategory?: (categoryId: number | null) => void;
  selectedCategoryId?: number | null;
}

export const BiCategoryDonut: React.FC<BiCategoryDonutProps> = ({
  categories,
  currency = 'USD',
  onSelectCategory,
  selectedCategoryId,
}) => {
  const { t, i18n } = useTranslation();
  const isArabic = i18n.language === 'ar';

  if (!categories || categories.length === 0) {
    return (
      <div className="p-6 bg-white border border-slate-200 rounded-3xl text-xs text-slate-500 text-center">
        {t('bi.no_category_data', 'No category sales recorded for this period.')}
      </div>
    );
  }

  const categoryColors = [
    'bg-brand-coral',
    'bg-brand-lilac',
    'bg-brand-mint',
    'bg-brand-charcoal',
    'bg-amber-500',
    'bg-sky-500',
  ];

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h2 className="font-serif text-lg font-bold text-brand-charcoal">
            {t('bi.category_breakdown', 'Category Sales Share')}
          </h2>
          <p className="text-[11px] text-slate-500">
            {t('bi.category_desc', 'Revenue contribution and units sold across merchandise departments')}
          </p>
        </div>
      </div>

      {/* Stacked Proportional Bar */}
      <div className="space-y-1.5">
        <div className="w-full h-3 rounded-full bg-slate-100 flex overflow-hidden">
          {categories.map((c, i) => (
            <div
              key={c.category_id}
              style={{ width: `${c.share_pct}%` }}
              className={`h-full transition-all ${categoryColors[i % categoryColors.length]}`}
              title={`${isArabic && c.category_name_ar ? c.category_name_ar : c.category_name}: ${c.share_pct}%`}
            />
          ))}
        </div>
      </div>

      {/* Category Breakdown Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
              <th className="py-2">{t('bi.category', 'Category')}</th>
              <th className="py-2 text-right">{t('bi.units', 'Units')}</th>
              <th className="py-2 text-right">{t('bi.gross_sales', 'Gross Sales')}</th>
              <th className="py-2 text-right">{t('bi.share', 'Share')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {categories.map((cat, idx) => {
              const isSelected = selectedCategoryId === cat.category_id;
              const name = isArabic && cat.category_name_ar ? cat.category_name_ar : cat.category_name;
              return (
                <tr
                  key={cat.category_id}
                  onClick={() => onSelectCategory && onSelectCategory(isSelected ? null : cat.category_id)}
                  className={`hover:bg-slate-50 transition-colors cursor-pointer ${
                    isSelected ? 'bg-slate-50 font-semibold' : ''
                  }`}
                >
                  <td className="py-2.5 flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full inline-block shrink-0 ${
                        categoryColors[idx % categoryColors.length]
                      }`}
                    />
                    <span className="truncate max-w-[140px] text-brand-charcoal">{name}</span>
                  </td>
                  <td className="py-2.5 text-right font-mono text-slate-600">{cat.units_sold}</td>
                  <td className="py-2.5 text-right font-mono font-medium text-brand-charcoal">
                    {currency} {cat.gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-2.5 text-right font-mono font-bold text-slate-800">
                    {cat.share_pct}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
