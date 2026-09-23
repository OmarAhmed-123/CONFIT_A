import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useCapabilities } from '../../hooks/useCapabilities';

/**
 * TrustFooter — the commerce claims in the site footer, bound to the
 * deployment's OWN capability flags.
 *
 * WHY THIS EXISTS (audit 2026-09-21, finding "بعض الوعود التسويقية في footer
 * مثل BNPL وBOPIS والقياسات الحيوية تحتاج شروطًا وموافقة وحدود توفر واضحة"):
 *
 * The footer printed four fixed marketing lines regardless of what the
 * platform could do. On the live deployment at the time of this audit that
 * produced three defects that are simply FALSE on the rendered page:
 *
 *   1. "Tabby & Tamara 0% Interest BNPL" — the server reported
 *      `bnpl_live: false, payments_mode: "demo"`. Instalment payments are not
 *      enabled; checkout shows a simulated adapter. A live storefront
 *      advertising a payment method it does not accept is not a copy issue.
 *   2. "GDPR Privacy & On-Device Biometrics" — no biometric computation runs
 *      anywhere in this product. The measurement flow compiles the user's
 *      SELF-REPORTED slider values (see CameraScanModal.runVisionAnalysis,
 *      which states this explicitly) and the photo is uploaded to the API.
 *      The claim is withdrawn rather than reworded: there is nothing on-device
 *      to describe.
 *   3. "30-Day Zero-Fee Concierge Returns" — the number was hard-typed in the
 *      string while the API already exposes `returns_window_days`. Two copies
 *      of one fact.
 *
 * CONTRACT: a claim is rendered only when the matching flag is true; when it
 * is false the SAME SLOT shows the honest counterpart (demo mode / not
 * configured) instead of disappearing, because a silently missing promise is
 * harder to audit than an explicit one — and `disclosure_source` states on
 * screen that these labels come from the deployment's endpoint.
 *
 * When `/catalog/capabilities` cannot be fetched, useCapabilities falls back to
 * every-flag-false (HONEST_FALLBACK_CAPABILITIES), so an unreachable API
 * degrades to the most conservative wording rather than the most flattering.
 */
export const TrustFooter: React.FC = () => {
  const { t } = useTranslation();
  const { capabilities, isLoading } = useCapabilities();

  const badge = (live: boolean, liveKey: string, offKey: string) => (
    <span
      className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
        live ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-600/30 text-slate-400'
      }`}
    >
      {live ? t(liveKey) : t(offKey)}
    </span>
  );

  /**
   * While the flags are still loading we must not render a claim: rendering
   * the optimistic wording first and correcting it a moment later is exactly
   * the flash-of-false-claim the audit is about. The whole list waits.
   */
  if (isLoading) {
    return (
      <ul className="space-y-2 font-light" aria-busy="true">
        <li className="h-4 w-40 bg-slate-700/40 rounded animate-pulse" />
        <li className="h-4 w-52 bg-slate-700/40 rounded animate-pulse" />
        <li className="h-4 w-44 bg-slate-700/40 rounded animate-pulse" />
      </ul>
    );
  }

  const {
    payments_live,
    cod_live,
    bnpl_live,
    bopis_live,
    bopis_store_count,
    returns_window_days,
  } = capabilities;

  /**
   * `payments_live` is measured (a PSP rail that can really charge), and the
   * sentence behind the live badge is about a payment service provider — so the
   * two now agree. When it is false there are two different truths, and saying
   * the wrong one is a claim either way:
   *
   *  * cash on delivery settles → the shopper CAN complete an order; the demo
   *    disclosure's "no goods are shipped" would be false;
   *  * nothing settles → the original disclosure is exactly right.
   */
  const paymentDisclosureKey = cod_live
    ? 'footer.payment_mode_disclosure_cod'
    : 'footer.payment_mode_disclosure';

  /**
   * A capability flag says a FEATURE is enabled; it does not guarantee that the
   * number behind it is usable. `returns_window_days: 0` rendered literally as
   * "0-Day Zero-Fee Concierge Returns", and a missing value rendered as
   * "undefined-day". Both are claims the reader has no way to disbelieve, so the
   * number is validated here and a non-answer falls back to the honest wording.
   *
   * This is the same discipline the rest of this component applies to booleans,
   * extended to the values: never print a figure the deployment did not give us.
   */
  const asPositiveCount = (value: unknown): number => {
    const n = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  };
  const returnsDays = asPositiveCount(returns_window_days);
  const storeCount = asPositiveCount(bopis_store_count);
  const returnsLive = returnsDays > 0;
  // `bopis_live` with a zero store count would promise pickup at no locations.
  const bopisAvailable = bopis_live && storeCount > 0;

  return (
    <ul className="space-y-2 font-light" data-testid="trust-footer">
      {/* Payments — always stated, because the mode is what a shopper needs. */}
      <li className="flex items-start gap-2">
        {badge(payments_live, 'footer.badge_live', 'footer.badge_demo')}
        <span className="text-slate-300">
          {payments_live ? t('footer.payments_live') : t(paymentDisclosureKey)}
        </span>
      </li>

      {/* BNPL — "Tabby & Tamara 0% interest" only when the flag is live. */}
      <li className="flex items-start gap-2">
        {badge(bnpl_live, 'footer.badge_live', 'footer.badge_unavailable')}
        <span className="text-slate-300">
          {bnpl_live
            ? t('footer.bnpl_available', { providers: t('footer.bnpl_brand_name_full') })
            : t('footer.bnpl_unavailable')}
        </span>
      </li>

      {/* BOPIS — the store count is a real COUNT() from the stores table. */}
      <li className="flex items-start gap-2">
        {badge(bopisAvailable, 'footer.badge_live', 'footer.badge_unavailable')}
        <span className="text-slate-300">
          {bopisAvailable
            ? t('footer.bopis_available', { count: storeCount })
            : t('footer.bopis_unavailable')}
        </span>
      </li>

      {/* Returns — the window is the server's value, never a typed constant. */}
      <li className="flex items-start gap-2">
        {badge(returnsLive, 'footer.badge_live', 'footer.badge_unavailable')}
        <span className="text-slate-300">
          {returnsLive
            ? t('footer.returns_available', { days: returnsDays })
            : t('footer.returns_unavailable')}
        </span>
      </li>

      {/* Privacy — states only what the product does. No biometrics claim. */}
      <li className="flex items-start gap-2">
        {badge(true, 'footer.badge_live', 'footer.badge_live')}
        <span className="text-slate-300">{t('footer.trust_privacy')}</span>
      </li>

      {/* Storage — the deployment reports its real storage mode. */}
      {capabilities.storage_mode === 'local' && (
        <li className="flex items-start gap-2">
          {badge(false, 'footer.badge_live', 'footer.badge_unavailable')}
          <span className="text-slate-400">{t('footer.trust_storage_local_note')}</span>
        </li>
      )}

      <li className="pt-1">
        <Link to="/privacy" // Measured 2026-09-23 (axe, real browser): slate-500 on this panel is
        // 4.02:1 at 10px — below the 4.5:1 AA threshold. slate-400 clears it.
        className="text-[10px] text-slate-400 hover:text-slate-300 underline">
          {t('footer.disclosure_source')}
        </Link>
      </li>
    </ul>
  );
};
