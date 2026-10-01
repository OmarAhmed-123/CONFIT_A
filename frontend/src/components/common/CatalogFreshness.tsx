import React from "react";
import { useTranslation } from "react-i18next";
import {
  useCatalogRevision,
  CATALOG_REVISION_POLL_MS,
} from "../../hooks/useCatalogRevision";
import { StatusIcon, type StatusIconStatus } from "./InteractionPrimitives";

/**
 * Mounts the catalogue freshness poll once, for every role.
 *
 * Renders nothing. It exists because `useCatalogRevision` needs to live
 * INSIDE the QueryClientProvider (it calls `useQueryClient`), and putting a
 * hook call directly in `App` would tie the poll's lifetime to the provider's
 * own render rather than to a component that can be moved or disabled.
 *
 * One mount, one interval, all roles — a shopper, a brand user and an admin
 * all learn about a stock change from the same signal instead of each view
 * inventing its own refresh rule.
 */
export const CatalogFreshness: React.FC = () => {
  useCatalogRevision(true);
  return null;
};

/**
 * Visible freshness status (spec 14) for surfaces where stale stock is the
 * risk (B2B inventory). Three HONEST states driven by the same deduplicated
 * `['catalog','revision']` query the root poll owns — no second request
 * stream, react-query shares the subscription:
 *
 *   checking  → first fingerprint still in flight (loading glyph)
 *   live      → fingerprint current as of the last poll; the copy states
 *               the poll interval instead of claiming "real-time" (polling
 *               is not push, and we say so)
 *   degraded  → the LAST poll failed: data still renders but freshness is
 *               no longer guaranteed. Warning shape + text — never silent,
 *               never an invented error page.
 *
 * Container carries `role="status"` + `aria-live="polite"` (§6.3); the icon
 * is decorative because the sentence beside it is the state (§6.2). The
 * revision fingerprint is a CODE, so it stays LTR inside the Arabic page.
 */
export const CatalogFreshnessIndicator: React.FC<{ className?: string }> = ({
  className = "",
}) => {
  const { t } = useTranslation();
  const { revision, error } = useCatalogRevision(true);

  let status: StatusIconStatus;
  let text: string;
  if (revision === null && error) {
    status = "warning";
    text = t("freshness.degraded");
  } else if (revision === null) {
    status = "loading";
    text = t("freshness.checking");
  } else if (error) {
    status = "warning";
    text = t("freshness.degraded");
  } else {
    status = "success";
    text = t("freshness.live", {
      seconds: Math.round(CATALOG_REVISION_POLL_MS / 1000),
    });
  }

  return (
    <p
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="catalog-freshness"
      data-freshness-state={status}
      className={`inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 ${className}`}
    >
      <StatusIcon status={status} size={14} />
      <span>{text}</span>
      {revision ? (
        <span dir="ltr" className="font-mono text-[10px] text-slate-400">
          {revision.slice(0, 8)}
        </span>
      ) : null}
    </p>
  );
};

export default CatalogFreshness;
