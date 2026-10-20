import React from 'react';
import { useTranslation } from 'react-i18next';
import type { CustomerBrand } from '../../models';

interface BrandCardProps {
  brand: CustomerBrand;
  onSelect: (brandSlug: string) => void;
}

export const BrandCard: React.FC<BrandCardProps> = ({ brand, onSelect }) => {
  const { t } = useTranslation();

  /*
   * LOGO FAILURE IS A FIRST-CLASS STATE.
   *
   * `logo_url` is a third-party URL (the live catalogue serves Unsplash for all
   * four brands), so it can 404, be rate-limited, or be blocked by an image
   * proxy. The card previously rendered a bare <img> with no handler: a failed
   * logo produced the browser's broken-image glyph inside a 56px tile, which
   * reads as a bug in the shop rather than a missing asset. Falling back to the
   * monogram we already render when no logo exists is honest — it asserts the
   * initials and nothing more.
   *
   * Reset on `logo_url` change so a card that fails for brand A does not show
   * brand B's initials after a re-render in a list.
   */
  const [logoFailed, setLogoFailed] = React.useState(false);
  React.useEffect(() => {
    setLogoFailed(false);
  }, [brand.logo_url]);

  const showLogo = Boolean(brand.logo_url) && !logoFailed;

  return (
    <div
      onClick={() => onSelect(brand.slug)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(brand.slug);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`Explore brand ${brand.brand_name}`}
      className="group relative cursor-pointer rounded-2xl bg-white p-6 border border-neutral-200 shadow-sm transition-all duration-300 hover:border-brand-charcoal hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-charcoal flex flex-col justify-between"
    >
      <div>
        {/* Brand Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5">
            {showLogo ? (
              /*
               * DECORATIVE, AND DELIBERATELY NOT CAPTIONED AS A LOGO.
               *
               * `logo_url` is a free-text column: nothing in the schema proves
               * the file is an official brand mark, and measured on 2026-10-20
               * all four live values are Unsplash photographs (a flat-lay, a
               * clothes rack, a shop window, a shop interior). Rendering them
               * with alt="<Brand> logo" asserted a trademark the asset is not.
               *
               * Until the owners supply approved marks, the honest options are
               * "no claim" or "a fabricated logo", and fabricating a trademark
               * is not an option. The brand name is already an <h3> beside this
               * tile, so the image carries an empty alt and is hidden from the
               * accessibility tree: a screen reader hears the brand once, and
               * no caption says "logo".
               */
              <img
                src={brand.logo_url as string}
                alt=""
                aria-hidden="true"
                data-testid="brand-logo"
                onError={() => setLogoFailed(true)}
                className="h-14 w-14 rounded-xl object-cover border border-neutral-100 shadow-xs"
              />
            ) : (
              <div
                data-testid="brand-monogram"
                aria-hidden="true"
                className="h-14 w-14 rounded-xl bg-neutral-100 border border-neutral-200 flex items-center justify-center font-serif font-bold text-lg text-brand-charcoal"
              >
                {brand.brand_name.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-serif text-lg font-bold text-brand-charcoal group-hover:text-black">
                  {brand.brand_name}
                </h3>
                {brand.is_verified && (
                  <span
                    className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"
                    title={t('brands.verified_brand_house')}
                  >
                    {t('brands.verified_partner')}
                  </span>
                )}
              </div>
              {/*
                Only a description the brand actually supplied. The previous
                fallback asserted "Curated European fashion house" for every
                brand that had not written one — a fabricated claim about a
                company, rendered in the same type as real copy. An absent
                description now renders nothing.
              */}
              {brand.description ? (
                <p className="text-xs text-neutral-500 line-clamp-1 mt-0.5">
                  {brand.description}
                </p>
              ) : null}
            </div>
          </div>

          <span className="shrink-0 rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-semibold text-brand-charcoal">
            {brand.stores_count} {brand.stores_count === 1 ? 'Store' : 'Stores'}
          </span>
        </div>

        {/* Promotion Highlight Ribbon */}
        {brand.promotions && brand.promotions.length > 0 && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-purple-50 px-3 py-2 text-xs font-semibold text-purple-900 border border-purple-200/80">
            <span className="h-2 w-2 rounded-full bg-brand-lilac animate-pulse" />
            <span className="line-clamp-1">
              {brand.promotions[0].discount_type === 'percent'
                ? `${brand.promotions[0].discount_value}% OFF`
                : `${brand.promotions[0].currency} ${brand.promotions[0].discount_value} OFF`}
              : {brand.promotions[0].description}
            </span>
          </div>
        )}

        {/* Categories & Cities Pills */}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {brand.categories.slice(0, 3).map((cat) => (
            <span
              key={cat}
              className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-700"
            >
              {cat}
            </span>
          ))}
          {brand.cities.slice(0, 2).map((city) => (
            <span
              key={city}
              className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-100"
            >
              {city}
            </span>
          ))}
        </div>
      </div>

      {/* Footer Explore Action */}
      <div className="mt-6 pt-3 border-t border-neutral-100 flex items-center justify-between text-xs font-bold text-brand-charcoal">
        <span className="text-neutral-500 font-normal">
          {t('brands.available_items', { count: brand.total_products })}
        </span>
        <span className="group-hover:translate-x-1 transition-transform inline-flex items-center gap-1 text-brand-coral">
          {t('brands.explore_stores_catalog')}
        </span>
      </div>
    </div>
  );
};
