import React from 'react';
import { useTranslation } from 'react-i18next';
import type { BiInventoryHealth } from '../../models';

interface BiInventoryHealthCardProps {
  inventory: BiInventoryHealth;
}

export const BiInventoryHealthCard: React.FC<BiInventoryHealthCardProps> = ({ inventory }) => {
  const { t } = useTranslation();

  if (!inventory) return null;

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-6">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="font-serif text-lg font-bold text-brand-charcoal">
          {t('bi.inventory_health', 'Merchandise Inventory Health & Stock Pools')}
        </h2>
        <p className="text-[11px] text-slate-500">
          {t('bi.inventory_desc', 'Authoritative stock levels separated by central warehouse sellable units and branch boutique BOPIS pools')}
        </p>
      </div>

      {/* Stock Pool Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500 font-bold">
            {t('bi.warehouse_stock', 'Warehouse Stock')}
          </span>
          <span className="font-mono text-xl font-bold text-brand-charcoal mt-1 block">
            {inventory.total_warehouse_units.toLocaleString()}
          </span>
          <span className="text-[10px] text-brand-muted mt-0.5 block">
            {t('bi.warehouse_stock_desc', 'Central sellable units')}
          </span>
        </div>

        <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500 font-bold">
            {t('bi.bopis_stock', 'Branch BOPIS Stock')}
          </span>
          <span className="font-mono text-xl font-bold text-brand-charcoal mt-1 block">
            {inventory.total_branch_bopis_units.toLocaleString()}
          </span>
          <span className="text-[10px] text-brand-muted mt-0.5 block">
            {t('bi.bopis_stock_desc', 'In-store pickup pool')}
          </span>
        </div>

        <div className="p-4 rounded-2xl bg-amber-50/60 border border-amber-200">
          <span className="block text-[10px] uppercase text-amber-800 font-bold">
            {t('bi.low_stock', 'Low Stock SKUs (≤ 5)')}
          </span>
          <span className="font-mono text-xl font-bold text-amber-700 mt-1 block">
            {inventory.low_stock_count}
          </span>
          <span className="text-[10px] text-amber-700 mt-0.5 block">
            {t('bi.low_stock_desc', 'Requires replenishment')}
          </span>
        </div>

        <div className="p-4 rounded-2xl bg-rose-50/60 border border-rose-200">
          <span className="block text-[10px] uppercase text-rose-800 font-bold">
            {t('bi.out_of_stock_skus')}
          </span>
          <span className="font-mono text-xl font-bold text-rose-700 mt-1 block">
            {inventory.out_of_stock_count}
          </span>
          <span className="text-[10px] text-rose-700 mt-0.5 block">
            {t('bi.out_of_stock_desc', 'Urgent reorder required')}
          </span>
        </div>
      </div>

      {/* Replenishment Action Items */}
      {inventory.replenishment_items && inventory.replenishment_items.length > 0 && (
        <div className="space-y-3 pt-2">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
            {t('bi.replenishment_alerts', 'Actionable Replenishment Alerts')}
          </h4>
          <div className="overflow-x-auto max-h-60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
                  <th className="py-2">{t('bi.product', 'Product')}</th>
                  <th className="py-2">{t('bi.sku', 'SKU')}</th>
                  <th className="py-2">{t('bi.variant', 'Size / Color')}</th>
                  <th className="py-2 text-right">{t('bi.current_stock', 'Current Stock')}</th>
                  <th className="py-2 text-center">{t('bi.status', 'Status')}</th>
                  <th className="py-2 text-right">{t('bi.suggested_reorder', 'Suggested Reorder')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {inventory.replenishment_items.map((item) => (
                  <tr key={item.sku_id} className="hover:bg-slate-50">
                    <td className="py-2 font-bold text-brand-charcoal truncate max-w-[160px]">
                      {item.product_title}
                    </td>
                    <td className="py-2 font-mono text-slate-600 text-[11px]">{item.sku_code}</td>
                    <td className="py-2 text-slate-600">
                      {item.size} · {item.color}
                    </td>
                    <td className="py-2 text-right font-mono font-bold text-slate-800">
                      {item.stock_level}
                    </td>
                    <td className="py-2 text-center">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          item.status === 'out_of_stock'
                            ? 'bg-rose-100 text-rose-800 border border-rose-200'
                            : 'bg-amber-100 text-amber-800 border border-amber-200'
                        }`}
                      >
                        {item.status === 'out_of_stock'
                          ? t('bi.status_out_of_stock')
                          : t('bi.status_low_stock')}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      {typeof item.recommended_reorder === 'number' ? (
                        <>
                          <span className="font-mono font-bold text-brand-coral">
                            {t('bi.reorder_units', { count: item.recommended_reorder })}
                          </span>
                          {/*
                            The number is a rule of thumb (20 when out of stock,
                            otherwise 15 - stock). It has no demand history,
                            lead time or safety stock behind it, so it is
                            labelled as an estimate rather than shown as though
                            the system had calculated a reorder point.
                          */}
                          <span
                            className="block text-[9px] text-brand-muted"
                            title={t('bi.reorder_estimate_hint')}
                          >
                            {t('bi.reorder_estimate')}
                          </span>
                        </>
                      ) : (
                        <span className="text-[10px] text-brand-muted">
                          {t('bi.reorder_unavailable')}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
