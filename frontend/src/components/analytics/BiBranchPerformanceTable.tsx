import React from 'react';
import { useTranslation } from 'react-i18next';
import type { BiBranchItem } from '../../models';

interface BiBranchPerformanceTableProps {
  branches: BiBranchItem[];
  currency?: string;
  selectedBranchId?: number | null;
  onSelectBranch?: (branchId: number | null) => void;
}

export const BiBranchPerformanceTable: React.FC<BiBranchPerformanceTableProps> = ({
  branches,
  currency = 'USD',
  selectedBranchId,
  onSelectBranch,
}) => {
  const { t, i18n } = useTranslation();
  const isArabic = i18n.language === 'ar';

  if (!branches || branches.length === 0) {
    return (
      <div className="p-6 bg-white border border-slate-200 rounded-3xl text-xs text-slate-500 text-center">
        {t('bi.no_branches', 'No physical branch locations recorded for this brand.')}
      </div>
    );
  }

  const maxBranchSales = Math.max(1, ...branches.map((b) => b.gross_sales));

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div>
          <h2 className="font-serif text-lg font-bold text-brand-charcoal">
            {t('bi.branch_performance', 'Branch & Omnichannel Performance')}
          </h2>
          <p className="text-[11px] text-slate-500">
            {t('bi.branch_desc', 'Location-specific sales, completed BOPIS pickup orders, and live on-hand boutique inventory')}
          </p>
        </div>
        {selectedBranchId && onSelectBranch && (
          <button data-motion="neutral" data-motion-tone="icon"
            type="button"
            onClick={() => onSelectBranch(null)}
            className="text-[11px] font-bold text-brand-coral hover:underline"
          >
            {t('bi.clear_branch_filter', 'Show All Branches')}
          </button>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
              <th className="py-2.5">{t('bi.branch', 'Branch')}</th>
              <th className="py-2.5">{t('bi.city', 'City')}</th>
              <th className="py-2.5 text-right">{t('bi.bopis_orders', 'BOPIS Orders')}</th>
              <th className="py-2.5 text-right">{t('bi.units_sold', 'Units Sold')}</th>
              <th className="py-2.5 text-right">{t('bi.gross_sales', 'Gross Sales')}</th>
              <th className="py-2.5 text-right">{t('bi.available_stock', 'Available Stock')}</th>
              <th className="py-2.5 text-center">{t('bi.stock_status', 'Stock Alert')}</th>
              <th className="py-2.5 text-center">{t('bi.action', 'Action')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {branches.map((b) => {
              const isSelected = selectedBranchId === b.store_id;
              const name = isArabic && b.name_ar ? b.name_ar : b.name;
              return (
                <tr
                  key={b.store_id}
                  className={`hover:bg-slate-50 transition-colors ${
                    isSelected ? 'bg-slate-50 font-semibold' : ''
                  }`}
                >
                  <td className="py-3 font-bold text-brand-charcoal">
                    <div className="truncate max-w-[180px]">{name}</div>
                    <div className="text-[10px] text-brand-muted font-normal truncate max-w-[180px]">
                      {b.address}
                    </div>
                  </td>
                  <td className="py-3 text-slate-600 font-medium">{b.city}</td>
                  <td className="py-3 text-right font-mono font-bold text-slate-700">{b.orders_count}</td>
                  <td className="py-3 text-right font-mono text-slate-600">{b.units_sold}</td>
                  <td className="py-3 text-right font-mono font-bold text-brand-charcoal">
                    {currency} {b.gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 text-right font-mono font-medium text-emerald-700">
                    {b.available_stock.toLocaleString()} units
                  </td>
                  <td className="py-3 text-center">
                    {b.low_stock_skus > 0 ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                        {b.low_stock_skus} low
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                        Healthy
                      </span>
                    )}
                  </td>
                  <td className="py-3 text-center">
                    {onSelectBranch && (
                      <button data-motion="filter" data-motion-tone="icon"
                        type="button"
                        onClick={() => onSelectBranch(isSelected ? null : b.store_id)}
                        className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all ${
                          isSelected
                            ? 'bg-brand-charcoal text-white'
                            : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        {isSelected ? t('bi.selected', 'Selected') : t('bi.filter', 'Filter')}
                      </button>
                    )}
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
