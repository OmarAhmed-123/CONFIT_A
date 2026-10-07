import React from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { formatMoney } from "../../i18n/format";
import { usePrefersReducedMotion } from "../common/InteractionPrimitives";

/**
 * Announcement bar — the storefront's one-line conversion hook.
 *
 * Honesty contract (the reason this component exists at all):
 * - It renders ONLY when the server publishes a real free-shipping policy
 *   (`/catalog/capabilities.free_shipping_threshold`, currency-converted with
 *   the same rate table the cart uses). No server figure → no bar. The
 *   classic "$50 free shipping" hardcoded banner is exactly the defect class
 *   this storefront bans.
 * - One message, no rotation, no countdown: a single true sentence.
 *
 * UX: dismissible, and the dismissal is remembered per policy value — if the
 * merchandiser later changes the threshold, the new fact is news and the bar
 * returns. Entrance is a slide/fade; disabled under prefers-reduced-motion.
 */
const DISMISS_KEY = "confit.announcement.freeship.v1";

export const AnnouncementBar: React.FC<{
  threshold?: number | null;
  currency?: string | null;
}> = ({ threshold, currency }) => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  const reduceMotion = usePrefersReducedMotion();

  // Remember WHICH policy was dismissed, not just "dismissed".
  const policyTag = `${threshold ?? ""}:${currency ?? ""}`;
  const [dismissed, setDismissed] = React.useState<boolean>(() => {
    try {
      return window.localStorage.getItem(DISMISS_KEY) === policyTag;
    } catch {
      return false;
    }
  });

  if (
    dismissed ||
    threshold == null ||
    !Number.isFinite(threshold) ||
    threshold <= 0 ||
    !currency
  ) {
    return null;
  }

  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, policyTag);
    } catch {
      /* private mode — the bar simply returns next visit */
    }
  };

  const body = (
    <div
      role="region"
      data-testid="announcement-bar"
      aria-label={t("home.announcement_aria")}
      className="flex items-center justify-center gap-3 rounded-2xl border border-[#C5A059]/30 bg-[#0C0E1E] px-4 py-2.5"
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[#C5A059]" />
      <p className="text-[11px] font-semibold tracking-wide text-[#FAF9F6] sm:text-xs">
        {t("home.announce_free_shipping", {
          amount: formatMoney(Math.round(threshold * 100), currency, lang),
        })}
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("a11y.dismiss_announcement")}
        className="ms-1 flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
      >
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  );

  if (reduceMotion) {
    return body;
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      {body}
    </motion.div>
  );
};
