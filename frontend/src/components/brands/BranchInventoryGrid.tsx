import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { BranchProductItem, BranchSKUAvailability } from '../../models';

interface BranchInventoryGridProps {
  products: BranchProductItem[];
  branchName: string;
  onReserveClick?: (product: BranchProductItem, sku: BranchSKUAvailability) => void;
}

export const BranchInventoryGrid: React.FC<BranchInventoryGridProps> = ({
  products,
  branchName,
  onReserveClick,
}) => {
  const { t } = useTranslation();
  const [selectedSkus, setSelectedSkus] = useState<Record<number, number>>({});

  const handleSelectSku = (productId: number, skuId: number) => {
    setSelectedSkus((prev) => ({ ...prev, [productId]: skuId }));
  };

  if (!products || products.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-neutral-300 p-10 text-center bg-neutral-50/50">
        <p className="font-serif text-base font-bold text-neutral-800">
          {t('brands.no_inventory_title')}
        </p>
        <p className="text-xs text-neutral-500 mt-1">
          {t('brands.no_inventory_desc', { name: branchName })}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
      {products.map((item) => {
        const activeSkuId = selectedSkus[item.id] || item.branch_skus[0]?.sku_id;
        const activeSku = item.branch_skus.find((s) => s.sku_id === activeSkuId) || item.branch_skus[0];

        return (
          <div
            key={item.id}
            className="flex flex-col rounded-2xl bg-white border border-neutral-200 p-4 shadow-sm hover:border-neutral-400 hover:shadow-md transition-all duration-200"
          >
            {/* Product Image & Badges */}
            <div className="relative aspect-4/5 w-full overflow-hidden rounded-xl bg-neutral-100">
              <img
                src={item.thumbnail_url}
                alt={item.title}
                className="h-full w-full object-cover object-center transition-transform duration-500 hover:scale-105"
                loading="lazy"
              />
              <div className="absolute top-2.5 left-2.5 flex flex-col gap-1">
                {item.discount_percent && (
                  <span className="rounded-md bg-brand-coral px-2 py-0.5 text-[11px] font-bold text-brand-charcoal shadow-xs">
                    -{item.discount_percent}% OFF
                  </span>
                )}
                <span className="rounded-md bg-brand-charcoal/85 backdrop-blur-xs px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                  {item.category_name}
                </span>
              </div>

              {/* Status Pill on top right */}
              <div className="absolute top-2.5 right-2.5">
                {item.branch_availability_status === 'in_stock' ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/90 text-white backdrop-blur-xs px-2.5 py-0.5 text-[10px] font-bold shadow-xs">
                    {t('brands.in_stock_badge', { count: item.branch_total_units })}
                  </span>
                ) : item.branch_availability_status === 'low_stock' ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/90 text-white backdrop-blur-xs px-2.5 py-0.5 text-[10px] font-bold shadow-xs">
                    {t('brands.low_stock_badge', { count: item.branch_total_units })}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-neutral-700/90 text-white backdrop-blur-xs px-2.5 py-0.5 text-[10px] font-bold shadow-xs">
                    {t('brands.sold_out_badge')}
                  </span>
                )}
              </div>
            </div>

            {/* Product Meta */}
            <div className="mt-3.5 flex flex-1 flex-col justify-between space-y-3">
              <div>
                <span className="text-[10px] font-bold tracking-wider uppercase text-brand-muted">
                  {item.brand_name}
                </span>
                <h4 className="font-serif text-sm font-bold text-brand-charcoal line-clamp-1 mt-0.5">
                  <Link to={`/product/${item.slug}`} className="hover:underline">
                    {item.title}
                  </Link>
                </h4>

                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-sm font-bold text-brand-charcoal">
                    {item.currency} {Number(item.base_price).toLocaleString()}
                  </span>
                  {item.compare_at_price && Number(item.compare_at_price) > Number(item.base_price) && (
                    <span className="text-xs text-brand-muted line-through">
                      {item.currency} {Number(item.compare_at_price).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Branch Size Availability Curve */}
              <div className="pt-2 border-t border-neutral-100">
                <div className="flex items-center justify-between text-[11px] mb-1.5">
                  <span className="font-semibold text-neutral-600">{t('brands.branch_stock_by_size')}</span>
                  {activeSku && (
                    <span
                      className={`font-semibold ${
                        activeSku.quantity_available > 2
                          ? 'text-emerald-700'
                          : activeSku.quantity_available > 0
                          ? 'text-amber-700'
                          : 'text-neutral-400'
                      }`}
                    >
                      {activeSku.quantity_available > 0
                        ? t('brands.on_rack', { count: activeSku.quantity_available })
                        : t('brands.out_in_size')}
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {item.branch_skus.map((sku) => {
                    const isSelected = sku.sku_id === activeSku?.sku_id;
                    const isOut = sku.quantity_available <= 0;

                    return (
                      <button data-motion="admin" data-motion-tone="icon"
                        key={sku.sku_id}
                        type="button"
                        onClick={() => handleSelectSku(item.id, sku.sku_id)}
                        disabled={isOut}
                        title={`Size ${sku.size}: ${sku.quantity_available} units available`}
                        className={`h-7 min-w-7 px-2 rounded-lg text-xs font-semibold transition-all ${
                          isSelected
                            ? 'bg-brand-charcoal text-white ring-2 ring-brand-charcoal ring-offset-1'
                            : isOut
                            ? 'bg-neutral-100 text-neutral-300 cursor-not-allowed line-through'
                            : 'bg-neutral-100 text-brand-charcoal hover:bg-neutral-200'
                        }`}
                        aria-label={`Size ${sku.size}, ${sku.quantity_available} available`}
                      >
                        {sku.size}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-2 flex items-center gap-2">
                <Link
                  to={`/product/${item.slug}`}
                  className="flex-1 text-center py-2 px-3 rounded-xl border border-neutral-300 text-xs font-bold text-brand-charcoal hover:bg-neutral-50 transition-colors"
                >
                  {t('brands.view_garment')}
                </Link>

                <button data-motion="admin"
                  type="button"
                  disabled={!activeSku || activeSku.quantity_available <= 0}
                  onClick={() => activeSku && onReserveClick?.(item, activeSku)}
                  className={`py-2 px-3 rounded-xl text-xs font-bold transition-all ${
                    activeSku && activeSku.quantity_available > 0
                      ? 'bg-brand-charcoal text-white hover:bg-brand-charcoal/90'
                      : 'bg-neutral-100 text-neutral-400 cursor-not-allowed'
                  }`}
                >
                  {t('brands.hold_in_store')}
                  <span className="sr-only"> — {item.title}</span>
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
