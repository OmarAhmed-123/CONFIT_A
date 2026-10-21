import React from 'react';
import { useTranslation } from 'react-i18next';
import type { StoreBranchSummary } from '../../models';

interface StoreBranchCardProps {
  branch: StoreBranchSummary;
  isSelected: boolean;
  onSelect: (branchId: number) => void;
  brandName?: string;
}

export const StoreBranchCard: React.FC<StoreBranchCardProps> = ({
  branch,
  isSelected,
  onSelect,
}) => {
  const { t } = useTranslation();

  return (
    /*
     * NOT a button. The card contains three real controls — "Get directions",
     * a tel: link and "View stock" — and a button may not contain other
     * controls (axe: nested-interactive, WCAG 4.1.2). The old markup made the
     * table of focus stops unreadable: Tab landed on the card, then on the
     * links inside it, with no way to tell which level you were on, and
     * aria-pressed on the card announced a pressed state for a control whose
     * only job was to contain the ones that do the work.
     *
     * The click handler stays so a mouse user can still select by clicking
     * anywhere on the card; the keyboard path is the "View stock" button,
     * which performs the same action and is announced as a button.
     */
    <div
      onClick={() => onSelect(branch.id)}
      className={`group relative cursor-pointer rounded-2xl p-5 transition-all duration-200 border text-left ${
        isSelected
          ? 'bg-brand-charcoal text-white border-brand-charcoal shadow-lg ring-2 ring-brand-mint'
          : 'bg-white text-brand-charcoal border-neutral-200 hover:border-neutral-400 hover:shadow-sm'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-serif text-base font-bold tracking-tight">
              {branch.name}
            </h3>
            {branch.distance_km !== null && branch.distance_km !== undefined && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                  isSelected
                    ? 'bg-neutral-800 text-brand-mint border border-brand-mint/40'
                    : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                }`}
              >
                {branch.distance_km} km away
              </span>
            )}
          </div>
          <p className={`text-xs ${isSelected ? 'text-neutral-300' : 'text-neutral-600'}`}>
            {branch.address}, {branch.city}, {branch.country}
          </p>
        </div>

        {/* BOPIS & Operational status badges */}
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
              isSelected
                ? 'bg-neutral-800 text-brand-mint border border-neutral-700'
                : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-brand-mint animate-pulse" />
            {t('brands.open_branch')}
          </span>
          {branch.is_bopis_enabled && (
            <span
              className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md ${
                isSelected ? 'bg-neutral-800 text-brand-lilac' : 'bg-purple-50 text-purple-700 border border-purple-200'
              }`}
            >
              {t('brands.bopis_ready')}
            </span>
          )}
        </div>
      </div>

      {branch.pickup_instructions && (
        <div className={`mt-3 text-xs p-2.5 rounded-xl border ${isSelected ? 'bg-neutral-800/80 border-neutral-700 text-neutral-300' : 'bg-neutral-50 border-neutral-200/80 text-neutral-600'}`}>
          <span className="font-semibold block mb-0.5 text-[11px] uppercase tracking-wider text-neutral-400">
            {t('brands.pickup_instructions')}
          </span>
          {branch.pickup_instructions}
        </div>
      )}

      {/* Promos tag */}
      {branch.active_promotions && branch.active_promotions.length > 0 && (
        <div className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-brand-coral">
          <span className="h-2 w-2 rounded-full bg-brand-coral shrink-0" />
          <span>
            {branch.active_promotions.length === 1
              ? t('brands.active_promotions_count', { count: branch.active_promotions.length })
              : t('brands.active_promotions_count_plural', { count: branch.active_promotions.length })}
          </span>
        </div>
      )}

      {/* Action Utility Bar */}
      <div className={`mt-4 pt-3 flex items-center gap-2 border-t ${isSelected ? 'border-neutral-800' : 'border-neutral-100'}`}>
        <a
          href={branch.google_maps_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl text-xs font-bold transition-colors ${
            isSelected
              ? 'bg-white text-brand-charcoal hover:bg-neutral-100'
              : 'bg-brand-coral text-white hover:bg-brand-coral/90'
          }`}
          aria-label={`Open Google Maps directions for ${branch.name}`}
        >
          <svg className="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
          </svg>
          {t('brands.get_directions')}
        </a>

        {branch.phone && (
          <a
            href={`tel:${branch.phone.replace(/[\s\-\(\)]/g, '')}`}
            onClick={(e) => e.stopPropagation()}
            className={`inline-flex items-center justify-center px-3 py-2 rounded-xl border text-xs font-semibold transition-colors ${
              isSelected
                ? 'border-neutral-700 text-neutral-200 hover:bg-neutral-800'
                : 'border-neutral-200 text-neutral-700 hover:bg-neutral-50'
            }`}
            aria-label={`Call branch at ${branch.phone}`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
          </a>
        )}

        <button data-motion="admin" data-motion-tone="icon"
          type="button"
          onClick={() => onSelect(branch.id)}
          className={`px-3 py-2 rounded-xl text-xs font-semibold border transition-colors ${
            isSelected
              ? 'border-brand-mint text-brand-mint bg-neutral-800'
              : 'border-neutral-200 text-neutral-700 hover:bg-neutral-50'
          }`}
        >
          {isSelected ? t('brands.viewing_stock') : t('brands.view_stock')}
        </button>
      </div>
    </div>
  );
};
