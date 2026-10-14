import { useTranslation } from 'react-i18next';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { RefreshCw, CheckCircle2, Circle } from 'lucide-react';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { Surface } from '../../components/common/Surface';
import { HonestProductImage } from '../../components/common/HonestProductImage';
import { usePrefersReducedMotion } from '../../components/common/InteractionPrimitives';
import { brandService } from '../../services/apiServices';
import type { BrandOnboardingStatus } from '../../models';

/**
 * B02 — Partner Command Center, re-pass (see docs/B02_PARTNER_DASHBOARD_REDESIGN.md).
 *
 * The previous build rendered a wall of hard-coded English, shipped database
 * table names as user copy, repeated "Real Data" self-praise chips, and painted
 * slate-400/gold text on white (2.56:1 / 2.85:1 — both fail WCAG 2.2 AA). This
 * pass rebuilds the same REAL data on the B01 register: token surfaces, hairline
 * ledger, human source notes, geometry-tailored shimmer, per-source failure
 * states, and full EN/AR i18n (the eight baseline debt entries for this file are
 * deleted).
 *
 * Honesty contract (backend/app/schemas/brand.py): every Optional rate renders
 * the translated "Not enough data" when null — never a substituted 0%. The
 * backend `methodology` string is shown verbatim as the single methodology
 * footnote; that is the honest surface, and it replaces the "(Real)" chips.
 */

