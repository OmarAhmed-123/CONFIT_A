import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { useTryOnViewModel } from '../../viewmodels/useTryOnViewModel';
import { RulerIcon, BagIcon } from '../icons/ConfitIcons';
import { useCartStore } from '../../stores/cartStore';
import { catalogService } from '../../services/apiServices';
import { CameraScanModal } from './CameraScanModal';
import { useModalFocus } from '../../hooks/useModalFocus';
import type { ProductSKU } from '../../models';

const MODAL_SHAPES = [
  { value: 'Athletic', labelKey: 'fit_finder.shape_athletic' },
  { value: 'Hourglass', labelKey: 'fit_finder.shape_hourglass' },
  { value: 'Rectangle', labelKey: 'fit_finder.shape_rectangle' },
  { value: 'Pear', labelKey: 'fit_finder.shape_pear' },
  { value: 'Inverted Triangle', labelKey: 'fit_finder.shape_inverted_triangle' },
] as const;

const MODAL_FITS = [
  { value: 'slim', labelKey: 'no_photo_fit.fit_slim' },
  { value: 'regular', labelKey: 'no_photo_fit.fit_regular' },
  { value: 'relaxed', labelKey: 'no_photo_fit.fit_relaxed' },
] as const;

export function resolveRecommendedInStockSku(
  skus: ProductSKU[] | undefined,
  recommendedSize: string | undefined | null,
): ProductSKU | null {
  if (!skus?.length || !recommendedSize) return null;
  const target = recommendedSize.trim().toUpperCase();
  const matching = skus.filter((s) => s.size.trim().toUpperCase() === target);
  return matching.find((s) => s.is_in_stock !== false && (s.stock_level ?? 0) > 0) ?? null;
}

