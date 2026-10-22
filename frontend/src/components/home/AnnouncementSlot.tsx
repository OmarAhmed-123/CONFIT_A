import React from "react";
import { AnnouncementBar } from "./AnnouncementBar";
import { useCapabilities } from "../../hooks/useCapabilities";
// The sentinel lives in its own module precisely so this component never has to
// import a constant from a module that tests replace wholesale with vi.mock.
import { HONEST_FALLBACK_CAPABILITIES } from "../../hooks/capabilitiesFallback";

/**
 * The announcement bar's layout slot — the homepage CLS fix.
 *
 * THE DEFECT (measured 2026-10-21, Chromium 156, 412x915, web-vitals)
 *   `/` scored CLS 0.8088. Ablating only `/catalog/capabilities` dropped it to
 *   0.0147; ablating an unrelated endpoint left 0.7641. The bar is data-gated on
 *   a real server-published free-shipping threshold (a deliberate honesty
 *   contract), so it was inserted into normal flow above the hero ~1.3s after
 *   first paint, pushing the hero down 46px while the content container's
 *   negative margin collapsed 24px back.
 *
 * WHAT WAS RULED OUT BY MEASUREMENT, NOT ARGUMENT
 *   - "Fetch the data earlier": fulfilling /catalog/capabilities with ZERO
 *     latency still scored 0.8077. React commits the bar after first paint
 *     whatever the response time, so this cannot work in a client-rendered SPA.
 *   - Reserving the slot: 0.0088 on the same page, final geometry identical to
 *     the unreserved page (hero top 253, page height 11888).
 *
 * THE HARD PART: a late boolean cannot be known at first paint
 *   The hero's final position depends on whether a bar will exist, and that
 *   answer arrives ~1.3s late. Reserving commits to "bar present". Releasing that
 *   commitment after the hero is painted moves it, and a release at ~1.3s
 *   measured 0.8145 — WORSE than the defect, in exactly the failure case
 *   (capability fetch aborted) where nothing should have moved at all.
 *
 *   So the reservation is never released mid-session. It is decided at first
 *   paint from what is already known locally:
 *     - this shopper dismissed this exact policy  -> nothing will render: no space
 *     - a previous visit proved this deployment has no policy -> no space
 *     - anything else (loading, unknown, failed)  -> hold the space
 *   A deployment that genuinely has no policy therefore pays a 46px gap on its
 *   FIRST visit (invisible to CLS, since nothing moves) and writes a hint so
 *   later visits reserve nothing. That trade is deliberate: a stable band is a
 *   layout design choice, a 0.81 viewport shift is a Core Web Vitals failure.
 *
 * Dismissal still removes the bar immediately, and that removal is a layout
 * shift too — but it follows a click, and layout shifts within 500ms of user
 * input are excluded from CLS by definition (hadRecentInput).
 */

/** Measured height of the rendered bar at 412px (Chromium 156): 46px. */
const RESERVED_HEIGHT_PX = 46;

/** Same key and value format as AnnouncementBar — see there for the rationale. */
const DISMISS_KEY = "confit.announcement.freeship.v1";

/**
 * What the last resolved visit proved about this deployment.
 * Absent = unknown (first visit, or the fetch failed).
 */
const POLICY_HINT_KEY = "confit.announcement.policy.v1";

type PolicyHint = "present" | "none" | null;

const readHint = (): PolicyHint => {
  try {
    const v = window.localStorage.getItem(POLICY_HINT_KEY);
    return v === "present" || v === "none" ? v : null;
  } catch {
    return null;
  }
};

const writeHint = (v: PolicyHint) => {
  try {
    if (v) window.localStorage.setItem(POLICY_HINT_KEY, v);
  } catch {
    /* private mode: the next visit simply reserves again, which is safe */
  }
};

const isRenderable = (threshold?: number | null, currency?: string | null) =>
  threshold != null && Number.isFinite(threshold) && threshold > 0 && Boolean(currency);

/**
 * Presentational slot. `reserved` decides whether the space is held this frame.
 * Kept free of hooks so every branch is testable without mocking React Query.
 */
export const AnnouncementSlotView: React.FC<{
  reserved: boolean;
  showBar: boolean;
  threshold?: number | null;
  currency?: string | null;
  onDismiss?: () => void;
}> = ({ reserved, showBar, threshold, currency, onDismiss }) => (
  <div
    data-testid="announcement-slot"
    data-reserved={reserved ? "true" : "false"}
    // min-height, not height: a longer localized sentence must wrap and grow the
    // bar, never be clipped. The reserve only guarantees the floor.
    style={reserved ? { minHeight: RESERVED_HEIGHT_PX } : undefined}
  >
    {showBar ? (
      <AnnouncementBar
        threshold={threshold}
        currency={currency}
        onDismiss={onDismiss}
      />
    ) : null}
  </div>
);

export const AnnouncementSlot: React.FC = () => {
  const { capabilities, isLoading } = useCapabilities();
  const threshold = capabilities.free_shipping_threshold;
  const currency = capabilities.shipping_currency;
  const renderable = isRenderable(threshold, currency);

  // Read once per mount: this is a first-paint decision, not a reactive one.
  const [hintAtMount] = React.useState<PolicyHint>(readHint);
  const [dismissed, setDismissed] = React.useState<boolean>(() => {
    if (!renderable) return false;
    try {
      return window.localStorage.getItem(DISMISS_KEY) === `${threshold}:${currency}`;
    } catch {
      return false;
    }
  });

  // Keep the dismissal flag honest if the policy value changes under us (a
  // merchandiser editing the threshold makes the bar news again).
  React.useEffect(() => {
    if (!renderable) {
      setDismissed(false);
      return;
    }
    try {
      setDismissed(window.localStorage.getItem(DISMISS_KEY) === `${threshold}:${currency}`);
    } catch {
      setDismissed(false);
    }
  }, [renderable, threshold, currency]);

  // Record what the server actually reported, for the NEXT first paint only.
  //
  // A failed fetch is indistinguishable from "no policy" by value — both leave
  // the threshold and currency null — but they must not be treated the same.
  // `useCapabilities` returns the exported HONEST_FALLBACK_CAPABILITIES object
  // itself when it has no data, so identity tells a real answer apart from a
  // degraded one. Writing "none" off a failure would permanently strip the
  // space from a deployment that does have a policy.
  React.useEffect(() => {
    if (isLoading) return;
    if (renderable) {
      writeHint("present");
      return;
    }
    const isRealAnswer = capabilities !== HONEST_FALLBACK_CAPABILITIES;
    if (isRealAnswer) writeHint("none");
  }, [isLoading, renderable, capabilities]);

  const showBar = renderable && !dismissed;
  // Decided at first paint; never revised downward by a later response.
  const reserved = showBar || (!dismissed && hintAtMount !== "none");

  return (
    <AnnouncementSlotView
      reserved={reserved}
      showBar={showBar}
      threshold={threshold}
      currency={currency}
      onDismiss={() => setDismissed(true)}
    />
  );
};