export const BrandDashboardView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const { profile, analytics, fetchErrors, isLoading, loadFailed, refresh } =
    useBrandViewModel();

  const [onboarding, setOnboarding] = useState<BrandOnboardingStatus | null>(null);

  useEffect(() => {
    let isMounted = true;
    brandService.getOnboardingStatus()
      .then((data) => {
        if (isMounted) setOnboarding(data);
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  const [stamp, setStamp] = useState<string | null>(null);
  useEffect(() => {
    if (!isLoading && analytics) {
      setStamp(
        new Intl.DateTimeFormat(i18n.language, { hour: '2-digit', minute: '2-digit' }).format(
          new Date(),
        ),
      );
    }
  }, [isLoading, analytics, i18n.language]);

  const percent = (value: number | null | undefined) =>
    value == null ? t('b2b.dash.not_enough_data') : `${value}%`;

  /* ---------------------------------------------------------------- loading */
  if (isLoading) {
    return (
      <div className="space-y-8 pb-20" role="status" aria-live="polite">
        <span className="sr-only">{t('b2b.dash.loading')}</span>
        {/* masthead geometry */}
        <div className="grid grid-cols-12 gap-8" aria-hidden="true">
          <div className="col-span-12 lg:col-span-7 space-y-4 py-2">
            <div className="h-3 w-40 animate-pulse rounded bg-slate-200" />
            <div className="skeleton-shimmer h-12 w-4/5 rounded-xl bg-slate-100" />
            <div className="skeleton-shimmer h-12 w-3/5 rounded-xl bg-slate-100" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
          </div>
          <div className="col-span-12 lg:col-span-5 skeleton-shimmer h-40 rounded-2xl bg-slate-100" />
        </div>
        {/* ledger geometry */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="space-y-3 p-5">
              <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
              <div className="skeleton-shimmer h-9 w-20 rounded-lg bg-slate-100" />
              <div className="h-3 w-28 animate-pulse rounded bg-slate-200" />
            </div>
          ))}
        </div>
        {/* panels geometry */}
        <div className="grid grid-cols-12 gap-8" aria-hidden="true">
          <div className="col-span-12 lg:col-span-7 skeleton-shimmer h-64 rounded-2xl bg-slate-100" />
          <div className="col-span-12 lg:col-span-5 skeleton-shimmer h-64 rounded-2xl bg-slate-100" />
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------- terminal failure */
  if (loadFailed) {
    return (
      <Surface variant="solid" className="rounded-2xl border-rose-300 p-8 text-center" role="alert">
        <h1 className="font-serif text-xl font-bold text-brand-charcoal">
          {t('b2b.dash.loadfailed_title')}
        </h1>
        <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-slate-600">
          {fetchErrors.analytics ?? t('b2b.dash.unavailable_body')}
        </p>
        <button
          type="button"
          onClick={refresh}
          className="mt-5 inline-flex min-h-12 items-center gap-2 rounded-xl bg-brand-charcoal px-6 text-xs font-semibold text-white transition-colors duration-300 ease-luxury hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
        >
          {t('common.retry')}
        </button>
      </Surface>
    );
  }

  /* ------------------------------------------------- single-source failure */
  if (!analytics) {
    return (
      <Surface variant="solid" className="rounded-2xl border-rose-300 p-8 text-center" role="alert">
        <h1 className="font-serif text-xl font-bold text-brand-charcoal">
          {t('b2b.dash.unavailable_title')}
        </h1>
        <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-slate-600">
          {fetchErrors.analytics || t('b2b.dash.unavailable_body')}
        </p>
        <button
          type="button"
          onClick={refresh}
          className="mt-5 inline-flex min-h-12 items-center gap-2 rounded-xl bg-brand-charcoal px-6 text-xs font-semibold text-white transition-colors duration-300 ease-luxury hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
        >
          {t('common.retry')}
        </button>
      </Surface>
    );
  }

  const hasData = analytics.total_views > 0 || analytics.total_purchases > 0;
  const sessionsPerView =
    analytics.total_views > 0
      ? `${((analytics.total_tryons / analytics.total_views) * 100).toFixed(1)}%`
      : null;

  const cohortBars = [
    {
      label: t('b2b.dash.cohort_before'),
      rate: analytics.return_rate_before_vton,
      bar: 'bg-brand-coral',
      text: 'text-brand-coral',
    },
    {
      label: t('b2b.dash.cohort_after'),
      rate: analytics.return_rate_after_vton,
      bar: 'bg-brand-mint',
      text: 'text-[#065F46] font-bold',
    },
  ];

  const rankPillStyles = [
    'bg-brand-coral text-white',
    'bg-brand-lilac text-brand-charcoal',
    'bg-brand-mint text-brand-charcoal',
    'bg-brand-charcoal text-white',
  ];

  return (
    <div className="space-y-10 pb-20">
      {/* ----------------------------------------------- 1 · editorial masthead */}
      <header className="grid grid-cols-12 items-start gap-8">
        <div className="col-span-12 lg:col-span-7">
          <div className="flex flex-wrap items-center gap-2">
            <span className="h-px w-8 bg-brand-coral" aria-hidden="true" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-brand-charcoal">
              {t('b2b.dash.eyebrow')}
            </span>
            <span
              className={
                'rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ' +
                (profile?.is_verified
                  ? 'bg-brand-mint/25 text-[#064E3B] border border-brand-mint/50'
                  : 'bg-slate-200 text-slate-700')
              }
            >
              {profile?.is_verified ? t('b2b.dash.verified') : t('b2b.dash.pending')}
            </span>
          </div>
          <h1
            className="mt-3 font-serif font-bold text-brand-charcoal"
            style={{ fontSize: 'clamp(1.75rem, 3.5vw, 2.75rem)', lineHeight: 1.08, letterSpacing: '-0.015em' }}
          >
            {t('b2b.dash.title', { brand: profile?.brand_name || 'Brand' })}
          </h1>
          <p className="mt-3 max-w-xl text-xs leading-relaxed text-slate-600 sm:text-sm">
            {t('b2b.dash.catalog_line', {
              products: analytics.total_products_count.toLocaleString(i18n.language),
              skus: analytics.total_skus_count.toLocaleString(i18n.language),
              commission:
                profile?.commission_rate != null ? `${profile.commission_rate}%` : t('b2b.dash.commission_unavailable'),
              bopis: percent(analytics.bopis_store_fulfillment_rate),
            })}
          </p>
          {fetchErrors.profile && (
            <p className="mt-2 text-[11px] font-medium text-amber-700" role="status">
              {t('b2b.dash.profile_failed')}
            </p>
          )}
        </div>

        <Surface variant="solid" reveal revealDelay={0.06} className="col-span-12 rounded-2xl p-5 lg:col-span-5 bg-white border border-slate-200">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <span className="block text-[11px] font-bold uppercase tracking-widest text-slate-600">
                {t('b2b.dash.methodology')}
              </span>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
                {analytics.methodology}
              </p>
            </div>
            <button
              type="button"
              onClick={refresh}
              className="inline-flex min-h-12 shrink-0 items-center gap-2 rounded-xl border border-slate-300 px-4 text-xs font-semibold text-brand-charcoal transition-colors duration-300 ease-luxury hover:border-brand-coral hover:text-brand-coral focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-coral"
            >
              <RefreshCw size={14} aria-hidden="true" />
              {t('b2b.dash.refresh')}
            </button>
          </div>
          {stamp && (
            <p className="mt-3 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
              {t('b2b.dash.updated', { time: stamp })}
            </p>
          )}
        </Surface>
      </header>

      {/* ----------------------------------------------- 1b · Guided Onboarding & Welcome Hub */}
      {onboarding && (
        <Surface variant="solid" reveal className="rounded-3xl border border-neutral-200 bg-neutral-50/70 p-6 sm:p-8 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-widest text-brand-coral">
                  {t('brand_onboard.title', 'Brand Onboarding & Setup')}
                </span>
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    onboarding.is_verified
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                      : 'bg-amber-50 text-amber-700 border border-amber-200'
                  }`}
                >
                  {onboarding.publication_status === 'active'
                    ? t('brand_onboard.active', 'Active & Published')
                    : onboarding.publication_status === 'pending_review'
                    ? t('brand_onboard.pending', 'Pending Review')
                    : t('brand_onboard.incomplete', 'Setup Incomplete')}
                </span>
              </div>
              <h2 className="font-serif text-lg sm:text-xl font-bold text-brand-charcoal">
                {onboarding.welcome_message}
              </h2>
            </div>

            <Link
              to={onboarding.primary_cta_url}
              className="inline-flex shrink-0 items-center gap-1.5 px-5 py-2.5 rounded-xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 transition-colors shadow-sm self-start sm:self-center"
            >
              {onboarding.primary_cta_label} &rarr;
            </Link>
          </div>

          {/* Progress Bar */}
          <div className="space-y-2 pt-2 border-t border-neutral-200">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-600">
              <span>{t('brand_onboard.checklist_title', { completed: onboarding.completed_steps_count, total: onboarding.total_steps_count, defaultValue: `Setup Checklist (${onboarding.completed_steps_count} of ${onboarding.total_steps_count} completed)` })}</span>
              <span>{onboarding.completion_percentage}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-neutral-200 overflow-hidden">
              <div
                className="h-full bg-brand-coral transition-all duration-500 rounded-full"
                style={{ width: `${onboarding.completion_percentage}%` }}
              />
            </div>
          </div>

          {/* Steps Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 pt-2">
            {onboarding.steps.map((step) => (
              <Link
                key={step.key}
                to={step.action_url}
                className={`p-3.5 rounded-2xl border transition-all flex flex-col justify-between space-y-2 ${
                  step.is_completed
                    ? 'bg-white border-neutral-200 hover:border-neutral-400'
                    : 'bg-white/80 border-dashed border-neutral-300 hover:border-brand-charcoal'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-bold text-brand-charcoal line-clamp-1">
                    {step.title}
                  </span>
                  {step.is_completed ? (
                    <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                  ) : (
                    <Circle size={16} className="text-neutral-300 shrink-0" />
                  )}
                </div>
                <p className="text-[11px] text-neutral-500 line-clamp-2 leading-relaxed">
                  {step.description}
                </p>
                <span className="text-[10px] font-bold text-brand-coral block pt-1">
                  {step.is_completed ? t('brand_onboard.review_step', 'Review Step →') : t('brand_onboard.complete_step', 'Complete Step →')}
                </span>
              </Link>
            ))}
          </div>
        </Surface>
      )}

      {/* ------------------------------------------------- 2 · hairline ledger */}
      <Surface variant="solid" reveal className="grid grid-cols-2 lg:grid-cols-4 bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-xs">
        <div className="space-y-1.5 p-5 border-t-4 border-t-brand-lilac bg-white">
          <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">
            {t('b2b.dash.kpi_views')}
          </span>
          <span className="block font-serif text-2xl font-black text-brand-charcoal">
            {analytics.total_views.toLocaleString(i18n.language)}
          </span>
          <span className="block text-[11px] text-slate-500">{t('b2b.dash.kpi_views_note')}</span>
          {!hasData && (
            <span className="block rounded-lg bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700">
              {t('b2b.dash.kpi_views_empty')}
            </span>
          )}
        </div>
        <div className="space-y-1.5 border-s border-t-4 border-t-brand-coral border-slate-200 p-5 bg-white">
          <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">
            {t('b2b.dash.kpi_tryons')}
          </span>
          <span className="block font-serif text-2xl font-black text-brand-charcoal">
            {analytics.total_tryons.toLocaleString(i18n.language)}
          </span>
          <span className="block text-[11px] text-slate-500">
            {sessionsPerView != null
              ? t('b2b.dash.kpi_tryons_note', { rate: sessionsPerView })
              : t('b2b.dash.kpi_tryons_note_plain')}
          </span>
        </div>
        <div className="space-y-1.5 border-s border-t-4 border-t-brand-charcoal border-slate-200 p-5 bg-white">
          <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">
            {t('b2b.dash.kpi_ratio')}
          </span>
          <span className="block font-serif text-2xl font-black text-brand-charcoal">
            {analytics.funnel_conversion_rate == null ? 'N/A' : `${analytics.funnel_conversion_rate}%`}
          </span>
          <span className="block text-[11px] text-slate-500">
            {analytics.funnel_conversion_rate == null
              ? t('b2b.dash.kpi_ratio_na')
              : t('b2b.dash.kpi_ratio_note')}
          </span>
        </div>
        <div className="space-y-1.5 border-s border-t-4 border-t-brand-mint border-slate-200 p-5 bg-white">
          <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">
            {t('b2b.dash.kpi_return')}
          </span>
          {/* colour only when a real measurement exists — green must mean "good news measured", not "no data" */}
          <span
            className={
              'block font-serif text-2xl font-black ' +
              (analytics.return_rate_after_vton == null
                ? 'text-brand-charcoal'
                : 'text-[#065F46]')
            }
          >
            {percent(analytics.return_rate_after_vton)}
          </span>
          <span className="block text-[11px] text-slate-500">
            {t('b2b.dash.kpi_return_note', { rate: percent(analytics.return_rate_before_vton) })}
          </span>
        </div>
      </Surface>

      {/* ------------------------- 3+4 · cohort bars (7) / most styled (5) */}
      <div className="grid grid-cols-12 gap-8">
        <Surface variant="solid" reveal as="section" className="col-span-12 space-y-6 rounded-2xl p-6 lg:col-span-7 bg-white border border-slate-200 shadow-xs">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 pb-3">
            <div>
              <h2 className="font-serif text-lg font-bold text-brand-charcoal">
                {t('b2b.dash.cohort_title')}
              </h2>
              <p className="mt-0.5 text-[11px] text-slate-500">{t('b2b.dash.cohort_hint')}</p>
            </div>
            <span className="rounded-full bg-brand-mint/25 border border-brand-mint/50 px-3 py-1 text-[11px] font-bold text-[#064E3B]">
              {t('b2b.dash.cohort_diff', { rate: percent(analytics.return_reduction_percentage) })}
            </span>
          </div>

          <div className="space-y-5">
            {cohortBars.map((c) => (
              <div key={c.label}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-xs font-bold text-slate-700">
                  <span>{c.label}</span>
                  <span className={`font-mono text-sm ${c.text}`}>{percent(c.rate)}</span>
                </div>
                <div className="h-4 w-full overflow-hidden rounded-full bg-slate-100">
                  <motion.div
                    className={`h-full rounded-full ${c.bar}`}
                    initial={reduceMotion ? false : { width: 0 }}
                    animate={{ width: `${Math.min(100, c.rate ?? 0)}%` }}
                    transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1] }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-[11px] leading-relaxed text-slate-600">
            <p>
              <strong className="font-bold text-brand-charcoal">
                {t('b2b.dash.methodology')}:
              </strong>{' '}
              {analytics.return_cohorts?.methodology}
            </p>
            <p className="text-slate-500">
              {t('b2b.dash.spend_line', {
                spend: `$${analytics.ad_spend_total}`,
                revenue: `$${analytics.ad_revenue_total}`,
                bopis: percent(analytics.bopis_store_fulfillment_rate),
              })}
            </p>
            <p className="text-slate-500">{t('b2b.dash.source_note')}</p>
          </div>
        </Surface>

        <Surface variant="solid" reveal revealDelay={0.06} as="section" className="col-span-12 space-y-4 rounded-2xl p-6 lg:col-span-5 bg-white border border-slate-200 shadow-xs">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="font-serif text-lg font-bold text-brand-charcoal">
              {t('b2b.dash.styled_title')}
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">{t('b2b.ranked_by_appearances')}</p>
          </div>

          {analytics.outfit_appearance_rankings.length === 0 ? (
            <div className="space-y-1.5 py-8 text-center">
              <p className="text-xs font-semibold text-slate-600">{t('b2b.dash.styled_empty')}</p>
              <p className="mx-auto max-w-xs text-[11px] leading-relaxed text-slate-500">
                {t('b2b.dash.styled_empty_note')}
              </p>
            </div>
          ) : (
            <ol className="space-y-3">
              {analytics.outfit_appearance_rankings.map((rank: any, idx: number) => (
                <li key={rank.product_id} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-2.5 hover:border-brand-hairline transition-colors">
                  <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${rankPillStyles[idx % rankPillStyles.length]}`}>
                    #{idx + 1}
                  </span>
                  <span className="h-14 w-12 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-white">
                    <HonestProductImage
                      src={rank.thumbnail_url}
                      alt={rank.product_title}
                      className="h-full w-full object-cover"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-bold text-brand-charcoal">
                      {rank.product_title}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {t('b2b.dash.styled_note', { count: rank.outfit_appearances })}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {t('b2b.dash.styled_rates', {
                        cart: rank.add_to_cart_rate,
                        purchase: rank.purchase_rate,
                      })}
                    </span>
                  </span>
                  <span className="text-end text-[11px]">
                    <span className="block font-bold text-[#065F46]">{rank.purchase_rate}%</span>
                    <span className="block text-slate-500">{t('b2b.dash.conversion')}</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Surface>
      </div>

      {/* ---------------------------------------------------- 5 · catalog strip */}
      <Surface variant="solid" reveal as="section" className="grid grid-cols-2 lg:grid-cols-4">
        {(
          [
            ['b2b.dash.catalog_products', analytics.total_products_count, ''],
            ['b2b.dash.catalog_skus', analytics.total_skus_count, ''],
            ['b2b.dash.catalog_purchases', analytics.total_purchases, 'text-emerald-700'],
            ['b2b.dash.catalog_cart', analytics.total_add_to_carts, ''],
          ] as const
        ).map(([key, value, tone], i) => (
          <div
            key={key}
            className={
              'space-y-1 p-5 ' +
              [
                '',
                'border-s border-slate-200',
                'border-t border-slate-200 lg:border-s lg:border-t-0',
                'border-s border-t border-slate-200 lg:border-t-0',
              ][i]
            }
          >
            <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-600">
              {t(key)}
            </span>
            <span className={`block font-serif text-lg font-black ${tone || 'text-brand-charcoal'}`}>
              {Number(value).toLocaleString(i18n.language)}
            </span>
          </div>
        ))}
      </Surface>
    </div>
  );
};