export const NoPhotoFitModal: React.FC = () => {
  const { t } = useTranslation();
  const { rulerProduct, rulerMeasurements, closeRuler } = useUIStore();
  const { rulerLoading, noPhotoResult, runNoPhotoFit } = useTryOnViewModel(rulerProduct);
  const { addItem, openCart } = useCartStore();

  const [height, setHeight] = useState(178);
  const [weight, setWeight] = useState(72);
  const [shape, setShape] = useState('Athletic');
  const [chest, setChest] = useState(98);
  const [waist, setWaist] = useState(82);
  const [fitPref, setFitPref] = useState('regular');
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);

  const panelRef = useModalFocus<HTMLDivElement>(
    closeRuler,
    !!rulerProduct && !isCameraScanOpen,
  );

  useEffect(() => {
    if (!rulerProduct || !rulerMeasurements) return;
    setHeight(rulerMeasurements.height_cm);
    setWeight(rulerMeasurements.weight_kg);
    setShape(rulerMeasurements.body_shape);
    setChest(rulerMeasurements.chest_cm);
    setWaist(rulerMeasurements.waist_cm);
    void runNoPhotoFit({
      ...rulerMeasurements,
      preferred_fit: 'regular',
    });
  }, [rulerProduct, rulerMeasurements, runNoPhotoFit]);

  useEffect(() => {
    if (!rulerProduct?.id || !noPhotoResult?.recommended || !noPhotoResult?.recommended_size) {
      return;
    }
    void catalogService.recordEngagementEvent({
      event_id: `fit-modal:${rulerProduct.id}:${noPhotoResult.recommended_size}`,
      product_id: rulerProduct.id,
      event_type: 'fit_recommendation',
      attribution_source: 'no_photo_fit_modal',
      recommended_size: noPhotoResult.recommended_size,
      confidence_band: noPhotoResult.confidence_band ?? undefined,
    });
  }, [rulerProduct?.id, noPhotoResult?.recommended, noPhotoResult?.recommended_size]);

  if (!rulerProduct) return null;

  const handleCalculate = (customData?: any) => {
    runNoPhotoFit({
      height_cm: customData?.height_cm || height,
      weight_kg: customData?.weight_kg || weight,
      body_shape: customData?.body_shape || shape,
      chest_cm: customData?.chest_cm || chest,
      waist_cm: customData?.waist_cm || waist,
      preferred_fit: fitPref,
    });
  };

  const handleApplyFromScan = (scanData: any) => {
    setHeight(scanData.height_cm);
    setWeight(scanData.weight_kg);
    setShape(scanData.body_shape);
    setChest(scanData.chest_cm);
    setWaist(scanData.waist_cm);
    handleCalculate(scanData);
  };

  const matchedSku = resolveRecommendedInStockSku(
    rulerProduct.skus,
    noPhotoResult?.recommended_size,
  );

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md confit-fade-in"
        onClick={(e) => {
          if (e.target === e.currentTarget) closeRuler();
        }}
      >
        <div
          ref={panelRef}
          tabIndex={-1}
          className="w-full max-w-3xl bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col focus:outline-none"
          role="dialog"
          aria-modal="true"
          aria-labelledby="no-photo-fit-title"
        >
          {/* Modal Header */}
          <div className="p-4 sm:p-6 border-b border-slate-100 bg-brand-wash flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div
                aria-hidden="true"
                className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-brand-charcoal shrink-0"
              >
                <RulerIcon size={22} color="#242526" />
              </div>
              <div className="min-w-0">
                <h2 id="no-photo-fit-title" className="font-serif text-lg font-bold text-brand-charcoal">
                  {t('tryon.ruler_mode')}
                </h2>
                <p className="text-xs text-slate-600 font-light truncate">
                  {t('tryon.ruler_privacy_subtitle', { title: rulerProduct.title })}
                </p>
              </div>
            </div>
            <button data-motion="neutral" data-motion-tone="icon"
              type="button"
              onClick={closeRuler}
              aria-label={t('no_photo_fit.close_modal')}
              className="min-h-11 min-w-11 rounded-full bg-slate-100 text-slate-600 hover:text-slate-900 flex items-center justify-center transition-colors shrink-0"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>

          {/* Modal Body */}
          <div className="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left Inputs */}
            <div className="space-y-4">
              <div className="flex justify-between items-center gap-3 bg-brand-wash p-3 rounded-2xl border border-brand-hairline/30">
                <div className="text-xs">
                  <div className="font-bold text-brand-charcoal">{t('tryon.nophoto_scan')}</div>
                  <div className="text-[11px] text-slate-600 font-light">{t('fit_finder.camera_estimate_note')}</div>
                </div>
                <button data-motion="upload"
                  type="button"
                  onClick={() => setIsCameraScanOpen(true)}
                  className="min-h-11 px-3.5 py-2 rounded-xl bg-brand-charcoal hover:bg-black text-white text-xs font-bold shadow-sm shrink-0"
                >
                  {t('no_photo_fit.open_camera')}
                </button>
              </div>

              <div>
                <label
                  htmlFor="no-photo-height-range"
                  className="flex justify-between text-xs font-bold text-slate-800 mb-1"
                >
                  <span>{t('no_photo_fit.height_display', { value: height })}</span>
                  <span className="text-slate-500 font-light" dir="ltr">
                    ({Math.floor(height / 30.48)}&apos; {Math.round((height % 30.48) / 2.54)}&quot;)
                  </span>
                </label>
                <input
                  id="no-photo-height-range"
                  type="range"
                  min="140"
                  max="210"
                  value={height}
                  aria-label={t('no_photo_fit.height_aria')}
                  aria-valuetext={t('no_photo_fit.height_valuetext', { value: height })}
                  onChange={(e) => setHeight(Number(e.target.value))}
                  className="w-full min-h-11 accent-brand-charcoal cursor-pointer"
                />
              </div>

              <div>
                <label
                  htmlFor="no-photo-weight-range"
                  className="flex justify-between text-xs font-bold text-slate-800 mb-1"
                >
                  <span>{t('no_photo_fit.weight_display', { value: weight })}</span>
                  <span className="text-slate-500 font-light">
                    {t('no_photo_fit.weight_secondary', { lbs: Math.round(weight * 2.204) })}
                  </span>
                </label>
                <input
                  id="no-photo-weight-range"
                  type="range"
                  min="40"
                  max="140"
                  value={weight}
                  aria-label={t('no_photo_fit.weight_aria')}
                  aria-valuetext={t('no_photo_fit.weight_valuetext', { value: weight })}
                  onChange={(e) => setWeight(Number(e.target.value))}
                  className="w-full min-h-11 accent-brand-charcoal cursor-pointer"
                />
              </div>

              <div>
                <span className="text-xs font-bold text-slate-800 block mb-1.5">{t('fit_finder.body_silhouette')}</span>
                <div
                  role="group"
                  aria-label={t('fit_finder.body_silhouette')}
                  className="grid grid-cols-3 gap-1.5"
                >
                  {MODAL_SHAPES.map((s) => (
                    <button data-motion="creative" data-motion-tone="icon"
                      type="button"
                      key={s.value}
                      aria-pressed={shape === s.value}
                      onClick={() => setShape(s.value)}
                      className={`min-h-11 py-2 px-1.5 text-center text-xs rounded-xl border transition-all truncate ${
                        shape === s.value
                          ? 'border-brand-charcoal bg-brand-charcoal text-white font-bold'
                          : 'border-slate-200 text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      {t(s.labelKey)}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-xs font-bold text-slate-800 block mb-1.5">{t('fit_finder.preferred_fit_colon')}</span>
                <div
                  role="group"
                  aria-label={t('fit_finder.preferred_fit_colon')}
                  className="grid grid-cols-3 gap-2"
                >
                  {MODAL_FITS.map((f) => (
                    <button data-motion="creative" data-motion-tone="icon"
                      type="button"
                      key={f.value}
                      aria-pressed={fitPref === f.value}
                      onClick={() => setFitPref(f.value)}
                      className={`min-h-11 py-2 px-2 text-center text-xs rounded-xl border transition-all ${
                        fitPref === f.value
                          ? 'border-brand-charcoal bg-brand-charcoal text-white font-bold'
                          : 'border-slate-200 text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      {t(f.labelKey)}
                    </button>
                  ))}
                </div>
              </div>

              <button data-motion="creative" data-motion-tone="icon"
                type="button"
                onClick={() => handleCalculate()}
                disabled={rulerLoading}
                className="w-full min-h-11 py-3.5 rounded-xl bg-brand-charcoal hover:bg-black text-white font-semibold text-xs shadow-md transition-all flex items-center justify-center gap-2"
              >
                {rulerLoading ? t('no_photo_fit.calculating_cta') : t('no_photo_fit.calculate_cta')}
              </button>
            </div>

            {/* Right Verdict Result */}
            <div
              role="region"
              aria-live="polite"
              data-testid="no-photo-fit-result"
              className="bg-brand-wash border border-slate-200/80 rounded-2xl p-5 flex flex-col justify-between"
            >
              {noPhotoResult && !noPhotoResult.recommended ? (
                <div className="space-y-3" role="status">
                  <span className="text-[10px] text-slate-500 font-bold uppercase">{t('tryon.nophoto_no_size')}</span>
                  <p className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-xl p-3 leading-relaxed">
                    {noPhotoResult.confidence_disclosure}
                  </p>
                  {noPhotoResult.missing && noPhotoResult.missing.length > 0 && (
                    <p className="text-[11px] text-slate-700">
                      {t('fit_finder.add_colon')} {noPhotoResult.missing.map((m) => m.replace(/_cm$/, '')).join(', ')}
                    </p>
                  )}
                </div>
              ) : noPhotoResult ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center pb-3 border-b border-slate-200 gap-2">
                    <div>
                      <span className="text-[10px] text-slate-500 font-bold uppercase">{t('tryon.scan_recommended_size')}</span>
                      <div className="text-2xl font-serif font-black text-brand-charcoal">
                        <bdi>{t('fit_finder.size_value', { size: noPhotoResult.recommended_size })}</bdi>
                      </div>
                      <span className="text-[10px] text-slate-600 capitalize">
                        {t('fit_finder.confidence_band', { band: noPhotoResult.confidence_band ?? t('fit_finder.unrated') })}
                        {noPhotoResult.is_estimated ? t('fit_finder.partly_estimated_suffix') : ''}
                      </span>
                    </div>
                    <div className="text-end">
                      <span className="text-xs font-bold text-slate-700 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200 block">
                        {t('fit_finder.return_risk_colon')} {noPhotoResult.return_risk?.label}
                      </span>
                    </div>
                  </div>

                  {noPhotoResult.is_between_sizes && noPhotoResult.alternative_size && (
                    <p className="text-[11px] text-brand-charcoal bg-brand-wash border border-brand-hairline/40 rounded-xl p-2.5">
                      {t('no_photo_fit.between_sizes', { size: noPhotoResult.alternative_size })}
                    </p>
                  )}

                  {/* Fit Breakdown */}
                  <div className="space-y-2">
                    <span className="text-xs font-bold text-slate-800">{t('fit_finder.zone_fit_breakdown')}</span>
                    <div className="bg-white rounded-xl p-3 border border-slate-200 space-y-1.5 text-xs">
                      {Object.entries(noPhotoResult.fit_breakdown).map(([zone, desc]) => (
                        <div key={zone} className="flex justify-between items-center text-slate-700">
                          <span className="capitalize font-semibold text-slate-900">{zone}:</span>
                          <span className="text-slate-600 font-light">{desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {noPhotoResult.confidence_band_reason && (
                    <p className="text-[10px] text-slate-600 leading-relaxed">
                      {noPhotoResult.confidence_band_reason}{' '}
                      <span className="text-slate-500">
                        {t('fit_finder.rule_based_rating')}
                      </span>
                    </p>
                  )}

                  <div className="text-[11px] text-slate-600 font-light bg-white/80 p-2.5 rounded-lg border border-slate-100 space-y-1">
                    <p>{noPhotoResult.brand_sizing_tendency?.summary}</p>
                    <p className="text-[10px]">
                      {t('fit_finder.chart_colon')} {noPhotoResult.size_chart_source?.label}
                      {noPhotoResult.size_chart_source?.updated_at
                        ? ` · ${t('no_photo_fit.source_chart_updated', {
                            date: noPhotoResult.size_chart_source.updated_at,
                          })}`
                        : ''}
                    </p>
                  </div>

                  {matchedSku ? (
                    <button data-motion="commerce"
                      type="button"
                      data-testid="no-photo-add-recommended-btn"
                      onClick={async () => {
                        await addItem(matchedSku.id, {
                          id: rulerProduct.id,
                          title: rulerProduct.title,
                          category: rulerProduct.category_name,
                          color: matchedSku.color || rulerProduct.color_family,
                        });
                        closeRuler();
                        openCart();
                      }}
                      className="w-full min-h-11 py-3.5 rounded-xl bg-brand-charcoal hover:bg-black text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
                    >
                      <BagIcon size={14} color="#FFFFFF" />
                      <span>
                        {t('no_photo_fit.add_recommended_cta', {
                          size: noPhotoResult.recommended_size,
                        })}
                      </span>
                    </button>
                  ) : (
                    <div className="space-y-2">
                      <p
                        role="status"
                        data-testid="no-photo-oos-notice"
                        className="text-xs font-medium text-amber-900 bg-amber-50 border border-amber-200 rounded-xl p-2.5"
                      >
                        {t('no_photo_fit.out_of_stock_notice', {
                          size: noPhotoResult.recommended_size,
                        })}
                      </p>
                      <Link
                        to={`/product/${rulerProduct.slug}?size=${encodeURIComponent(noPhotoResult.recommended_size || '')}`}
                        onClick={closeRuler}
                        data-testid="no-photo-view-product-link"
                        className="w-full min-h-11 py-3 rounded-xl border border-brand-charcoal text-brand-charcoal hover:bg-brand-charcoal hover:text-white font-bold text-xs transition-all flex items-center justify-center"
                      >
                        {t('no_photo_fit.view_on_product_cta', {
                          size: noPhotoResult.recommended_size,
                        })}
                      </Link>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-500">
                  <RulerIcon size={36} color="#242526" />
                  <span className="text-xs font-semibold text-slate-700 mt-3">{t('tryon.nophoto_adjust')}</span>
                  <span className="text-[11px] text-slate-500 font-light mt-1 max-w-xs">
                    {t('fit_finder.cross_reference_note', { brand: rulerProduct.brand_name })}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={handleApplyFromScan}
      />
    </>
  );
};
